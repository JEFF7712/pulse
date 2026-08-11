"""The user's self-description, and how much it can currently be trusted.

`profile.md` is written once at `pulse init` and never again. That is fine as a design
for *stated* self-description — it is the user's own words about themselves — but it
becomes a trap the moment an agent treats it as current fact. A four-month-old profile
that says "current projects: A, B, C" is not evidence that the user still believes that;
it is evidence that they believed it four months ago.

The distinction matters because "what you say about yourself versus what the data shows"
is one of the few genuinely non-obvious findings available, and it is only a finding if
the stated side is actually current. Against a stale profile the same divergence has two
readings that cannot be told apart: a real self-narrative gap, or a document that
correctly described a different month.

So two rules, and the whole module exists to enforce them:

1. **The agent never edits stated text.** The self-description is the measurement
   instrument for that comparison. An agent that "corrects" it toward the data destroys
   the signal permanently and silently, and would then find perfect agreement forever.
2. **Staleness is always reported alongside it.** An agent that can see the profile is
   130 days old can hedge correctly; one that cannot will assert a gap it has not earned.

Observations *derived* from data go somewhere else entirely — `04-Config/observed.md` —
so the two never mix and the user can always see which is which.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

PROFILE_FILE = "profile.md"
OBSERVED_FILE = "observed.md"
FACTS_FILE = "facts.md"

# Past this age a stated profile is a historical document, not a current claim.
STALE_AFTER_DAYS = 120
# Past this it is old enough that divergence says nothing at all on its own.
VERY_STALE_AFTER_DAYS = 240

_CONFIRMED_RE = re.compile(
    r"^\*\*Last confirmed:\*\*\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE
)


@dataclass(slots=True)
class ProfileFreshness:
    exists: bool
    last_confirmed: str | None
    age_days: int | None
    staleness: str  # missing | fresh | stale | very_stale | unknown
    guidance: str

    def as_dict(self) -> dict:
        return {
            "exists": self.exists,
            "last_confirmed": self.last_confirmed,
            "age_days": self.age_days,
            "staleness": self.staleness,
            "guidance": self.guidance,
        }


def parse_last_confirmed(content: str) -> str | None:
    """Read the `**Last confirmed:** YYYY-MM-DD` marker, if the profile carries one."""
    match = _CONFIRMED_RE.search(content or "")
    return match.group(1) if match else None


def assess_profile(
    content: str, *, as_of: date, file_mtime: date | None = None
) -> ProfileFreshness:
    """Judge how far a stated profile can be trusted as a current claim.

    Falls back to the file's mtime when no explicit marker is present, which is the
    case for every profile written before the marker existed.
    """
    if not (content or "").strip():
        return ProfileFreshness(
            exists=False,
            last_confirmed=None,
            age_days=None,
            staleness="missing",
            guidance=(
                "No stated profile. Do not infer what the user believes about "
                "themselves; report only what the data shows."
            ),
        )

    marker = parse_last_confirmed(content)
    confirmed = marker
    if confirmed is None and file_mtime is not None:
        confirmed = file_mtime.isoformat()

    if confirmed is None:
        return ProfileFreshness(
            exists=True,
            last_confirmed=None,
            age_days=None,
            staleness="unknown",
            guidance=(
                "Stated profile has no date. Treat it as possibly out of date: a "
                "divergence from the data is not by itself evidence of a self-narrative "
                "gap."
            ),
        )

    age = (as_of - date.fromisoformat(confirmed)).days
    if age >= VERY_STALE_AFTER_DAYS:
        staleness = "very_stale"
        guidance = (
            f"Stated profile is {age} days old. It describes a different period of the "
            "user's life. Divergence from current data is expected and is NOT a finding "
            "on its own — say the profile needs refreshing instead of asserting a gap."
        )
    elif age >= STALE_AFTER_DAYS:
        staleness = "stale"
        guidance = (
            f"Stated profile is {age} days old. Divergence has two readings — a real "
            "self-narrative gap, or a profile that correctly described an earlier "
            "period. Say which you mean, and hedge if you cannot tell them apart."
        )
    else:
        staleness = "fresh"
        guidance = (
            f"Stated profile was confirmed {age} days ago, so it can be read as a "
            "current claim about what the user believes."
        )

    return ProfileFreshness(
        exists=True,
        last_confirmed=confirmed,
        age_days=age,
        staleness=staleness,
        guidance=guidance,
    )


def stamp_last_confirmed(content: str, day: str) -> str:
    """Set or replace the `Last confirmed` marker, leaving all other text untouched."""
    if _CONFIRMED_RE.search(content or ""):
        return _CONFIRMED_RE.sub(f"**Last confirmed:** {day}", content, count=1)

    body = (content or "").lstrip("\n")
    lines = body.splitlines()
    # Slot the marker under a leading heading if there is one, so the file still reads
    # naturally in Obsidian rather than opening on metadata.
    if lines and lines[0].startswith("#"):
        head, rest = lines[0], lines[1:]
        return "\n".join([head, "", f"**Last confirmed:** {day}", *rest]) + "\n"
    return f"**Last confirmed:** {day}\n\n{body}".rstrip() + "\n"


# ----------------------------------------------------------------------
# Facts
# ----------------------------------------------------------------------

FACTS_HEADER = """# Facts

Plain facts about you — where you live, where you study or work, what year you
graduate. Kept here rather than in `profile.md` so that confirming a correction never
rewrites a word you wrote yourself.

Pulse only changes a line here after you confirm it. Edit or delete anything freely.
"""

_FACT_RE = re.compile(
    r"^- \*\*(?P<field>[^*]+):\*\*\s*(?P<value>.*?)\s*$", re.MULTILINE
)


def parse_facts(content: str) -> dict[str, str]:
    """Read `- **field:** value` lines into a mapping."""
    return {
        m.group("field").strip(): m.group("value").strip()
        for m in _FACT_RE.finditer(content or "")
    }


def upsert_fact(content: str, field: str, value: str, *, confirmed_on: str) -> str:
    """Set one fact, leaving every other line byte-identical.

    Rewriting the whole file from a parsed mapping would silently discard anything the
    user added by hand that does not match the expected shape, so edit in place.
    """
    field = field.strip()
    line = f"- **{field}:** {value.strip()}  _(confirmed {confirmed_on})_"
    body = content if (content or "").strip() else FACTS_HEADER

    pattern = re.compile(
        rf"^- \*\*{re.escape(field)}:\*\*.*$", re.MULTILINE | re.IGNORECASE
    )
    if pattern.search(body):
        return pattern.sub(line, body, count=1)
    return body.rstrip() + "\n" + line + "\n"


OBSERVED_HEADER = """# Observed

Derived from your data by your agent. Kept separate from `profile.md` on purpose:
that file is what *you* say about yourself and is never edited automatically, because
comparing the two is only meaningful while they stay independent.

Edit or delete anything here freely.
"""


def observed_scaffold() -> str:
    return OBSERVED_HEADER

"""The gate between "an agent proposed something" and "the user gets a push".

This is where the old failure mode gets fixed. Given only a schedule and a day of
data, an agent will always produce prose, so it produces prose about nothing: it
re-asserts a pattern it already recorded, or it appends the *absence* of a pattern
as fresh evidence for that pattern. Real vault files ended up with eight entries
reading "no such activity detected" under a finding's evidence log.

So novelty is enforced on the output, independent of how a finding was reached:

* a proposal too close to an existing pattern is a duplicate, not a discovery;
* an update whose observation restates the previous one is not a change;
* only a genuine create, or a materially changed pattern, is worth a notification.

Similarity uses the local embedder when one is available and falls back to token
overlap, so the gate keeps working without the semantic extra installed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from pulse.domain.pattern_statuses import is_closed_status

# Above this similarity, a proposal is the same finding as one already on file.
DUPLICATE_THRESHOLD = 0.86
# Above this, a new observation says nothing the previous one did not.
RESTATEMENT_THRESHOLD = 0.90

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*?)\s*$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class PatternSnapshot:
    """The parts of a pattern that decide whether it changed."""

    slug: str
    title: str
    status: str
    observation: str
    evidence: tuple[str, ...]

    def fingerprint(self) -> str:
        """Hash of the meaningful content, excluding volatile fields.

        `Last updated` moves on every run by definition, so including it would make
        every pattern look changed every time and defeat the whole gate.
        """
        payload = "\x1f".join(
            [self.title, self.status, self.observation, *self.evidence]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class PatternChanges:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.created or self.updated)

    def all_slugs(self) -> list[str]:
        return [*self.created, *self.updated]


def _section(content: str, heading: str) -> str:
    matches = list(_SECTION_RE.finditer(content))
    for i, match in enumerate(matches):
        if match.group(1).strip().lower() != heading.lower():
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        return content[start:end].strip()
    return ""


def _field(content: str, name: str) -> str:
    for match in _FIELD_RE.finditer(content):
        if match.group(1).strip().lower() == name.lower():
            return match.group(2).strip()
    return ""


def parse_pattern(slug: str, content: str) -> PatternSnapshot:
    observation = _section(content, "Observation")
    evidence_block = _section(content, "Evidence Log")
    evidence = tuple(
        line.lstrip("- ").strip()
        for line in evidence_block.splitlines()
        if line.strip().startswith("-")
    )
    title = ""
    for line in content.splitlines():
        if line.startswith("# Pattern:"):
            title = line.removeprefix("# Pattern:").strip()
            break
    return PatternSnapshot(
        slug=slug,
        title=title,
        status=_field(content, "Status"),
        observation=observation,
        evidence=evidence,
    )


def snapshot_patterns(patterns: list[dict]) -> dict[str, PatternSnapshot]:
    """Build slug → snapshot from ``VaultMemory.read_patterns()`` output."""
    return {
        p["slug"]: parse_pattern(p["slug"], p["content"])
        for p in patterns
        if p.get("slug")
    }


def diff_patterns(
    before: dict[str, PatternSnapshot], after: dict[str, PatternSnapshot]
) -> PatternChanges:
    """What actually changed between two vault states.

    Deriving the notification from vault state rather than from what the agent said
    means the push describes a recorded finding, not a narrative about the day.
    """
    changes = PatternChanges()
    for slug, snap in after.items():
        prior = before.get(slug)
        if prior is None:
            changes.created.append(slug)
        elif prior.fingerprint() != snap.fingerprint():
            changes.updated.append(slug)
    changes.created.sort()
    changes.updated.sort()
    return changes


# ----------------------------------------------------------------------
# similarity
# ----------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def similarity(a: str, b: str, embedder=None) -> float:
    """Cosine similarity when an embedder is available, else token overlap."""
    if not a.strip() or not b.strip():
        return 0.0
    if embedder is not None:
        try:
            from pulse.semantic.search import cosine

            vecs = embedder.embed([a, b])
            return max(0.0, cosine(vecs[0], vecs[1]))
        except Exception:
            pass  # degrade to lexical rather than fail the gate
    return _jaccard(a, b)


def find_duplicate(
    proposed_title: str,
    proposed_observation: str,
    existing: dict[str, PatternSnapshot],
    *,
    embedder=None,
    threshold: float = DUPLICATE_THRESHOLD,
    ignore_slug: str | None = None,
) -> tuple[str, float] | None:
    """Return ``(slug, score)`` of an existing pattern this proposal duplicates."""
    proposed = f"{proposed_title}\n{proposed_observation}".strip()
    best: tuple[str, float] | None = None
    for slug, snap in existing.items():
        if slug == ignore_slug:
            continue
        # A closed pattern describes something that stopped. If it is happening again
        # that is a new finding, and a stale one must never gag the agent about now.
        if is_closed_status(snap.status):
            continue
        score = similarity(proposed, f"{snap.title}\n{snap.observation}", embedder)
        if score >= threshold and (best is None or score > best[1]):
            best = (slug, score)
    return best


def is_restatement(
    new_observation: str,
    previous_observation: str,
    *,
    embedder=None,
    threshold: float = RESTATEMENT_THRESHOLD,
) -> bool:
    """True when an update adds nothing the pattern did not already say.

    Guards the specific failure that filled real vault files: the same finding
    re-appended with a slightly different number every time the job ran.
    """
    if not previous_observation.strip():
        return False
    return similarity(new_observation, previous_observation, embedder) >= threshold

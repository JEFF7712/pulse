"""YAML frontmatter and Obsidian graph helpers for Pulse vault markdown."""

from __future__ import annotations

import re
from datetime import date

from pulse.vault.wikilinks import daily_note_link

_ISO_DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def format_daily_digest_frontmatter(iso_day: str) -> str:
    return (
        "---\n"
        "pulse: true\n"
        "type: daily-digest\n"
        f"date: {iso_day}\n"
        "tags: [pulse, pulse/digest]\n"
        "---\n\n"
    )


def format_pattern_frontmatter(slug: str) -> str:
    return (
        "---\n"
        "pulse: true\n"
        "type: pattern\n"
        f"slug: {slug}\n"
        "tags: [pulse, pulse/pattern]\n"
        "---\n\n"
    )


def format_daily_pulse_links_section() -> str:
    """Wikilinks to long-lived vault notes plus inline tags for Obsidian."""
    return (
        "## Pulse links\n"
        "Core notes this digest relates to:\n"
        "- [[04-Config/profile]]\n"
        "- [[03-Life/routines]]\n"
        "\n"
        "#pulse #pulse/digest\n"
    )


def collect_pattern_related_iso_days(
    first_seen: str,
    last_updated: str,
    evidence_log: list[str],
) -> list[str]:
    """Collect YYYY-MM-DD strings from metadata and evidence lines."""
    days: set[str] = set()
    for raw in (first_seen, last_updated):
        parsed = _parse_iso_day_prefix(raw)
        if parsed:
            days.add(parsed)
    for line in evidence_log:
        for m in _ISO_DAY.finditer(line):
            days.add(m.group(1))
    valid: list[str] = []
    for d in sorted(days):
        try:
            date.fromisoformat(d)
        except ValueError:
            continue
        valid.append(d)
    return valid


def _parse_iso_day_prefix(raw: str) -> str | None:
    s = (raw or "").strip()
    if len(s) < 10:
        return None
    candidate = s[:10]
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def format_pattern_related_days_section(related_days: list[str]) -> str:
    if not related_days:
        body = "_No daily digest links yet._\n"
    else:
        body = "".join(f"- {daily_note_link(d)}\n" for d in related_days)
    return f"## Related days\n{body}\n"

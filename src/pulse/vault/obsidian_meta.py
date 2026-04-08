"""YAML frontmatter and Obsidian graph helpers for Pulse vault markdown."""

from __future__ import annotations

import re
from datetime import date

_ISO_DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def format_pattern_frontmatter(slug: str) -> str:
    return (
        "---\n"
        "pulse: true\n"
        "type: pattern\n"
        f"slug: {slug}\n"
        "tags: [pulse, pulse/pattern]\n"
        "---\n\n"
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
        body = "_No related dates recorded yet._\n"
    else:
        body = "".join(f"- {d}\n" for d in related_days)
    return f"## Related days\n{body}\n"

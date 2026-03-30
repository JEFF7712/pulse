"""Obsidian-style wikilinks for Pulse vault markdown (deterministic, path-qualified)."""

from __future__ import annotations

from datetime import date, timedelta

# Path from vault root so Obsidian resolves uniquely even with other YYYY-MM-DD files.
DAILY_DIGEST_FOLDER = "01-Daily"


def daily_note_link(iso_day: str) -> str:
    """Wikilink target for a daily digest file (``iso_day`` = ``YYYY-MM-DD``)."""
    return f"[[{DAILY_DIGEST_FOLDER}/{iso_day}]]"


def format_daily_digest_nav_line(day: date) -> str:
    """Previous/next calendar day links for the top of a daily digest note."""
    prev_d = day - timedelta(days=1)
    next_d = day + timedelta(days=1)
    return (
        f"← {daily_note_link(prev_d.isoformat())} · "
        f"{daily_note_link(next_d.isoformat())} →"
    )

"""Tests for Obsidian frontmatter and related-day helpers."""

from pulse.vault.obsidian_meta import (
    collect_pattern_related_iso_days,
    format_pattern_related_days_section,
)


def test_collect_pattern_related_iso_days_dedupes_and_sorts() -> None:
    days = collect_pattern_related_iso_days(
        "2026-01-10",
        "2026-01-10",
        ["Noise on 2026-02-01 and 2026-02-01", "bad 2026-99-99 skip"],
    )
    assert days == ["2026-01-10", "2026-02-01"]


def test_format_pattern_related_days_section_empty() -> None:
    text = format_pattern_related_days_section([])
    assert "## Related days" in text
    assert "No related dates" in text


def test_format_pattern_related_days_section_plain_dates() -> None:
    text = format_pattern_related_days_section(["2026-03-01", "2026-03-02"])
    assert "- 2026-03-01" in text
    assert "- 2026-03-02" in text

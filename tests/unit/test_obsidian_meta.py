"""Tests for Obsidian frontmatter and related-day link helpers."""

from pulse.vault.obsidian_meta import (
    collect_pattern_related_iso_days,
    format_daily_digest_frontmatter,
    format_pattern_related_days_section,
)


def test_format_daily_digest_frontmatter_includes_date_and_tags() -> None:
    fm = format_daily_digest_frontmatter("2026-04-08")
    assert fm.startswith("---\n")
    assert "pulse: true" in fm
    assert "type: daily-digest" in fm
    assert "date: 2026-04-08" in fm
    assert "tags: [pulse, pulse/digest]" in fm
    assert fm.endswith("---\n\n")


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
    assert "No daily digest links" in text


def test_format_pattern_related_days_section_wikilinks() -> None:
    text = format_pattern_related_days_section(["2026-03-01", "2026-03-02"])
    assert "[[01-Daily/2026-03-01]]" in text
    assert "[[01-Daily/2026-03-02]]" in text

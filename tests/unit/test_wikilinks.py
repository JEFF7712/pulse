from datetime import date

from pulse.vault.wikilinks import daily_note_link, format_daily_digest_nav_line


def test_daily_note_link_uses_daily_folder_prefix() -> None:
    assert daily_note_link("2026-03-30") == "[[01-Daily/2026-03-30]]"


def test_format_daily_digest_nav_line_neighbors() -> None:
    line = format_daily_digest_nav_line(date(2026, 3, 15))
    assert "[[01-Daily/2026-03-14]]" in line
    assert "[[01-Daily/2026-03-16]]" in line
    assert line.startswith("←")

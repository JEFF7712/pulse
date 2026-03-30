def test_render_daily_digest_skips_nav_when_date_label_not_iso():
    from datetime import date

    from pulse.vault.renderer import render_daily_digest

    result = render_daily_digest(
        date_label="Saturday, March 22, 2026",
        timeline_items=["Morning run"],
        email_highlights=[],
        spending_items=[],
        health_items=[],
        media_items=[],
        tags=[],
        navigation_day=None,
    )
    assert "[[01-Daily/" not in result
    assert result.startswith("# Saturday, March 22, 2026\n")


def test_render_daily_digest_respects_explicit_navigation_day_when_label_not_iso():
    from datetime import date

    from pulse.vault.renderer import render_daily_digest

    result = render_daily_digest(
        date_label="Saturday, March 22, 2026",
        timeline_items=["Morning run"],
        email_highlights=[],
        spending_items=[],
        health_items=[],
        media_items=[],
        tags=[],
        navigation_day=date(2026, 3, 22),
    )
    assert "[[01-Daily/2026-03-21]]" in result
    assert "[[01-Daily/2026-03-23]]" in result


def test_render_daily_digest_includes_all_sections_and_items():
    from pulse.vault.renderer import render_daily_digest

    result = render_daily_digest(
        date_label="2026-03-22",
        timeline_items=["Morning run", "Team sync"],
        email_highlights=["Inbox to zero"],
        spending_items=["Coffee - $4.50"],
        health_items=["Steps: 10000"],
        media_items=["Read 20 pages"],
        tags=["health", "work"],
    )

    expected = "\n".join(
        [
            "# 2026-03-22",
            "",
            "← [[01-Daily/2026-03-21]] · [[01-Daily/2026-03-23]] →",
            "",
            "## Timeline",
            "- Morning run",
            "- Team sync",
            "",
            "## Email Highlights",
            "- Inbox to zero",
            "",
            "## Spending",
            "- Coffee - $4.50",
            "",
            "## Health",
            "- Steps: 10000",
            "",
            "## Media",
            "- Read 20 pages",
            "",
            "## Browsing",
            "- No browsing activity.",
            "",
            "## Tags",
            "- health",
            "- work",
        ]
    )

    assert result == expected


def test_render_daily_digest_uses_fallback_text_for_empty_sections():
    from pulse.vault.renderer import render_daily_digest

    result = render_daily_digest(
        date_label="2026-03-22",
        timeline_items=[],
        email_highlights=[],
        spending_items=[],
        health_items=[],
        media_items=[],
        tags=[],
    )

    expected = "\n".join(
        [
            "# 2026-03-22",
            "",
            "← [[01-Daily/2026-03-21]] · [[01-Daily/2026-03-23]] →",
            "",
            "## Timeline",
            "- No timeline entries.",
            "",
            "## Email Highlights",
            "- No email highlights.",
            "",
            "## Spending",
            "- No spending recorded.",
            "",
            "## Health",
            "- No health updates.",
            "",
            "## Media",
            "- No media activity.",
            "",
            "## Browsing",
            "- No browsing activity.",
            "",
            "## Tags",
            "- No tags.",
        ]
    )

    assert result == expected

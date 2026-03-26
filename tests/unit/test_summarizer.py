from datetime import UTC, date, datetime

import pytest


def test_daily_summarizer_renders_markdown_digest_from_events():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event

    day = date(2026, 3, 22)
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Team sync"},
        ),
        Event(
            id="evt-2",
            timestamp=datetime(2026, 3, 22, 10, 30, tzinfo=UTC),
            source="email",
            event_type="email.received",
            data={"subject": "Project update"},
        ),
        Event(
            id="evt-3",
            timestamp=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            source="slack",
            event_type="message.created",
            data={},
        ),
    ]

    summary = DailySummarizer().summarize(day, events)

    expected = "\n".join(
        [
            "# 2026-03-22",
            "",
            "## Timeline",
            "- Team sync",
            "- message.created",
            "",
            "## Email Highlights",
            "- Project update",
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

    assert summary.day == day
    assert summary.markdown == expected


def test_daily_summarizer_does_not_accept_an_llm_dependency_yet():
    from pulse.analysis.summarizer import DailySummarizer

    with pytest.raises(TypeError):
        DailySummarizer(llm=object())


def test_summarizer_routes_spotify_play_to_media_section():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event

    events = [Event(
        id="sp:1", timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        source="spotify", event_type="media.spotify.play",
        data={"track_name": "Cool Song", "artist": "Artist A"},
    )]
    result = DailySummarizer().summarize(date(2026, 3, 25), events)
    assert "Listened to Cool Song by Artist A" in result.markdown


def test_summarizer_routes_browsing_visit_to_browsing_section():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event

    events = [Event(
        id="br:1", timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        source="browser", event_type="browsing.visit",
        data={"url": "https://example.com", "title": "Example Site"},
    )]
    result = DailySummarizer().summarize(date(2026, 3, 25), events)
    assert "Example Site" in result.markdown
    assert "## Browsing" in result.markdown

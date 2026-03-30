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

    assert summary.day == day
    # New DigestBuilder format: timeline with time-block headers, email section, no spending/health/tags
    assert "# 2026-03-22" in summary.markdown
    assert "[[01-Daily/2026-03-21]]" in summary.markdown
    assert "[[01-Daily/2026-03-23]]" in summary.markdown
    assert "## Timeline" in summary.markdown
    assert "Team sync" in summary.markdown
    assert "## Email" in summary.markdown
    assert "Project update" in summary.markdown
    # New format does NOT include these old sections
    assert "## Spending" not in summary.markdown
    assert "## Health" not in summary.markdown
    assert "## Tags" not in summary.markdown


def test_daily_summarizer_accepts_llm_parameter():
    from pulse.analysis.summarizer import DailySummarizer

    # New DailySummarizer accepts llm parameter without raising TypeError
    summarizer = DailySummarizer(llm=None)
    assert summarizer is not None

    summarizer_with_model = DailySummarizer(
        llm=None, summarization_model="claude-haiku-4-5-20251001"
    )
    assert summarizer_with_model is not None


def test_summarizer_routes_spotify_play_to_media_section():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event

    events = [Event(
        id="sp:1", timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        source="spotify", event_type="media.spotify.play",
        data={"track_name": "Cool Song", "artist": "Artist A"},
    )]
    result = DailySummarizer().summarize(date(2026, 3, 25), events)
    # DigestBuilder formats as "Cool Song by Artist A" in the media session
    assert "Cool Song by Artist A" in result.markdown
    assert "## Media" in result.markdown


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

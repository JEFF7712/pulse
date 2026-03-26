from datetime import datetime

import pytest


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event

    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})


class TestEventSummarizerGroupsBySource:
    def test_summarize_events_groups_by_source(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 10, 0, 0)

        stats = [
            {"date": "2024-01-15", "source": "gmail", "event_type": "email.received", "count": 3, "first_at": ts, "last_at": ts},
            {"date": "2024-01-15", "source": "spotify", "event_type": "media.spotify.play", "count": 5, "first_at": ts, "last_at": ts},
        ]

        events = [
            _make_event("e1", ts, "gmail", "email.received", {"subject": "Hello World", "from": "alice@example.com"}),
            _make_event("e2", ts, "gmail", "email.received", {"subject": "Meeting Notes", "from": "bob@example.com"}),
            _make_event("e3", ts, "spotify", "media.spotify.play", {"track_name": "Bohemian Rhapsody", "artist": "Queen"}),
            _make_event("e4", ts, "spotify", "media.spotify.play", {"track_name": "Stairway to Heaven", "artist": "Led Zeppelin"}),
        ]

        baselines = [
            {"source": "gmail", "event_type": "email.received", "avg_daily": 2.0, "total": 60},
            {"source": "spotify", "event_type": "media.spotify.play", "avg_daily": 10.0, "total": 300},
        ]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events, baselines)

        # Both source sections present
        assert "## gmail (2024-01-15)" in result
        assert "## spotify (2024-01-15)" in result

        # Stat counts
        assert "email.received: 3 events" in result
        assert "media.spotify.play: 5 events" in result

        # Baseline comparison for gmail: 3 vs avg 2.0 => up 50%
        assert "baseline avg 2.0/day" in result
        assert "up 50%" in result

        # Baseline comparison for spotify: 5 vs avg 10.0 => down 50%
        assert "baseline avg 10.0/day" in result
        assert "down 50%" in result

        # Highlights
        assert '"Hello World" from alice@example.com' in result
        assert '"Meeting Notes" from bob@example.com' in result
        assert "Bohemian Rhapsody by Queen" in result
        assert "Stairway to Heaven by Led Zeppelin" in result

    def test_summarize_empty_data_returns_empty_string(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", [], [], None)
        assert result == ""


class TestEventSummarizerHighlights:
    def test_calendar_event_highlight(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 9, 0, 0)
        stats = [{"date": "2024-01-15", "source": "gcal", "event_type": "calendar.event", "count": 1, "first_at": ts, "last_at": ts}]
        events = [_make_event("c1", ts, "gcal", "calendar.event", {"title": "Team Standup"})]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events)
        assert "Team Standup" in result

    def test_browsing_visit_uses_title_then_url(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 9, 0, 0)
        stats = [{"date": "2024-01-15", "source": "browser", "event_type": "browsing.visit", "count": 2, "first_at": ts, "last_at": ts}]
        events = [
            _make_event("b1", ts, "browser", "browsing.visit", {"title": "GitHub", "url": "https://github.com"}),
            _make_event("b2", ts, "browser", "browsing.visit", {"url": "https://example.com"}),
        ]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events)
        assert "GitHub" in result
        assert "https://example.com" in result

    def test_youtube_activity_highlight(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 9, 0, 0)
        stats = [{"date": "2024-01-15", "source": "youtube", "event_type": "media.youtube.activity", "count": 1, "first_at": ts, "last_at": ts}]
        events = [_make_event("y1", ts, "youtube", "media.youtube.activity", {"title": "Python Tutorial"})]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events)
        assert "Python Tutorial" in result

    def test_generic_fallback_highlight(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 9, 0, 0)
        stats = [{"date": "2024-01-15", "source": "custom", "event_type": "custom.thing", "count": 1, "first_at": ts, "last_at": ts}]
        events = [_make_event("x1", ts, "custom", "custom.thing", {"name": "My Custom Thing"})]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events)
        assert "My Custom Thing" in result

    def test_highlights_capped_at_five_per_source(self):
        from pulse.analysis.event_summarizer import EventSummarizer

        ts = datetime(2024, 1, 15, 9, 0, 0)
        stats = [{"date": "2024-01-15", "source": "gmail", "event_type": "email.received", "count": 7, "first_at": ts, "last_at": ts}]
        events = [
            _make_event(f"e{i}", ts, "gmail", "email.received", {"subject": f"Email {i}", "from": f"user{i}@example.com"})
            for i in range(7)
        ]

        summarizer = EventSummarizer()
        result = summarizer.summarize("2024-01-15", stats, events)

        # Exactly 5 highlights; subjects Email 0..4 present, Email 5 and 6 not
        highlight_count = result.count('" from ')
        assert highlight_count == 5

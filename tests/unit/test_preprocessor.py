# tests/unit/test_preprocessor.py
from datetime import UTC, datetime

from pulse.domain.events import Event


def _browsing_event(id, ts, url, title):
    return Event(
        id=id,
        timestamp=ts,
        source="browser",
        event_type="browsing.visit",
        data={"url": url, "title": title, "browser": "firefox"},
    )


def test_browsing_clusters_group_by_domain():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _browsing_event("b1", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://docs.rs/tokio/latest", "tokio - Rust"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 10, tzinfo=UTC),
                        "https://docs.rs/tokio/latest/tokio/net", "tokio::net - Rust"),
        _browsing_event("b3", datetime(2026, 3, 26, 14, 20, tzinfo=UTC),
                        "https://docs.rs/async-std/latest", "async-std - Rust"),
        _browsing_event("b4", datetime(2026, 3, 26, 15, 30, tzinfo=UTC),
                        "https://news.ycombinator.com", "Hacker News"),
        _browsing_event("b5", datetime(2026, 3, 26, 15, 35, tzinfo=UTC),
                        "https://news.ycombinator.com/item?id=123", "Show HN: something"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    # Should have browsing clusters grouped by domain
    assert len(result.browsing_clusters) >= 2
    domains = [c.domain for c in result.browsing_clusters]
    assert "docs.rs" in domains
    assert "news.ycombinator.com" in domains

    # docs.rs cluster should have 3 visits
    docs_cluster = next(c for c in result.browsing_clusters if c.domain == "docs.rs")
    assert docs_cluster.visit_count == 3
    assert docs_cluster.estimated_minutes > 0


def test_browsing_clusters_deduplicate_same_url():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _browsing_event("b1", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://example.com/page", "Page"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 5, tzinfo=UTC),
                        "https://example.com/page", "Page"),
        _browsing_event("b3", datetime(2026, 3, 26, 14, 10, tzinfo=UTC),
                        "https://example.com/other", "Other"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    cluster = next(c for c in result.browsing_clusters if c.domain == "example.com")
    assert cluster.visit_count == 2  # deduped: 2 unique URLs
    assert len(cluster.titles) == 2


def _email_event(id, ts, subject, sender):
    return Event(
        id=id,
        timestamp=ts,
        source="gmail",
        event_type="email.received",
        data={"subject": subject, "from": sender},
    )


def test_email_threads_group_by_subject():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _email_event("e1", datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
                      "Q2 Roadmap", "alice@co.com"),
        _email_event("e2", datetime(2026, 3, 26, 9, 30, tzinfo=UTC),
                      "Re: Q2 Roadmap", "bob@co.com"),
        _email_event("e3", datetime(2026, 3, 26, 10, 0, tzinfo=UTC),
                      "Re: Re: Q2 Roadmap", "alice@co.com"),
        _email_event("e4", datetime(2026, 3, 26, 11, 0, tzinfo=UTC),
                      "Lunch?", "carol@co.com"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    assert len(result.email_threads) == 2
    roadmap = next(t for t in result.email_threads if t.subject == "Q2 Roadmap")
    assert roadmap.message_count == 3
    assert roadmap.is_active is True
    assert "alice@co.com" in roadmap.senders
    assert "bob@co.com" in roadmap.senders

    lunch = next(t for t in result.email_threads if t.subject == "Lunch?")
    assert lunch.message_count == 1
    assert lunch.is_active is False


def test_calendar_blocks_detect_back_to_back():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        Event(id="c1", timestamp=datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "Standup"}),
        Event(id="c2", timestamp=datetime(2026, 3, 26, 9, 15, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "Design Review"}),
        Event(id="c3", timestamp=datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "1:1"}),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    assert len(result.calendar_blocks) == 3
    assert result.calendar_blocks[0].back_to_back is True  # Standup -> Design Review
    assert result.calendar_blocks[1].back_to_back is False  # gap to 1:1
    assert result.calendar_blocks[2].back_to_back is False  # last event


def test_time_blocks_group_by_2h_windows():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _email_event("e1", datetime(2026, 3, 26, 9, 0, tzinfo=UTC), "A", "a@co.com"),
        _email_event("e2", datetime(2026, 3, 26, 9, 30, tzinfo=UTC), "B", "b@co.com"),
        _browsing_event("b1", datetime(2026, 3, 26, 9, 15, tzinfo=UTC),
                        "https://example.com", "Example"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://example.com", "Example"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    # Block 4 = 08:00-10:00 should have gmail:2, browser:1
    block_4 = next(b for b in result.time_blocks if b.block == 4)
    assert block_4.sources["gmail"] == 2
    assert block_4.sources["browser"] == 1

    # Block 7 = 14:00-16:00 should have browser:1
    block_7 = next(b for b in result.time_blocks if b.block == 7)
    assert block_7.sources["browser"] == 1

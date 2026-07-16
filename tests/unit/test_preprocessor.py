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


def test_browsing_time_does_not_inflate_for_spread_out_revisits():
    """Isolated revisits across the day (big gaps) must not count as continuous on-site time.
    Regression: the old heuristic summed inter-visit gaps (cap 30min), so 20 spread-out
    Google visits reported ~220min. Sessionization should keep this small."""
    from datetime import UTC, datetime

    from pulse.analysis.preprocessor import EventPreprocessor
    from pulse.domain.events import Event

    # 12 visits to one domain, each ~1 hour apart (clearly separate quick lookups)
    events = [
        Event(
            id=f"browser:{i}",
            timestamp=datetime(2026, 7, 15, 8 + i, 0, tzinfo=UTC),
            source="browser",
            event_type="browsing.visit",
            data={"url": f"https://www.google.com/search?q=q{i}", "title": f"q{i}"},
        )
        for i in range(12)
    ]
    pp = EventPreprocessor().preprocess(events)
    cluster = next(c for c in pp.browsing_clusters if c.domain == "www.google.com")
    assert cluster.visit_count == 12
    # 12 isolated lookups should read as a handful of minutes, not hours.
    assert cluster.estimated_minutes <= 30


def test_browsing_time_counts_continuous_session():
    """Rapid consecutive visits (small gaps) are continuous browsing and should sum."""
    from datetime import UTC, datetime

    from pulse.analysis.preprocessor import EventPreprocessor
    from pulse.domain.events import Event

    events = [
        Event(
            id=f"browser:{i}",
            timestamp=datetime(2026, 7, 15, 9, i * 2, tzinfo=UTC),  # every 2 min
            source="browser",
            event_type="browsing.visit",
            data={"url": f"https://docs.site.com/page{i}", "title": f"p{i}"},
        )
        for i in range(6)
    ]
    pp = EventPreprocessor().preprocess(events)
    cluster = next(c for c in pp.browsing_clusters if c.domain == "docs.site.com")
    # 5 gaps of 2 min each = ~10 min of continuous reading.
    assert 8 <= cluster.estimated_minutes <= 14


def test_email_threads_flag_promotional_by_category_and_sort_signal_first():
    from datetime import UTC, datetime

    from pulse.analysis.preprocessor import EventPreprocessor
    from pulse.domain.events import Event

    def _email(i, subject, sender, category=None):
        data = {"subject": subject, "sender": sender}
        if category is not None:
            data["category"] = category
        return Event(
            id=f"gmail:{i}",
            timestamp=datetime(2026, 7, 15, 9, i, tzinfo=UTC),
            source="gmail",
            event_type="email.received",
            data=data,
        )

    events = [
        _email(1, "70% off sale", "deals@shop.com", category="promotions"),
        _email(2, "Re: project sync", "colleague@work.com", category="primary"),
        # no category → sender-heuristic fallback should flag this bulk one
        _email(3, "Your receipt", "noreply@service.com"),
    ]
    pp = EventPreprocessor().preprocess(events)
    by_subject = {t.subject: t for t in pp.email_threads}
    assert by_subject["70% off sale"].is_promotional is True
    assert by_subject["project sync"].is_promotional is False
    assert by_subject["Your receipt"].is_promotional is True  # fallback heuristic
    # real correspondence sorts ahead of promotional
    assert pp.email_threads[0].is_promotional is False

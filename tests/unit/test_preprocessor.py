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

from datetime import UTC, datetime

from pulse.domain.events import Event
from pulse.store.normalizer import EventNormalizer, clean_url


def test_clean_url_strips_tracking_params_keeps_real_ones():
    url = "https://example.com/article?id=42&utm_source=news&utm_medium=email&fbclid=abc&gclid=xyz"
    assert clean_url(url) == "https://example.com/article?id=42"


def test_clean_url_leaves_clean_url_untouched():
    url = "https://example.com/path?page=2&q=hello"
    assert clean_url(url) == url


def test_clean_url_handles_no_query_and_non_urls():
    assert clean_url("https://example.com/x") == "https://example.com/x"
    assert (
        clean_url("not a url, just text with utm_source in it")
        == "not a url, just text with utm_source in it"
    )


def test_normalize_cleans_url_in_event_data_recursively():
    ev = Event(
        id="browser:1",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        source="browser",
        event_type="browsing.visit",
        data={
            "url": "https://shop.com/p?item=9&utm_campaign=sale",
            "title": "A page",
            "related": ["https://x.com/a?fbclid=zzz"],
        },
    )
    out = EventNormalizer().normalize(ev)
    assert out.data["url"] == "https://shop.com/p?item=9"
    assert out.data["related"] == ["https://x.com/a"]
    assert out.data["title"] == "A page"
    # identity fields preserved
    assert (out.id, out.source, out.event_type, out.timestamp) == (
        ev.id,
        ev.source,
        ev.event_type,
        ev.timestamp,
    )


def test_normalize_strips_zero_width_chars():
    ev = Event(
        id="x:1",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        source="gmail",
        event_type="email.received",
        data={"subject": "Invoice​ due", "sender": "a@b.com"},
    )
    out = EventNormalizer().normalize(ev)
    assert out.data["subject"] == "Invoice due"


def test_normalize_is_noop_for_already_clean_data():
    data = {"subject": "Lunch", "sender": "friend@example.com"}
    ev = Event(
        id="x:2",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        source="gmail",
        event_type="email.received",
        data=dict(data),
    )
    out = EventNormalizer().normalize(ev)
    assert out.data == data

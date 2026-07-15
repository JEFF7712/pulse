from datetime import UTC, datetime
from pulse.domain.events import Event
from pulse.semantic.embedder import event_text, FakeEmbedder


def _ev(**kw):
    base = dict(
        id="x",
        timestamp=datetime(2026, 7, 14, tzinfo=UTC),
        source="gmail",
        event_type="email.received",
        data={},
        metadata={},
    )
    base.update(kw)
    return Event(**base)


def test_event_text_joins_stringy_data_values():
    ev = _ev(data={"subject": "Invoice due", "sender": "a@b.com", "count": 3})
    txt = event_text(ev)
    assert "Invoice due" in txt and "a@b.com" in txt
    assert "gmail" in txt  # source included for context


def test_fake_embedder_is_deterministic_and_fixed_dim():
    emb = FakeEmbedder(dim=16)
    a = emb.embed(["hello world", "hello world"])
    b = emb.embed(["hello world"])
    assert len(a) == 2 and len(a[0]) == 16
    assert a[0] == a[1] == b[0]  # deterministic


def test_fake_embedder_differs_for_different_text():
    emb = FakeEmbedder(dim=16)
    v1, v2 = emb.embed(["cat"])[0], emb.embed(["dog"])[0]
    assert v1 != v2

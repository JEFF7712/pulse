from datetime import UTC, date, datetime, timedelta

from pulse.analysis.longitudinal import (
    attention_profile,
    build_longitudinal_profile,
    dormant_entities,
    entity_trends,
    sleep_phases,
)
from pulse.domain.events import Event


def _visit(i, domain, when):
    return Event(
        id=f"browser:{domain}:{i}",
        timestamp=when,
        source="browser",
        event_type="browsing.visit",
        data={"url": f"https://{domain}/p{i}", "title": "page"},
    )


def _month_events(domain, year, month, n, start_id=0):
    base = datetime(year, month, 2, 12, tzinfo=UTC)
    return [
        _visit(start_id + i, domain, base + timedelta(minutes=i * 7)) for i in range(n)
    ]


def _filler(year, month, n, start_id=0):
    """Background volume so monthly shares have a denominator."""
    return _month_events("filler.com", year, month, n, start_id=start_id)


# ----------------------------------------------------------------------
# composition drift
# ----------------------------------------------------------------------


def test_shares_are_normalised_so_volume_changes_are_not_trends():
    """A domain holding a constant share while total volume collapses is steady, not
    declining. Un-normalised counts would call it a collapse."""
    events = []
    for i, (month, total) in enumerate([(1, 1000), (2, 1000), (3, 400), (4, 200)]):
        events += _month_events(
            "steady.com", 2026, month, total // 10, start_id=i * 5000
        )
        events += _filler(2026, month, total - total // 10, start_id=i * 5000 + 2000)

    trends = {t.key: t for t in entity_trends(events)}
    assert "steady.com" not in trends  # steady entities are dropped, not reported


def test_collapse_needs_a_meaningful_peak():
    """Everything peaks and most things decay; a 0.5%-share blip dying is not a finding."""
    events = []
    for i, month in enumerate([1, 2, 3, 4, 5, 6]):
        n = 5 if month <= 2 else 0
        if n:
            events += _month_events("tiny.com", 2026, month, n, start_id=i * 5000)
        events += _filler(2026, month, 1000, start_id=i * 5000 + 100)

    keys = {t.key for t in entity_trends(events, min_entity_events=5)}
    assert "tiny.com" not in keys


def test_a_real_collapse_is_reported():
    events = []
    for i, month in enumerate([1, 2, 3, 4, 5, 6]):
        n = 400 if month <= 2 else 5
        events += _month_events("textbooks.com", 2026, month, n, start_id=i * 9000)
        events += _filler(2026, month, 1000, start_id=i * 9000 + 3000)

    trends = {t.key: t for t in entity_trends(events)}
    assert trends["textbooks.com"].classification == "collapsed"
    assert trends["textbooks.com"].fraction_of_peak < 0.25


def test_something_below_its_peak_is_never_called_rising():
    """The original classifier compared against the first months of the whole window,
    so anything absent back then read as rising even at a third of its peak."""
    plan = [(1, 20), (2, 60), (3, 600), (4, 500), (5, 260), (6, 240)]
    events = []
    for i, (month, n) in enumerate(plan):
        events += _month_events("github.com", 2026, month, n, start_id=i * 9000)
        events += _filler(2026, month, 1200, start_id=i * 9000 + 3000)

    trends = {t.key: t for t in entity_trends(events)}
    if "github.com" in trends:
        t = trends["github.com"]
        assert not (t.classification == "rising" and t.fraction_of_peak < 0.8)


def test_sibling_subdomains_are_grouped_into_one_trend():
    """A self-hosted stack going quiet is one fact about the user, not eleven."""
    events = []
    for i, month in enumerate([1, 2, 3, 4, 5, 6]):
        n = 120 if month <= 2 else 1
        for sub in ("argo", "lidarr", "books", "music"):
            events += _month_events(
                f"{sub}.rupan.dev", 2026, month, n, start_id=i * 9000 + hash(sub) % 500
            )
        events += _filler(2026, month, 1500, start_id=i * 9000 + 6000)

    keys = [t.key for t in entity_trends(events)]
    assert keys.count("rupan.dev") == 1
    assert not any(k.endswith(".rupan.dev") for k in keys)


def test_trend_list_is_capped_and_ranked_by_peak_share():
    events = []
    for i, month in enumerate([1, 2, 3, 4, 5, 6]):
        for d in range(30):
            n = (200 if d == 0 else 60) if month <= 2 else 1
            events += _month_events(
                f"site{d}.com", 2026, month, n, start_id=i * 90000 + d * 1000
            )
        events += _filler(2026, month, 1500, start_id=i * 90000 + 60000)

    trends = entity_trends(events)
    assert len(trends) <= 20
    shares = [t.peak_share for t in trends]
    assert shares == sorted(shares, reverse=True)


def test_too_little_history_yields_no_trends():
    events = _month_events("a.com", 2026, 1, 500) + _filler(2026, 1, 1000)
    assert entity_trends(events) == []


# ----------------------------------------------------------------------
# circadian
# ----------------------------------------------------------------------


def test_sleep_phase_recovers_a_known_bedtime_and_wake():
    events = []
    for day in range(40):
        d = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=day)
        # active until 01:30, back at 09:30
        events.append(_visit(day * 4 + 0, "a.com", d.replace(hour=22)))
        events.append(
            _visit(
                day * 4 + 1, "a.com", (d + timedelta(days=1)).replace(hour=1, minute=30)
            )
        )
        events.append(
            _visit(
                day * 4 + 2, "a.com", (d + timedelta(days=1)).replace(hour=9, minute=30)
            )
        )

    phases = sleep_phases(events)
    assert phases
    p = phases[0]
    assert abs(p.bedtime_hour - 1.5) < 0.6
    assert abs(p.wake_hour - 9.5) < 0.6
    assert abs(p.gap_hours - 8.0) < 0.6


def test_implausible_gaps_are_ignored():
    """A three-day trip with no browsing is not a 72-hour sleep."""
    events = [
        _visit(1, "a.com", datetime(2026, 1, 5, 23, tzinfo=UTC)),
        _visit(2, "a.com", datetime(2026, 1, 9, 10, tzinfo=UTC)),
    ]
    assert sleep_phases(events) == []


def test_periods_with_too_few_nights_are_dropped():
    events = []
    for day in range(4):
        d = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(days=day)
        events.append(_visit(day * 2, "a.com", d.replace(hour=23)))
        events.append(
            _visit(day * 2 + 1, "a.com", (d + timedelta(days=1)).replace(hour=9))
        )
    assert sleep_phases(events) == []


# ----------------------------------------------------------------------
# attention
# ----------------------------------------------------------------------


def test_deep_fraction_separates_anchors_from_glances():
    events = []
    # deep.com: one continuous 60-minute session per day
    for day in range(20):
        base = datetime(2026, 3, 2, 14, tzinfo=UTC) + timedelta(days=day)
        for k in range(13):
            events.append(
                _visit(day * 100 + k, "deep.com", base + timedelta(minutes=k * 5))
            )
    # glance.com: many isolated single visits, same total visit count
    for day in range(20):
        base = datetime(2026, 3, 2, 20, tzinfo=UTC) + timedelta(days=day)
        for k in range(13):
            events.append(
                _visit(
                    50000 + day * 100 + k,
                    "glance.com",
                    base + timedelta(hours=k // 2, minutes=(k % 2) * 40),
                )
            )

    profiles = {a.key: a for a in attention_profile(events, min_minutes=1)}
    assert profiles["deep.com"].deep_fraction > 0.8
    assert profiles["glance.com"].deep_fraction < profiles["deep.com"].deep_fraction


# ----------------------------------------------------------------------
# dormancy
# ----------------------------------------------------------------------


def test_dormancy_needs_sustained_use_then_real_silence():
    events = []
    for day in range(80):
        d = datetime(2026, 1, 5, 12, tzinfo=UTC) + timedelta(days=day)
        for k in range(3):
            events.append(
                _visit(day * 10 + k, "abandoned.com", d + timedelta(minutes=k))
            )

    found = {d.key: d for d in dormant_entities(events, as_of=date(2026, 8, 10))}
    assert "abandoned.com" in found
    assert found["abandoned.com"].silent_days > 100

    # still in use → not dormant
    recent = events + [
        _visit(99999, "abandoned.com", datetime(2026, 8, 9, 12, tzinfo=UTC))
    ]
    assert "abandoned.com" not in {
        d.key for d in dormant_entities(recent, as_of=date(2026, 8, 10))
    }


def test_a_brief_flirtation_is_not_dormancy():
    """Two days of use then nothing is not something that 'stopped'."""
    events = [
        _visit(
            i,
            "tried-once.com",
            datetime(2026, 1, 5, 12, tzinfo=UTC) + timedelta(minutes=i),
        )
        for i in range(150)
    ]
    assert dormant_entities(events, as_of=date(2026, 8, 10)) == []


# ----------------------------------------------------------------------
# assembly
# ----------------------------------------------------------------------


def test_empty_store_is_handled():
    p = build_longitudinal_profile([], as_of=date(2026, 8, 10))
    assert p.is_empty()
    assert p.notes


def test_thin_history_reports_a_note_instead_of_trends():
    events = _month_events("a.com", 2026, 8, 300)
    p = build_longitudinal_profile(events, as_of=date(2026, 8, 31))
    assert p.entity_trends == []
    assert any("history" in n for n in p.notes)

from datetime import UTC, date, datetime, timedelta

from pulse.analysis.change_surface import (
    MIN_NEW_ENTITY_COUNT,
    build_change_surface,
    compute_entity_deltas,
    compute_novel_clusters,
)
from pulse.analysis.entities import entity_key
from pulse.domain.events import Event


def _visit(i, domain, when, title="page"):
    return Event(
        id=f"browser:{domain}:{i}",
        timestamp=when,
        source="browser",
        event_type="browsing.visit",
        data={"url": f"https://{domain}/p{i}", "title": title},
    )


def _mail(i, sender, when, subject="hi"):
    return Event(
        id=f"gmail:{i}",
        timestamp=when,
        source="gmail",
        event_type="email.received",
        data={"sender": sender, "subject": subject},
    )


def _push(i, repo, when):
    return Event(
        id=f"github:{i}",
        timestamp=when,
        source="github",
        event_type="dev.push",
        data={"repo": repo, "title": f"Push to main — {repo}"},
    )


def _spread(make, count, start, **kw):
    """Spread `count` events one hour apart from `start`."""
    return [make(i, when=start + timedelta(hours=i), **kw) for i in range(count)]


WINDOW_START = date(2026, 8, 3)
WINDOW_END = date(2026, 8, 9)
BASELINE_START = date(2026, 6, 8)


def _win_dt(day_offset=0, hour=9):
    return datetime(2026, 8, 3, hour, tzinfo=UTC) + timedelta(days=day_offset)


def _base_dt(day_offset=0, hour=9):
    return datetime(2026, 6, 8, hour, tzinfo=UTC) + timedelta(days=day_offset)


# ----------------------------------------------------------------------
# entity keys
# ----------------------------------------------------------------------


def test_entity_key_normalises_hosts_and_addresses():
    assert entity_key(_visit(1, "www.github.com", _win_dt())) == (
        "domain",
        "github.com",
    )
    assert entity_key(_mail(1, "A Colleague <person@work.edu>", _win_dt())) == (
        "sender",
        "person@work.edu",
    )
    # a job-alert blast is bulk, so it never becomes an entity at all
    assert (
        entity_key(
            _mail(2, "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", _win_dt())
        )
        is None
    )
    assert entity_key(_push(1, "JEFF7712/pulse", _win_dt())) == (
        "repo",
        "JEFF7712/pulse",
    )


def test_entity_key_survives_unparseable_urls():
    bad = Event(
        id="browser:bad",
        timestamp=_win_dt(),
        source="browser",
        event_type="browsing.visit",
        data={"url": "http://[oops", "title": "x"},
    )
    assert entity_key(bad) is None


# ----------------------------------------------------------------------
# entity deltas
# ----------------------------------------------------------------------


def test_new_entity_requires_repeat_visits():
    baseline = _spread(_visit, 20, _base_dt(), domain="github.com")
    window_one_off = [_visit(0, "vast.ai", _win_dt())]
    window_repeated = _spread(_visit, MIN_NEW_ENTITY_COUNT, _win_dt(), domain="vast.ai")

    def deltas(window):
        return compute_entity_deltas(
            window, baseline, baseline_days=56, window_days=7, window_end=WINDOW_END
        )

    assert [d.key for d in deltas(window_one_off)] == []
    found = deltas(window_repeated)
    assert [(d.key, d.status) for d in found] == [("vast.ai", "new")]


def test_dormant_entity_returning_is_distinguished_from_new():
    # last seen well beyond the dormancy threshold, then back
    baseline = _spread(_visit, 12, _base_dt(), domain="kaggle.com")
    window = _spread(_visit, 4, _win_dt(), domain="kaggle.com")

    found = compute_entity_deltas(
        window, baseline, baseline_days=56, window_days=7, window_end=WINDOW_END
    )
    by_key = {d.key: d for d in found}
    assert by_key["kaggle.com"].status == "returning"
    assert by_key["kaggle.com"].last_seen_before == "2026-06-08"


def test_ratio_shifts_need_a_real_baseline():
    """A 5x jump off two historical events is arithmetic, not a signal."""
    thin_baseline = _spread(_visit, 2, _base_dt(), domain="rare.com")
    window = _spread(_visit, 10, _win_dt(), domain="rare.com")

    found = compute_entity_deltas(
        window, thin_baseline, baseline_days=56, window_days=7, window_end=WINDOW_END
    )
    assert [d for d in found if d.status in ("spike", "drop")] == []


def test_spike_detected_against_a_solid_baseline():
    # 56 baseline events / 56 days = 1.0/day; 28 window events / 7 days = 4.0/day
    baseline = [_visit(i, "github.com", _base_dt(day_offset=i)) for i in range(56)]
    window = _spread(_visit, 28, _win_dt(), domain="github.com")

    found = compute_entity_deltas(
        window, baseline, baseline_days=56, window_days=7, window_end=WINDOW_END
    )
    spike = next(d for d in found if d.key == "github.com")
    assert spike.status == "spike"
    assert spike.ratio >= 3.0


# ----------------------------------------------------------------------
# embedding novelty
# ----------------------------------------------------------------------


def _vec(*weights):
    """Small explicit vectors so novelty is checkable by hand."""
    return list(weights)


def test_novel_cluster_surfaces_events_far_from_every_centroid():
    baseline = [
        _visit(i, f"routine{i % 8}.com", _base_dt(day_offset=i)) for i in range(24)
    ]
    window = _spread(_visit, 3, _win_dt(), domain="strange.com")

    vectors = {e.id: _vec(1.0, 0.0) for e in baseline}
    # orthogonal to everything in the baseline → novelty 1.0
    vectors.update({e.id: _vec(0.0, 1.0) for e in window})

    clusters = compute_novel_clusters(window, baseline, vectors)
    assert len(clusters) == 1
    assert clusters[0].novelty > 0.9
    assert clusters[0].sources == ["browser"]


def test_familiar_events_produce_no_clusters():
    baseline = [
        _visit(i, f"routine{i % 8}.com", _base_dt(day_offset=i)) for i in range(24)
    ]
    window = _spread(_visit, 3, _win_dt(), domain="routine1.com")
    vectors = {e.id: _vec(1.0, 0.0) for e in baseline + window}

    assert compute_novel_clusters(window, baseline, vectors) == []


def test_novelty_is_skipped_when_history_is_too_thin():
    """A cold store would otherwise mark literally everything as novel."""
    baseline = [_visit(1, "only.com", _base_dt())]
    window = _spread(_visit, 3, _win_dt(), domain="new.com")
    vectors = {e.id: _vec(1.0, 0.0) for e in baseline}
    vectors.update({e.id: _vec(0.0, 1.0) for e in window})

    assert compute_novel_clusters(window, baseline, vectors) == []


def test_single_novel_event_does_not_form_a_cluster():
    baseline = [
        _visit(i, f"routine{i % 8}.com", _base_dt(day_offset=i)) for i in range(24)
    ]
    window = [_visit(0, "oneoff.com", _win_dt())]
    vectors = {e.id: _vec(1.0, 0.0) for e in baseline}
    vectors[window[0].id] = _vec(0.0, 1.0)

    assert compute_novel_clusters(window, baseline, vectors) == []


# ----------------------------------------------------------------------
# assembly
# ----------------------------------------------------------------------


def test_quiet_window_yields_an_empty_surface():
    """The common case: nothing changed, so no agent needs to be woken."""
    baseline = [_visit(i, "github.com", _base_dt(day_offset=i)) for i in range(56)]
    window = _spread(_visit, 5, _win_dt(), domain="github.com")

    surface = build_change_surface(
        window,
        baseline,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        baseline_start=BASELINE_START,
    )
    assert surface.is_empty()
    assert surface.signal_count() == 0


def test_surface_without_baseline_reports_a_note_not_findings():
    window = _spread(_visit, 5, _win_dt(), domain="anything.com")
    surface = build_change_surface(
        window,
        [],
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        baseline_start=BASELINE_START,
    )
    assert surface.is_empty()
    assert any("baseline" in note for note in surface.notes)


def test_surface_notes_missing_embeddings():
    baseline = [_visit(i, "github.com", _base_dt(day_offset=i)) for i in range(56)]
    window = _spread(_visit, 5, _win_dt(), domain="github.com")
    surface = build_change_surface(
        window,
        baseline,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        baseline_start=BASELINE_START,
    )
    assert any("embeddings" in note for note in surface.notes)


# ----------------------------------------------------------------------
# domain rollup
# ----------------------------------------------------------------------


def test_subdomains_collapse_to_one_entity():
    """auth.parchment.com and parchment.com are one site to the user; keeping them
    apart triples the delta list and stops related events from clustering."""
    from pulse.analysis.entities import registrable_domain

    assert registrable_domain("auth.parchment.com") == "parchment.com"
    assert registrable_domain("registration.parchment.com") == "parchment.com"
    assert registrable_domain("marketplace.nvidia.com") == "nvidia.com"
    assert registrable_domain("nvidia.com") == "nvidia.com"
    # two-label public suffixes keep the extra label
    assert registrable_domain("www.bbc.co.uk") == "bbc.co.uk"
    assert registrable_domain("shop.example.com.au") == "example.com.au"


def test_rolled_up_subdomains_aggregate_into_a_single_delta():
    baseline = [_visit(i, "github.com", _base_dt(day_offset=i)) for i in range(56)]
    window = [
        _visit(1, "parchment.com", _win_dt()),
        _visit(2, "auth.parchment.com", _win_dt()),
        _visit(3, "registration.parchment.com", _win_dt()),
    ]
    found = compute_entity_deltas(
        window, baseline, baseline_days=56, window_days=7, window_end=WINDOW_END
    )
    parchment = [d for d in found if d.key == "parchment.com"]
    assert len(parchment) == 1
    assert parchment[0].count == 3
    assert parchment[0].status == "new"


def test_bare_hosts_are_preserved():
    from pulse.analysis.entities import entity_key

    event = _visit(1, "localhost", _win_dt())
    assert entity_key(event) == ("domain", "localhost")


# ----------------------------------------------------------------------
# bulk mail exclusion
# ----------------------------------------------------------------------


def test_bulk_senders_never_become_entities():
    """A retailer mailing twice as often is not a change in the user's life."""
    from pulse.analysis.entities import entity_key

    blast = Event(
        id="gmail:blast",
        timestamp=_win_dt(),
        source="gmail",
        event_type="email.received",
        data={
            "sender": "Bose <email@email.bose.com>",
            "subject": "Deals up to 35% off!",
            "category": "promotions",
        },
    )
    real = Event(
        id="gmail:real",
        timestamp=_win_dt(),
        source="gmail",
        event_type="email.received",
        data={
            "sender": "AssociatedBank@onlinebanking.associatedbank.com",
            "subject": "Confirmed: contact info changed",
            "category": "updates",
        },
    )
    assert entity_key(blast) is None
    assert entity_key(real) == (
        "sender",
        "associatedbank@onlinebanking.associatedbank.com",
    )


def test_bulk_mail_is_excluded_from_novelty_scoring():
    """Newsletters are textually unique by construction and would otherwise top
    every novelty ranking while saying nothing about the user."""
    baseline = [
        _visit(i, f"routine{i % 8}.com", _base_dt(day_offset=i)) for i in range(24)
    ]
    newsletters = [
        Event(
            id=f"gmail:news{i}",
            timestamp=_win_dt(day_offset=i),
            source="gmail",
            event_type="email.received",
            data={
                "sender": "news@newsletter.example.com",
                "subject": f"Issue #{i}",
                "category": "promotions",
            },
        )
        for i in range(4)
    ]
    vectors = {e.id: _vec(1.0, 0.0) for e in baseline}
    vectors.update({e.id: _vec(0.0, 1.0) for e in newsletters})

    assert compute_novel_clusters(newsletters, baseline, vectors) == []

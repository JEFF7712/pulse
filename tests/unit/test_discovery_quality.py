from pulse.analysis.discovery import _evidence_days, _is_significant_new_pattern
from pulse.analysis.prompts import NewPattern


def test_evidence_days_extracts_distinct_iso_days() -> None:
    days = _evidence_days(
        [
            "2026-04-15: first item",
            "2026-04-15: duplicate day",
            "context without date",
            "2026-04-16: second item",
        ]
    )

    assert days == {"2026-04-15", "2026-04-16"}


def test_significant_new_pattern_accepts_multi_day_pattern() -> None:
    pattern = NewPattern(
        title="Strong pattern",
        observation="Something meaningful.",
        confidence=0.7,
        evidence=[
            "2026-04-14: first day",
            "2026-04-15: second day",
        ],
        trend="new",
    )

    assert _is_significant_new_pattern(pattern) is True


def test_significant_new_pattern_accepts_high_confidence_single_day_cross_source_cluster() -> None:
    pattern = NewPattern(
        title="Strong single-day cluster",
        observation="Cross-source convergence in one window.",
        confidence=0.82,
        evidence=[
            "2026-04-15: source one",
            "2026-04-15: source two",
            "2026-04-15: source three",
            "2026-04-15: source four",
        ],
        trend="new",
    )

    assert _is_significant_new_pattern(pattern) is True


def test_significant_new_pattern_rejects_low_confidence_single_day_novelty() -> None:
    pattern = NewPattern(
        title="Weak novelty",
        observation="Interesting but thin.",
        confidence=0.58,
        evidence=[
            "2026-04-15: one domain appeared",
            "2026-04-15: contextual speculation",
            "2026-04-15: another same-day supporting point",
            "2026-04-15: baseline comparison",
        ],
        trend="new",
    )

    assert _is_significant_new_pattern(pattern) is False


def test_significant_new_pattern_rejects_sparse_evidence_even_with_ok_confidence() -> None:
    pattern = NewPattern(
        title="Too sparse",
        observation="Not enough support.",
        confidence=0.72,
        evidence=["2026-04-15: one item"],
        trend="new",
    )

    assert _is_significant_new_pattern(pattern) is False

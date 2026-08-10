from pulse.analysis.pattern_gate import (
    diff_patterns,
    find_duplicate,
    is_restatement,
    parse_pattern,
    snapshot_patterns,
)

PATTERN = """---
pulse: true
type: pattern
slug: transcript-transfer
---

# Pattern: Credit Transfer Underway

**Status:** active
**Confidence:** 0.6
**First seen:** 2026-08-09
**Last updated:** 2026-08-09

## Observation
Parchment transcript ordering and Moraine Valley self-service appeared together.

## Evidence Log
- 38 visits to parchment.com including payment.parchment.com
- 9 visits to self-serv.morainevalley.edu

## Trend
stable

## User Notes
_None yet._
"""


def _with(content, old, new):
    assert old in content
    return content.replace(old, new)


def test_parse_pattern_extracts_the_meaningful_parts():
    snap = parse_pattern("transcript-transfer", PATTERN)
    assert snap.title == "Credit Transfer Underway"
    assert snap.status == "active"
    assert "Parchment transcript ordering" in snap.observation
    assert len(snap.evidence) == 2


def test_last_updated_alone_is_not_a_change():
    """It moves every run by definition; counting it would mark everything changed."""
    before = snapshot_patterns([{"slug": "p", "content": PATTERN}])
    touched = _with(
        PATTERN, "**Last updated:** 2026-08-09", "**Last updated:** 2026-08-16"
    )
    after = snapshot_patterns([{"slug": "p", "content": touched}])

    assert diff_patterns(before, after).is_empty()


def test_new_evidence_counts_as_an_update():
    before = snapshot_patterns([{"slug": "p", "content": PATTERN}])
    grown = _with(
        PATTERN,
        "- 9 visits to self-serv.morainevalley.edu",
        "- 9 visits to self-serv.morainevalley.edu\n- registrar.wisc.edu returned after 6 weeks",
    )
    after = snapshot_patterns([{"slug": "p", "content": grown}])

    changes = diff_patterns(before, after)
    assert changes.updated == ["p"]
    assert changes.created == []


def test_a_brand_new_pattern_is_reported_as_created():
    before = {}
    after = snapshot_patterns([{"slug": "p", "content": PATTERN}])
    changes = diff_patterns(before, after)
    assert changes.created == ["p"]
    assert changes.updated == []


def test_status_change_counts_as_an_update():
    before = snapshot_patterns([{"slug": "p", "content": PATTERN}])
    closed = _with(PATTERN, "**Status:** active", "**Status:** inactive")
    after = snapshot_patterns([{"slug": "p", "content": closed}])
    assert diff_patterns(before, after).updated == ["p"]


# ----------------------------------------------------------------------
# duplicate / restatement guards
# ----------------------------------------------------------------------


def test_near_identical_proposal_is_flagged_as_duplicate():
    existing = snapshot_patterns([{"slug": "transcript-transfer", "content": PATTERN}])
    hit = find_duplicate(
        "Credit Transfer Underway",
        "Parchment transcript ordering and Moraine Valley self-service appeared together.",
        existing,
    )
    assert hit is not None
    assert hit[0] == "transcript-transfer"


def test_a_genuinely_different_finding_is_not_a_duplicate():
    existing = snapshot_patterns([{"slug": "transcript-transfer", "content": PATTERN}])
    assert (
        find_duplicate(
            "GPU Hardware Research",
            "Repeated visits to NVIDIA RTX PRO 6000 Blackwell workstation pages.",
            existing,
        )
        is None
    )


def test_restatement_of_the_previous_observation_is_rejected():
    """The exact failure that filled real vault files: the same claim re-appended
    with a slightly different number on every run."""
    previous = "Browsing fully normalized at 682 visits, effectively at baseline."
    repeat = "Browsing fully normalized at 682 visits, effectively at baseline."
    assert is_restatement(repeat, previous) is True


def test_a_substantively_new_observation_is_allowed():
    previous = "Browsing fully normalized at 682 visits, effectively at baseline."
    fresh = (
        "Parchment payment pages appeared for the first time, alongside UW registrar "
        "and Moraine Valley enrolment, indicating a credit transfer in progress."
    )
    assert is_restatement(fresh, previous) is False


def test_empty_previous_observation_is_never_a_restatement():
    assert is_restatement("anything at all", "") is False


def test_similarity_uses_the_embedder_when_present():
    class StubEmbedder:
        def embed(self, texts):
            # orthogonal vectors → similarity 0, overriding high lexical overlap
            return [[1.0, 0.0], [0.0, 1.0]]

    text = "the same words in both strings entirely"
    assert is_restatement(text, text) is True  # lexical path
    assert is_restatement(text, text, embedder=StubEmbedder()) is False


def test_gate_degrades_when_the_embedder_raises():
    class BrokenEmbedder:
        def embed(self, texts):
            raise RuntimeError("model unavailable")

    text = "identical text on both sides of the comparison"
    assert is_restatement(text, text, embedder=BrokenEmbedder()) is True


def test_a_closed_pattern_does_not_block_a_new_finding():
    """A behaviour that stopped and came back is news. A months-old inactive pattern
    must never gag the agent about the present."""
    closed = PATTERN.replace("**Status:** active", "**Status:** inactive")
    existing = snapshot_patterns([{"slug": "transcript-transfer", "content": closed}])

    assert (
        find_duplicate(
            "Credit Transfer Underway",
            "Parchment transcript ordering and Moraine Valley self-service appeared together.",
            existing,
        )
        is None
    )


def test_an_invalidated_pattern_also_does_not_block():
    closed = PATTERN.replace("**Status:** active", "**Status:** invalidated")
    existing = snapshot_patterns([{"slug": "transcript-transfer", "content": closed}])
    assert (
        find_duplicate(
            "Credit Transfer Underway",
            "Parchment transcript ordering and Moraine Valley self-service appeared together.",
            existing,
        )
        is None
    )


def test_a_weakening_pattern_still_blocks():
    """Weakening means still happening, so re-reporting it is still a duplicate."""
    weak = PATTERN.replace("**Status:** active", "**Status:** weakening")
    existing = snapshot_patterns([{"slug": "transcript-transfer", "content": weak}])
    hit = find_duplicate(
        "Credit Transfer Underway",
        "Parchment transcript ordering and Moraine Valley self-service appeared together.",
        existing,
    )
    assert hit is not None

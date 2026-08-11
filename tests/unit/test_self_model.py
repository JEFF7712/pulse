from datetime import date

from pulse.analysis.self_model import (
    assess_profile,
    parse_last_confirmed,
    stamp_last_confirmed,
)

PROFILE = """# User Profile

**Name:** Someone

**Current Projects:** A, B, C
"""


def test_missing_profile_says_so_rather_than_inviting_inference():
    f = assess_profile("", as_of=date(2026, 8, 10))
    assert f.exists is False
    assert f.staleness == "missing"
    assert "Do not infer" in f.guidance


def test_fresh_profile_can_be_read_as_a_current_claim():
    content = stamp_last_confirmed(PROFILE, "2026-08-01")
    f = assess_profile(content, as_of=date(2026, 8, 10))
    assert f.staleness == "fresh"
    assert f.age_days == 9


def test_stale_profile_flags_the_ambiguity():
    """A divergence from a four-month-old profile has two readings; the agent has to
    be told that, or it asserts a self-narrative gap it has not earned."""
    content = stamp_last_confirmed(PROFILE, "2026-04-08")
    f = assess_profile(content, as_of=date(2026, 8, 10))
    assert f.staleness == "stale"
    assert f.age_days == 124
    assert "two readings" in f.guidance


def test_very_stale_profile_is_not_evidence_at_all():
    content = stamp_last_confirmed(PROFILE, "2025-08-01")
    f = assess_profile(content, as_of=date(2026, 8, 10))
    assert f.staleness == "very_stale"
    assert "NOT a finding" in f.guidance


def test_undated_profile_falls_back_to_file_mtime():
    """Every profile written before the marker existed has no date in it."""
    f = assess_profile(PROFILE, as_of=date(2026, 8, 10), file_mtime=date(2026, 4, 8))
    assert f.last_confirmed == "2026-04-08"
    assert f.staleness == "stale"


def test_undated_profile_with_no_mtime_is_unknown_not_fresh():
    f = assess_profile(PROFILE, as_of=date(2026, 8, 10))
    assert f.staleness == "unknown"
    assert "possibly out of date" in f.guidance


# ----------------------------------------------------------------------
# stamping
# ----------------------------------------------------------------------


def test_stamp_inserts_under_the_heading_and_preserves_everything_else():
    out = stamp_last_confirmed(PROFILE, "2026-08-10")
    lines = out.splitlines()
    assert lines[0] == "# User Profile"
    assert "**Last confirmed:** 2026-08-10" in out
    assert "**Current Projects:** A, B, C" in out
    assert "**Name:** Someone" in out


def test_stamp_replaces_an_existing_marker_without_duplicating():
    once = stamp_last_confirmed(PROFILE, "2026-04-08")
    twice = stamp_last_confirmed(once, "2026-08-10")
    assert twice.count("**Last confirmed:**") == 1
    assert parse_last_confirmed(twice) == "2026-08-10"


def test_stamp_handles_a_profile_with_no_heading():
    out = stamp_last_confirmed("just some free text about me", "2026-08-10")
    assert "**Last confirmed:** 2026-08-10" in out
    assert "just some free text about me" in out

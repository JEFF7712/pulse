"""Tests for VaultMemory — read/write pattern and life knowledge files."""

from pathlib import Path

import pytest

from pulse.analysis.vault_memory import VaultMemory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory(tmp_path: Path) -> VaultMemory:
    return VaultMemory(tmp_path)


def _write_sample_pattern(mem: VaultMemory, slug: str = "late-night-coding") -> Path:
    return mem.write_pattern(
        slug=slug,
        title="Late-night coding sessions",
        status="active",
        confidence=0.82,
        first_seen="2026-01-10",
        last_updated="2026-03-20",
        observation="You consistently start deep work after 22:00.",
        evidence_log=[
            "2026-01-10: 3 h session after 22:00",
            "2026-02-14: 2.5 h session after 23:00",
        ],
        trend="Strengthening — frequency up 20 % in last 30 days.",
    )


# ---------------------------------------------------------------------------
# 1. write_pattern
# ---------------------------------------------------------------------------


def test_write_pattern_creates_markdown_file(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    assert path.exists(), "Pattern file was not created"
    assert path.suffix == ".md"
    assert path.stem == "late-night-coding"

    content = path.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "pulse: true" in content
    assert "type: pattern" in content
    assert "slug: late-night-coding" in content
    assert "tags: [pulse, pulse/pattern]" in content

    # Header
    assert "# Pattern: Late-night coding sessions" in content

    # Metadata fields
    assert "**Status:** active" in content
    assert "**Confidence:** 0.82" in content
    assert "**First seen:** 2026-01-10" in content
    assert "**Last updated:** 2026-03-20" in content

    # Sections
    assert "## Observation" in content
    assert "You consistently start deep work after 22:00." in content

    assert "## Evidence Log" in content
    assert "- 2026-01-10: 3 h session after 22:00" in content
    assert "- 2026-02-14: 2.5 h session after 23:00" in content

    assert "## Trend" in content
    assert "Strengthening" in content

    assert "## Related days" in content
    assert "[[01-Daily/2026-01-10]]" in content
    assert "[[01-Daily/2026-02-14]]" in content
    assert "[[01-Daily/2026-03-20]]" in content

    assert "## User Notes" in content
    assert "_None yet._" in content
    assert "#pulse #pulse/pattern" in content


def test_write_pattern_with_user_notes(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = mem.write_pattern(
        slug="focus-blocks",
        title="Focus blocks",
        status="active",
        confidence=0.9,
        first_seen="2026-02-01",
        last_updated="2026-03-01",
        observation="Long focus blocks on weekday mornings.",
        evidence_log=["2026-02-01: 4 h block"],
        trend="Stable.",
        user_notes="I know — I protect these intentionally.",
    )
    content = path.read_text(encoding="utf-8")
    assert "I know — I protect these intentionally." in content
    assert "_None yet._" not in content


# ---------------------------------------------------------------------------
# 2. read_patterns
# ---------------------------------------------------------------------------


def test_read_patterns_returns_all_active_patterns(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    _write_sample_pattern(mem, slug="pattern-a")
    _write_sample_pattern(mem, slug="pattern-b")

    patterns = mem.read_patterns()

    assert len(patterns) == 2
    slugs = {p["slug"] for p in patterns}
    assert slugs == {"pattern-a", "pattern-b"}

    for p in patterns:
        assert "content" in p
        assert "# Pattern:" in p["content"]


def test_read_patterns_returns_empty_list_when_directory_missing(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    # No patterns directory created yet
    result = mem.read_patterns()
    assert result == []


# ---------------------------------------------------------------------------
# 3. update_pattern — preserves user notes
# ---------------------------------------------------------------------------


def test_update_pattern_preserves_user_notes(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    # Simulate the user editing the notes section in the file directly
    original = path.read_text(encoding="utf-8")
    edited = original.replace("_None yet._", "This is my personal annotation.")
    path.write_text(edited, encoding="utf-8")

    # Now update — should preserve the hand-edited notes
    mem.update_pattern(
        slug="late-night-coding",
        title="Late-night coding sessions",
        status="confirmed",
        confidence=0.95,
        first_seen="2026-01-10",
        last_updated="2026-03-26",
        observation="You consistently start deep work after 22:00.",
        evidence_log=[
            "2026-01-10: 3 h session after 22:00",
            "2026-03-26: new evidence",
        ],
        trend="Stable.",
    )

    updated = path.read_text(encoding="utf-8")
    assert "This is my personal annotation." in updated
    assert "**Status:** confirmed" in updated
    assert "**Confidence:** 0.95" in updated
    assert "2026-03-26: new evidence" in updated


def test_update_pattern_does_not_preserve_default_notes(tmp_path: Path) -> None:
    """When notes are still the default placeholder, update should leave them as default."""
    mem = _make_memory(tmp_path)
    _write_sample_pattern(mem)

    mem.update_pattern(
        slug="late-night-coding",
        title="Late-night coding sessions",
        status="active",
        confidence=0.9,
        first_seen="2026-01-10",
        last_updated="2026-03-26",
        observation="Updated observation.",
        evidence_log=["2026-03-26: fresh entry"],
        trend="Up.",
    )

    path = tmp_path / "02-Insights" / "patterns" / "late-night-coding.md"
    content = path.read_text(encoding="utf-8")
    assert "_None yet._" in content


# ---------------------------------------------------------------------------
# 4. read_life_file
# ---------------------------------------------------------------------------


def test_read_life_file_returns_content_or_empty(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    # Non-existent file returns empty string
    result = mem.read_life_file("does-not-exist.md")
    assert result == ""

    # Write and read back
    life_dir = tmp_path / "03-Life"
    life_dir.mkdir(parents=True, exist_ok=True)
    (life_dir / "goals.md").write_text("# My Goals\n- Sleep more.", encoding="utf-8")

    result = mem.read_life_file("goals.md")
    assert "# My Goals" in result
    assert "Sleep more." in result


# ---------------------------------------------------------------------------
# 5. write_life_file
# ---------------------------------------------------------------------------


def test_write_life_file(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    content = "# Routines\n- Morning walk at 07:00."
    path = mem.write_life_file("routines.md", content)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == content
    assert path.parent == tmp_path / "03-Life"


def test_append_daily_correction_creates_reserved_section_and_preserves_digest(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    digest_path = tmp_path / "01-Daily" / "2026-03-27.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        "# 2026-03-27\n\n## Timeline\nWorked late.\n",
        encoding="utf-8",
    )

    path = mem.append_daily_correction(
        "2026-03-27", "Actually dinner was with Sam, not Alex."
    )

    assert path == digest_path
    content = digest_path.read_text(encoding="utf-8")
    assert "## Timeline\nWorked late." in content
    assert "## Corrections" in content
    assert "Actually dinner was with Sam, not Alex." in content


def test_append_daily_correction_appends_to_existing_reserved_section(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    digest_path = tmp_path / "01-Daily" / "2026-03-27.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        "# 2026-03-27\n\n## Timeline\nWorked late.\n\n## Corrections\n- First correction.\n",
        encoding="utf-8",
    )

    mem.append_daily_correction("2026-03-27", "Second correction.")

    content = digest_path.read_text(encoding="utf-8")
    assert content.count("## Corrections") == 1
    assert "- First correction." in content
    assert "- Second correction." in content


def test_append_daily_correction_ignores_heading_like_text_inside_fenced_code_block(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    digest_path = tmp_path / "01-Daily" / "2026-03-27.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        "# 2026-03-27\n\n## Timeline\n```md\n## not-a-heading\n```\n\n## Corrections\n- First correction.\n\n## Development\nShipped parser fix.\n",
        encoding="utf-8",
    )

    mem.append_daily_correction("2026-03-27", "Second correction.")

    content = digest_path.read_text(encoding="utf-8")
    assert "```md\n## not-a-heading\n```" in content
    assert (
        "## Corrections\n- First correction.\n- Second correction.\n\n## Development\nShipped parser fix."
        in content
    )


def test_append_daily_correction_preserves_heading_like_text_inside_corrections_body(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    digest_path = tmp_path / "01-Daily" / "2026-03-27.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        "# 2026-03-27\n\n## Corrections\n```md\n## not-a-heading\n```\n- First correction.\n\n## Development\nShipped parser fix.\n",
        encoding="utf-8",
    )

    mem.append_daily_correction("2026-03-27", "Second correction.")

    content = digest_path.read_text(encoding="utf-8")
    assert (
        "## Corrections\n```md\n## not-a-heading\n```\n- First correction.\n- Second correction.\n\n## Development\nShipped parser fix."
        in content
    )


def test_read_daily_digest_returns_content_or_empty(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    assert mem.read_daily_digest("2026-03-27") == ""

    digest_path = tmp_path / "01-Daily" / "2026-03-27.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text("# 2026-03-27\n\nDigest body.\n", encoding="utf-8")

    assert mem.read_daily_digest("2026-03-27") == "# 2026-03-27\n\nDigest body.\n"


# ---------------------------------------------------------------------------
# 6. read_config_file
# ---------------------------------------------------------------------------


def test_read_config_file(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    # Non-existent returns empty string
    assert mem.read_config_file("profile.md") == ""

    # Create the config dir and write a file
    config_dir = tmp_path / "04-Config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "profile.md").write_text(
        "name: Rupan\ntimezone: UTC+2", encoding="utf-8"
    )

    result = mem.read_config_file("profile.md")
    assert "name: Rupan" in result
    assert "UTC+2" in result


def test_upsert_config_section_replaces_target_section_without_clobbering_others(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    config_path = tmp_path / "04-Config" / "profile.md"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "# Profile\n\n## Bio\nBuilder.\n\n## Learned Corrections\nOld note.\n\n## Preferences\nTea.\n",
        encoding="utf-8",
    )

    path = mem.upsert_config_section(
        "profile.md",
        "## Learned Corrections",
        "- Prefer tea after 15:00.",
    )

    assert path == config_path
    content = config_path.read_text(encoding="utf-8")
    assert "## Bio\nBuilder." in content
    assert "## Preferences\nTea." in content
    assert "## Learned Corrections\n- Prefer tea after 15:00." in content
    assert "Old note." not in content


def test_upsert_config_section_appends_missing_reserved_section(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    config_path = tmp_path / "04-Config" / "profile.md"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("# Profile\n\n## Bio\nBuilder.\n", encoding="utf-8")

    mem.upsert_config_section(
        "profile.md",
        "## Learned Corrections",
        "Learns best from concrete examples.",
    )

    content = config_path.read_text(encoding="utf-8")
    assert "## Bio\nBuilder." in content
    assert "## Learned Corrections\nLearns best from concrete examples." in content


def test_upsert_config_section_preserves_complex_adjacent_sections(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    config_path = tmp_path / "04-Config" / "profile.md"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '# Profile\n\n## Bio\nWorks best with examples.\n\n## Learned Corrections\nOld note.\n\n## Preferences\n```yaml\nheading: "## not-a-heading"\n```\n- Tea\n',
        encoding="utf-8",
    )

    mem.upsert_config_section(
        "profile.md",
        "## Learned Corrections",
        "- Prefers examples before abstractions.",
    )

    content = config_path.read_text(encoding="utf-8")
    assert "## Bio\nWorks best with examples." in content
    assert "## Learned Corrections\n- Prefers examples before abstractions." in content
    assert '## Preferences\n```yaml\nheading: "## not-a-heading"\n```\n- Tea' in content
    assert "Old note." not in content


def test_upsert_config_section_rejects_non_reserved_target(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    with pytest.raises(ValueError, match="reserved config section"):
        mem.upsert_config_section(
            "preferences.md",
            "## Anything",
            "Nope.",
        )


def test_upsert_routines_section_replaces_target_section_without_clobbering_others(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    routines_path = tmp_path / "03-Life" / "routines.md"
    routines_path.parent.mkdir(parents=True, exist_ok=True)
    routines_path.write_text(
        "# Routines\n\n## Morning\nTea.\n\n## Correction Updates\nOld note.\n\n## Evening\nRead.\n",
        encoding="utf-8",
    )

    path = mem.upsert_life_section(
        "routines.md",
        "## Correction Updates",
        "Use a shorter shutdown routine.",
    )

    assert path == routines_path
    content = routines_path.read_text(encoding="utf-8")
    assert "## Morning\nTea." in content
    assert "## Evening\nRead." in content
    assert "## Correction Updates\nUse a shorter shutdown routine." in content
    assert "Old note." not in content


def test_upsert_routines_section_appends_missing_reserved_section(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    routines_path = tmp_path / "03-Life" / "routines.md"
    routines_path.parent.mkdir(parents=True, exist_ok=True)
    routines_path.write_text("# Routines\n\n## Morning\nTea.\n", encoding="utf-8")

    mem.upsert_life_section(
        "routines.md",
        "## Correction Updates",
        "Use a shorter shutdown routine.",
    )

    content = routines_path.read_text(encoding="utf-8")
    assert "## Morning\nTea." in content
    assert "## Correction Updates\nUse a shorter shutdown routine." in content


def test_update_pattern_notes_replaces_notes_only(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    updated_path = mem.update_pattern_notes(
        "late-night-coding", "This mostly happens when deadlines stack up."
    )

    assert updated_path == path
    content = path.read_text(encoding="utf-8")
    assert "**Status:** active" in content
    assert "**Confidence:** 0.82" in content
    assert "## Observation\nYou consistently start deep work after 22:00." in content
    assert "## User Notes\nThis mostly happens when deadlines stack up." in content
    assert "_None yet._" not in content


def test_update_pattern_notes_handles_non_terminal_user_notes_section(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)
    path.write_text(
        "# Pattern: Late-night coding sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nYou consistently start deep work after 22:00.\n\n## Evidence Log\n- 2026-01-10: 3 h session after 22:00\n\n## Trend\nStrengthening.\n\n## User Notes\nKeep this note.\n\n## Follow-up\n```md\n## still-not-a-heading\n```\nCheck again next week.\n",
        encoding="utf-8",
    )

    mem.update_pattern_notes("late-night-coding", "Updated note.")

    content = path.read_text(encoding="utf-8")
    assert (
        "## User Notes\nUpdated note.\n\n## Follow-up\n```md\n## still-not-a-heading\n```\nCheck again next week."
        in content
    )
    assert "Keep this note." not in content


def test_update_pattern_preserves_non_terminal_user_notes_section(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)
    path.write_text(
        "# Pattern: Late-night coding sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nYou consistently start deep work after 22:00.\n\n## Evidence Log\n- 2026-01-10: 3 h session after 22:00\n\n## Trend\nStrengthening.\n\n## User Notes\nKeep this note.\n\n## Follow-up\nMore context after notes.\n",
        encoding="utf-8",
    )

    mem.update_pattern(
        slug="late-night-coding",
        title="Late-night coding sessions",
        status="confirmed",
        confidence=0.95,
        first_seen="2026-01-10",
        last_updated="2026-03-26",
        observation="Pattern still present.",
        evidence_log=["2026-03-26: fresh entry"],
        trend="Stable.",
    )

    content = path.read_text(encoding="utf-8")
    assert "## User Notes\nKeep this note." in content
    assert "## Follow-up\nMore context after notes." in content


def test_update_pattern_preserves_unknown_extra_sections(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)
    path.write_text(
        "# Pattern: Late-night coding sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nYou consistently start deep work after 22:00.\n\n## Evidence Log\n- 2026-01-10: 3 h session after 22:00\n\n## Trend\nStrengthening.\n\n## User Notes\nKeep this note.\n\n## Follow-up\nMore context after notes.\n\n## References\n- journal/2026-03-20\n",
        encoding="utf-8",
    )

    mem.update_pattern(
        slug="late-night-coding",
        title="Late-night coding sessions",
        status="confirmed",
        confidence=0.95,
        first_seen="2026-01-10",
        last_updated="2026-03-26",
        observation="Pattern still present.",
        evidence_log=["2026-03-26: fresh entry"],
        trend="Stable.",
    )

    content = path.read_text(encoding="utf-8")
    assert "## User Notes\nKeep this note." in content
    assert "## Follow-up\nMore context after notes." in content
    assert "## References\n- journal/2026-03-20" in content


def test_update_pattern_notes_preserves_existing_status_when_not_provided(
    tmp_path: Path,
) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    mem.update_pattern_notes("late-night-coding", "Updated note.")

    content = path.read_text(encoding="utf-8")
    assert "**Status:** active" in content
    assert "## User Notes\nUpdated note." in content


def test_update_pattern_notes_does_not_accept_status_argument(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    _write_sample_pattern(mem)

    with pytest.raises(TypeError):
        mem.update_pattern_notes(
            "late-night-coding", "Updated note.", status="confirmed"
        )


def test_update_pattern_status_replaces_status_only(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    updated_path = mem.update_pattern_status("late-night-coding", "confirmed")

    assert updated_path == path
    content = path.read_text(encoding="utf-8")
    assert "**Status:** confirmed" in content
    assert "**Confidence:** 0.82" in content
    assert "## User Notes\n_None yet._" in content


@pytest.mark.parametrize("status", ["strengthening", "weakening", "invalidated"])
def test_update_pattern_status_accepts_lifecycle_statuses(
    tmp_path: Path, status: str
) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    updated_path = mem.update_pattern_status("late-night-coding", status)

    assert updated_path == path
    content = path.read_text(encoding="utf-8")
    assert f"**Status:** {status}" in content


def test_update_pattern_status_requires_existing_file(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    with pytest.raises(FileNotFoundError):
        mem.update_pattern_status("missing-pattern", "confirmed")


def test_update_pattern_rejects_invalid_status(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)
    path = _write_sample_pattern(mem)

    with pytest.raises(ValueError, match="Pattern status is not in the allowed set"):
        mem.update_pattern(
            slug="late-night-coding",
            title="Late-night coding sessions",
            status="definitely-maybe",
            confidence=0.95,
            first_seen="2026-01-10",
            last_updated="2026-03-26",
            observation="Pattern still present.",
            evidence_log=["2026-03-26: fresh entry"],
            trend="Stable.",
        )

    content = path.read_text(encoding="utf-8")
    assert "**Status:** active" in content


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("append_daily_correction", ("../escape", "nope")),
        ("read_daily_digest", ("../escape",)),
        ("read_pattern_by_slug", ("../escape",)),
        ("update_pattern_notes", ("../escape", "nope")),
        ("upsert_config_section", ("../profile.md", "## Learned Corrections", "nope")),
    ],
)
def test_helpers_reject_path_traversal_inputs(
    tmp_path: Path, method_name: str, args: tuple[object, ...]
) -> None:
    mem = _make_memory(tmp_path)

    with pytest.raises(ValueError, match="vault-relative name"):
        getattr(mem, method_name)(*args)


def test_read_pattern_by_slug_returns_content_or_empty(tmp_path: Path) -> None:
    mem = _make_memory(tmp_path)

    assert mem.read_pattern_by_slug("late-night-coding") == ""

    _write_sample_pattern(mem)

    content = mem.read_pattern_by_slug("late-night-coding")
    assert "# Pattern: Late-night coding sessions" in content

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
        evidence_log=["2026-01-10: 3 h session after 22:00", "2026-02-14: 2.5 h session after 23:00"],
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

    assert "## User Notes" in content
    assert "_None yet._" in content


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


def test_read_patterns_returns_empty_list_when_directory_missing(tmp_path: Path) -> None:
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
        evidence_log=["2026-01-10: 3 h session after 22:00", "2026-03-26: new evidence"],
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
    (config_dir / "profile.md").write_text("name: Rupan\ntimezone: UTC+2", encoding="utf-8")

    result = mem.read_config_file("profile.md")
    assert "name: Rupan" in result
    assert "UTC+2" in result

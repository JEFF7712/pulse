from pathlib import Path

from pulse.vault.onboarding import ensure_vault_onboarding


def test_ensure_vault_onboarding_creates_readme_and_agents(tmp_path: Path) -> None:
    ensure_vault_onboarding(tmp_path)

    readme = tmp_path / "README.md"
    agents = tmp_path / "Meta" / "AGENTS.md"
    assert readme.is_file()
    assert agents.is_file()
    assert "01-Daily" in readme.read_text(encoding="utf-8")
    assert "Reserved sections" in readme.read_text(encoding="utf-8")
    assert "Meta/AGENTS.md" in readme.read_text(encoding="utf-8")
    assert "reserved" in agents.read_text(encoding="utf-8").lower()


def test_ensure_vault_onboarding_idempotent_and_preserves_edits(tmp_path: Path) -> None:
    ensure_vault_onboarding(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# Custom\n", encoding="utf-8")

    ensure_vault_onboarding(tmp_path)

    assert readme.read_text(encoding="utf-8") == "# Custom\n"
    assert (tmp_path / "Meta" / "AGENTS.md").exists()

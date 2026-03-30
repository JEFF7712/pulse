from pathlib import Path

from pulse.vault.onboarding import ensure_vault_onboarding


def write_daily_digest(vault_root: Path, date_slug: str, content: str) -> Path:
    ensure_vault_onboarding(vault_root)
    output_path = Path(vault_root) / "01-Daily" / f"{date_slug}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path

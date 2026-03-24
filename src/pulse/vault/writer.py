from pathlib import Path


def write_daily_digest(vault_root: Path, date_slug: str, content: str) -> Path:
    output_path = Path(vault_root) / "01-Daily" / f"{date_slug}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path

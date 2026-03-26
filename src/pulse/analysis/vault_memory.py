"""VaultMemory — read/write pattern and life knowledge files in the Obsidian vault."""
from __future__ import annotations

from pathlib import Path

_DEFAULT_NOTES = "_None yet._"


class VaultMemory:
    """Thin file-system adapter for reading and writing vault knowledge files."""

    def __init__(self, vault_root: str | Path) -> None:
        self._root = Path(vault_root)

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def write_pattern(
        self,
        slug: str,
        title: str,
        status: str,
        confidence: float | str,
        first_seen: str,
        last_updated: str,
        observation: str,
        evidence_log: list[str],
        trend: str,
        user_notes: str | None = None,
    ) -> Path:
        """Write a pattern markdown file and return its path."""
        notes_section = user_notes if user_notes is not None else _DEFAULT_NOTES
        evidence_lines = "\n".join(f"- {item}" for item in evidence_log)

        content = (
            f"# Pattern: {title}\n"
            "\n"
            f"**Status:** {status}\n"
            f"**Confidence:** {confidence}\n"
            f"**First seen:** {first_seen}\n"
            f"**Last updated:** {last_updated}\n"
            "\n"
            "## Observation\n"
            f"{observation}\n"
            "\n"
            "## Evidence Log\n"
            f"{evidence_lines}\n"
            "\n"
            "## Trend\n"
            f"{trend}\n"
            "\n"
            "## User Notes\n"
            f"{notes_section}\n"
        )

        path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_patterns(self) -> list[dict]:
        """Return all pattern files as ``{"slug": stem, "content": text}`` dicts."""
        patterns_dir = self._root / "02-Insights" / "patterns"
        if not patterns_dir.exists():
            return []
        return [
            {"slug": p.stem, "content": p.read_text(encoding="utf-8")}
            for p in sorted(patterns_dir.glob("*.md"))
        ]

    def update_pattern(
        self,
        slug: str,
        title: str,
        status: str,
        confidence: float | str,
        first_seen: str,
        last_updated: str,
        observation: str,
        evidence_log: list[str],
        trend: str,
    ) -> Path:
        """Re-write a pattern file, preserving any user-edited notes."""
        existing_notes: str | None = None
        path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
        if path.exists():
            existing_notes = self._extract_user_notes(path.read_text(encoding="utf-8"))

        return self.write_pattern(
            slug=slug,
            title=title,
            status=status,
            confidence=confidence,
            first_seen=first_seen,
            last_updated=last_updated,
            observation=observation,
            evidence_log=evidence_log,
            trend=trend,
            user_notes=existing_notes,
        )

    # ------------------------------------------------------------------
    # Life files (03-Life/)
    # ------------------------------------------------------------------

    def read_life_file(self, filename: str) -> str:
        """Return file contents from ``03-Life/``, or ``""`` if not found."""
        path = self._root / "03-Life" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_life_file(self, filename: str, content: str) -> Path:
        """Write content to ``03-Life/{filename}`` and return the path."""
        path = self._root / "03-Life" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Config files (04-Config/)
    # ------------------------------------------------------------------

    def read_config_file(self, filename: str) -> str:
        """Return file contents from ``04-Config/``, or ``""`` if not found."""
        path = self._root / "04-Config" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_notes(content: str) -> str | None:
        """Pull out the text under ``## User Notes``; return None if default or missing."""
        marker = "## User Notes\n"
        idx = content.find(marker)
        if idx == -1:
            return None
        notes = content[idx + len(marker):].strip()
        if notes == _DEFAULT_NOTES:
            return None
        return notes

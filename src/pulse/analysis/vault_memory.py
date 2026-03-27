"""VaultMemory — read/write pattern and life knowledge files in the Obsidian vault."""

from __future__ import annotations

from pathlib import Path

from pulse.domain.pattern_statuses import normalize_pattern_status

_DEFAULT_NOTES = "_None yet._"
_RESERVED_CONFIG_SECTIONS = {
    "profile.md": {"## Learned Corrections"},
}
_RESERVED_LIFE_SECTIONS = {
    "routines.md": {"## Correction Updates"},
}


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
        extra_sections: str = "",
    ) -> Path:
        """Write a pattern markdown file and return its path."""
        slug = self._validate_vault_name(slug)
        normalized_status = normalize_pattern_status(status)
        notes_section = user_notes if user_notes is not None else _DEFAULT_NOTES
        evidence_lines = "\n".join(f"- {item}" for item in evidence_log)

        content = (
            f"# Pattern: {title}\n"
            "\n"
            f"**Status:** {normalized_status}\n"
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

        if extra_sections.strip():
            content = f"{content.rstrip()}\n\n{extra_sections.strip()}\n"

        path = self._pattern_path(slug)
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

    def read_pattern_by_slug(self, slug: str) -> str:
        """Return a pattern file by slug, or ``""`` if not found."""
        path = self._pattern_path(slug)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def pattern_exists(self, slug: str) -> bool:
        """Return True when the pattern file exists."""
        return self._pattern_path(slug).exists()

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
        """Re-write a pattern file, preserving existing observation, evidence, and user notes."""
        path = self._pattern_path(slug)
        normalized_status = normalize_pattern_status(status)
        existing_notes: str | None = None
        existing_observation: str | None = None
        existing_evidence: list[str] = []
        existing_first_seen: str | None = None
        extra_sections = ""

        if path.exists():
            content = path.read_text(encoding="utf-8")
            existing_notes = self._extract_user_notes(content)
            existing_observation = self._extract_section(content, "## Observation")
            existing_evidence = self._extract_evidence(content)
            existing_first_seen = self._extract_field(content, "First seen")
            extra_sections = self._extract_extra_sections(content)

        # Append new observation as an update entry, keep original
        if existing_observation:
            combined_observation = (
                f"{existing_observation}\n\n**Update ({last_updated}):** {observation}"
            )
        else:
            combined_observation = observation

        # Append new evidence to existing, dedup
        existing_set = set(existing_evidence)
        combined_evidence = list(existing_evidence)
        for item in evidence_log:
            if item not in existing_set:
                combined_evidence.append(item)

        return self.write_pattern(
            slug=slug,
            title=title,
            status=normalized_status,
            confidence=confidence,
            first_seen=existing_first_seen or first_seen,
            last_updated=last_updated,
            observation=combined_observation,
            evidence_log=combined_evidence,
            trend=trend,
            user_notes=existing_notes,
            extra_sections=extra_sections,
        )

    def update_pattern_notes(self, slug: str, note: str) -> Path:
        """Replace the reserved notes section for a pattern without rewriting other sections."""
        path = self._pattern_path(slug)
        content = path.read_text(encoding="utf-8")
        updated = self._upsert_section(content, "## User Notes", note)
        path.write_text(updated, encoding="utf-8")
        return path

    def update_pattern_status(self, slug: str, status: str) -> Path:
        """Replace the pattern status field without rewriting other content."""
        path = self._pattern_path(slug)
        content = path.read_text(encoding="utf-8")
        normalized_status = normalize_pattern_status(status)
        marker = "**Status:** "
        idx = content.find(marker)
        if idx == -1:
            raise ValueError("Pattern status field is missing")
        start = idx + len(marker)
        end = content.find("\n", start)
        if end == -1:
            end = len(content)
        updated = f"{content[:start]}{normalized_status}{content[end:]}"
        path.write_text(updated, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Daily digests (01-Daily/)
    # ------------------------------------------------------------------

    def read_daily_digest(self, date_slug: str) -> str:
        """Return daily digest contents, or ``""`` if not found."""
        path = self._daily_digest_path(date_slug)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def daily_digest_exists(self, date_slug: str) -> bool:
        """Return True when the daily digest file exists."""
        return self._daily_digest_path(date_slug).exists()

    def append_daily_correction(self, date_slug: str, note: str) -> Path:
        """Append a correction note under the reserved digest corrections section."""
        path = self._daily_digest_path(date_slug)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = self._append_section_bullet(existing, "## Corrections", note)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Life files (03-Life/)
    # ------------------------------------------------------------------

    def read_life_file(self, filename: str) -> str:
        """Return file contents from ``03-Life/``, or ``""`` if not found."""
        filename = self._validate_vault_name(filename)
        path = self._root / "03-Life" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def life_file_exists(self, filename: str) -> bool:
        """Return True when the life file exists."""
        filename = self._validate_vault_name(filename)
        return (self._root / "03-Life" / filename).exists()

    def write_life_file(self, filename: str, content: str) -> Path:
        """Write content to ``03-Life/{filename}`` and return the path."""
        filename = self._validate_vault_name(filename)
        path = self._root / "03-Life" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def upsert_life_section(self, filename: str, heading: str, body: str) -> Path:
        """Replace or append a reserved section within a life file."""
        filename = self._validate_vault_name(filename)
        allowed_headings = _RESERVED_LIFE_SECTIONS.get(filename)
        if allowed_headings is None or heading not in allowed_headings:
            raise ValueError(f"{filename} / {heading} is not a reserved life section")
        path = self._root / "03-Life" / filename
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = self._upsert_section(existing, heading, body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Config files (04-Config/)
    # ------------------------------------------------------------------

    def read_config_file(self, filename: str) -> str:
        """Return file contents from ``04-Config/``, or ``""`` if not found."""
        filename = self._validate_vault_name(filename)
        path = self._root / "04-Config" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def config_file_exists(self, filename: str) -> bool:
        """Return True when the config file exists."""
        filename = self._validate_vault_name(filename)
        return (self._root / "04-Config" / filename).exists()

    def write_config_file(self, filename: str, content: str) -> Path:
        """Write content to ``04-Config/{filename}`` and return the path."""
        filename = self._validate_vault_name(filename)
        path = self._root / "04-Config" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def upsert_config_section(self, filename: str, heading: str, body: str) -> Path:
        """Replace or append a reserved section within a config file."""
        filename = self._validate_vault_name(filename)
        allowed_headings = _RESERVED_CONFIG_SECTIONS.get(filename)
        if allowed_headings is None or heading not in allowed_headings:
            raise ValueError(f"{filename} / {heading} is not a reserved config section")
        path = self._root / "04-Config" / filename
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated = self._upsert_section(existing, heading, body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        return path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_notes(content: str) -> str | None:
        """Pull out the text under ``## User Notes``; return None if default or missing."""
        notes = VaultMemory._extract_section(content, "## User Notes")
        if notes is None:
            return None
        if notes == _DEFAULT_NOTES:
            return None
        return notes

    @staticmethod
    def _extract_section(content: str, heading: str) -> str | None:
        """Extract text between a heading and the next heading."""
        bounds = VaultMemory._find_section_bounds(content, heading)
        if bounds is None:
            return None
        _, start, end = bounds
        return content[start:end].strip()

    @staticmethod
    def _extract_evidence(content: str) -> list[str]:
        """Extract bullet items from the Evidence Log section."""
        section = VaultMemory._extract_section(content, "## Evidence Log")
        if section is None:
            return []
        return [
            line.lstrip("- ").strip()
            for line in section.strip().splitlines()
            if line.strip().startswith("- ")
        ]

    @staticmethod
    def _extract_field(content: str, field_name: str) -> str | None:
        """Extract a **Field:** value from pattern frontmatter."""
        marker = f"**{field_name}:** "
        idx = content.find(marker)
        if idx == -1:
            return None
        start = idx + len(marker)
        end = content.find("\n", start)
        return content[start:end].strip() if end != -1 else content[start:].strip()

    def _daily_digest_path(self, date_slug: str) -> Path:
        date_slug = self._validate_vault_name(date_slug)
        return self._root / "01-Daily" / f"{date_slug}.md"

    def _pattern_path(self, slug: str) -> Path:
        slug = self._validate_vault_name(slug)
        return self._root / "02-Insights" / "patterns" / f"{slug}.md"

    @staticmethod
    def _validate_vault_name(name: str) -> str:
        path = Path(name)
        if (
            not name
            or path.is_absolute()
            or len(path.parts) != 1
            or path.parts[0] in {".", ".."}
        ):
            raise ValueError(f"{name!r} is not a safe vault-relative name")
        return name

    @staticmethod
    def _extract_extra_sections(content: str) -> str:
        known_headings = {
            "## Observation",
            "## Evidence Log",
            "## Trend",
            "## User Notes",
        }
        extra_sections = [
            content[start:end].strip()
            for heading, start, _, end in VaultMemory._iter_level2_sections(content)
            if heading not in known_headings
        ]
        return "\n\n".join(section for section in extra_sections if section)

    @classmethod
    def _append_section_bullet(cls, content: str, heading: str, note: str) -> str:
        existing = cls._extract_section(content, heading)
        bullet = f"- {note.strip()}"
        if existing is None:
            return cls._upsert_section(content, heading, bullet)
        body = existing.rstrip()
        if body:
            body = f"{body}\n{bullet}"
        else:
            body = bullet
        return cls._upsert_section(content, heading, body)

    @staticmethod
    def _upsert_section(content: str, heading: str, body: str) -> str:
        normalized_body = body.strip()
        section = f"{heading}\n{normalized_body}\n"
        bounds = VaultMemory._find_section_bounds(content, heading)

        if bounds is None:
            base = content.rstrip()
            if base:
                return f"{base}\n\n{section}"
            return section

        section_start, _, end = bounds
        prefix = content[:section_start].rstrip()
        suffix = content[end:]

        result = section
        if prefix:
            result = f"{prefix}\n\n{result}"
        if suffix:
            result = f"{result}\n{suffix.lstrip()}"
        return result

    @staticmethod
    def _find_section_bounds(content: str, heading: str) -> tuple[int, int, int] | None:
        for (
            seen_heading,
            section_start,
            body_start,
            end,
        ) in VaultMemory._iter_level2_sections(content):
            if seen_heading == heading:
                return (section_start, body_start, end)
        return None

    @staticmethod
    def _iter_level2_sections(content: str) -> list[tuple[str, int, int, int]]:
        sections: list[tuple[str, int, int, int]] = []
        section_start: int | None = None
        body_start: int | None = None
        heading_text: str | None = None
        offset = 0
        in_fence = False
        fence_marker: str | None = None

        for line in content.splitlines(keepends=True):
            stripped = line.lstrip()
            heading_line = stripped.rstrip("\n")

            if fence_marker is None:
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_fence = True
                    fence_marker = stripped[:3]
            elif stripped.startswith(fence_marker):
                in_fence = False
                fence_marker = None

            if not in_fence and heading_line.startswith("## "):
                if (
                    section_start is not None
                    and body_start is not None
                    and heading_text is not None
                ):
                    sections.append((heading_text, section_start, body_start, offset))
                if heading_line.startswith("## "):
                    section_start = offset
                    body_start = offset + len(line)
                    heading_text = heading_line

            offset += len(line)

        if (
            section_start is not None
            and body_start is not None
            and heading_text is not None
        ):
            sections.append((heading_text, section_start, body_start, len(content)))
        return sections

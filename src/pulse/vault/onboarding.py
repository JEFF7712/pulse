"""Create default vault documentation on first use (Obsidian-friendly, idempotent)."""

from __future__ import annotations

from pathlib import Path

_README_MD = """# Pulse vault

This folder is **Pulse’s markdown memory**: discovered patterns and a small amount of config you can edit. Pulse writes here automatically; you can open the same directory in [Obsidian](https://obsidian.md/) or any editor.

Configure the path with `vault_path` in `pulse.toml` or the **`PULSE_VAULT_PATH`** environment variable.

## Layout

| Path | Purpose |
| --- | --- |
| `02-Insights/patterns/` | Recurring insights (“patterns”) with evidence and trends |
| `03-Life/` | Longer-lived context (e.g. `routines.md` baselines from discovery) |
| `04-Config/` | `profile.md` and other operator-facing notes |
| `Meta/` | Alongside this README: **`AGENTS.md`** (rules for AI tools) |

Some folders appear only after Pulse has generated content (for example patterns after discovery).

## What Pulse updates automatically

- **Pattern files** — created and updated by discovery; observations and evidence accumulate over time.
- **`03-Life/routines.md`** — may be rewritten when discovery proposes baseline updates.

## Reserved sections (machine edits)

Do not rename these headings if you want automation to keep working:

| File | Heading / field | Used for |
| --- | --- | --- |
| `02-Insights/patterns/*.md` | `## User Notes` | Operator commentary Pulse preserves when refreshing patterns |
| `02-Insights/patterns/*.md` | `**Status:**` line | Pattern status metadata |

Everything else in those files is yours to edit freely; Pulse tries to preserve user-authored body text when it refreshes patterns.

## Safe to edit

- **`04-Config/profile.md`** — your goals, context, and preferences.
- **Pattern `## User Notes`** — your commentary on each pattern.
- **Any new notes** you add in this vault — Pulse ignores files and folders it does not manage.

## Wikilinks, graph, and tags (Obsidian)

Pattern notes under **`02-Insights/patterns/`** include a **Related days** section listing ISO dates from evidence (plain text).

Pulse-written pattern notes start with YAML **frontmatter** (`pulse: true`, `type: pattern`, `tags`) and may end with inline **`#pulse`** hashtags for the tag pane.

## AI assistants

See **`Meta/AGENTS.md`** for a short contract (what to read first, what not to delete).

---

*Generated when this vault was first used. You may edit or delete this file; Pulse will not overwrite it.*
"""

_AGENTS_MD = """# Pulse vault — notes for AI assistants

This directory is a **Pulse** knowledge vault (plain Markdown on disk). The human operator may open it in Obsidian.

## Read first

1. Parent **`README.md`** — full folder map and **reserved section** list (do not rename those `##` headings).
2. **`02-Insights/patterns/`** for discovered patterns and evidence.
3. **`04-Config/profile.md`** for user-stated preferences and goals.

## Defaults

- Prefer **narrow edits**: append bullets under reserved headings rather than rewriting whole files.
- **Do not** delete or rename **`02-Insights/patterns/`** or reserved headings unless the user explicitly asks.
- **Do not** assume every file exists yet; list or read before editing.

## Operator config

Vault path is set by the operator (`vault_path` / `PULSE_VAULT_PATH`). Pulse MCP and CLI expose events, discovery, and patterns against this tree.

---

*Generated when this vault was first used. The operator may edit or delete this file; Pulse will not overwrite it.*
"""


def ensure_vault_onboarding(vault_root: str | Path) -> None:
    """Write default README and Meta/AGENTS.md if missing (never overwrite)."""
    root = Path(vault_root)
    root.mkdir(parents=True, exist_ok=True)

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(_README_MD, encoding="utf-8")

    meta = root / "Meta"
    meta.mkdir(parents=True, exist_ok=True)
    agents = meta / "AGENTS.md"
    if not agents.exists():
        agents.write_text(_AGENTS_MD, encoding="utf-8")

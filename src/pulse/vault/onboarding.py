"""Create default vault documentation on first use (Obsidian-friendly, idempotent)."""

from __future__ import annotations

from pathlib import Path

_README_MD = """# Pulse vault

This folder is **Pulse’s markdown memory**: daily digests, discovered patterns, and a small amount of config you can edit. Pulse writes here automatically; you can open the same directory in [Obsidian](https://obsidian.md/) or any editor.

Configure the path with `vault_path` in `pulse.toml` or the **`PULSE_VAULT_PATH`** environment variable.

## Layout

| Path | Purpose |
| --- | --- |
| `01-Daily/` | One file per day (`YYYY-MM-DD.md`) — timeline-style digest |
| `02-Insights/patterns/` | Recurring insights (“patterns”) with evidence and trends |
| `03-Life/` | Longer-lived context (e.g. `routines.md` baselines from discovery) |
| `04-Config/` | `profile.md` and other operator-facing notes |
| `Meta/` | This README’s companion: **`AGENTS.md`** (rules for AI tools) |

Some folders appear only after Pulse has generated content (for example patterns after discovery).

## What Pulse updates automatically

- **Daily digests** — new or overwritten for each date when the digest job runs.
- **Pattern files** — created and updated by discovery; observations and evidence accumulate over time.
- **`03-Life/routines.md`** — may be rewritten when discovery proposes baseline updates.
- **Corrections** — when you send a correction (Telegram reply, webhook, or MCP), Pulse may append or patch **only the sections listed below**.

## Reserved sections (machine edits)

Do not rename these headings if you want corrections and automation to keep working:

| File | Heading / field | Used for |
| --- | --- | --- |
| `01-Daily/*.md` | `## Corrections` | User corrections appended as bullets |
| `02-Insights/patterns/*.md` | `## User Notes` | Correction text may replace this section |
| `02-Insights/patterns/*.md` | `**Status:**` line | Status may be updated by corrections |
| `04-Config/profile.md` | `## Learned Corrections` | Bounded correction summaries |
| `03-Life/routines.md` | `## Correction Updates` | Bounded correction summaries |

Everything else in those files is yours to edit freely; Pulse tries to preserve user-authored body text when it refreshes patterns.

## Safe to edit

- **`04-Config/profile.md`** — your goals, context, and preferences (keep the reserved heading above if you use corrections).
- **Pattern `## User Notes`** — your commentary on each pattern.
- **Any new notes** you add in this vault — Pulse ignores files and folders it does not manage.

## Wikilinks (Obsidian)

Daily digest notes include **path-qualified** links to the previous and next calendar day, for example `[[01-Daily/2026-03-29]]`. In [Obsidian](https://obsidian.md/), those become clickable and contribute to the graph. Targets use the `01-Daily/` prefix so the link resolves even if other files share the same `YYYY-MM-DD` stem elsewhere in the vault. Neighbor days may not exist yet; Obsidian will still show the link (often as “unresolved”) until you generate that digest.

## AI assistants

See **`Meta/AGENTS.md`** for a short contract (what to read first, what not to delete).

---

*Generated when this vault was first used. You may edit or delete this file; Pulse will not overwrite it.*
"""

_AGENTS_MD = """# Pulse vault — notes for AI assistants

This directory is a **Pulse** knowledge vault (plain Markdown on disk). The human operator may open it in Obsidian.

## Read first

1. Parent **`README.md`** — full folder map and **reserved section** list (do not rename those `##` headings).
2. Recent **`01-Daily/`** notes for factual timeline context.
3. **`04-Config/profile.md`** for user-stated preferences and goals.

## Defaults

- Prefer **narrow edits**: append bullets under reserved headings rather than rewriting whole files.
- **Do not** delete or rename **`01-Daily/`**, **`02-Insights/patterns/`**, or reserved headings unless the user explicitly asks.
- **Do not** assume every file exists yet; list or read before editing.

## Wikilinks

Daily digests may contain Obsidian wikilinks such as `[[01-Daily/YYYY-MM-DD]]` for adjacent days. Prefer that path form when linking digest files so names stay unique.

## Operator config

Vault path is set by the operator (`vault_path` / `PULSE_VAULT_PATH`). Pulse MCP and CLI expose events, digests, and corrections against this tree.

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

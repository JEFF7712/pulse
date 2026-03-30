# Self-Hosting Quickstart

**Happy path:** `pulse configure` → `pulse init` → `pulse run`.

## Install

Ships `pulse` and `pulse-mcp`.

```bash
pipx install pulse-agent
```

Alternatives: `uv tool install pulse-agent` or `pip install pulse-agent`. Check with `pulse --help`.

## Developer install

- **uv:** `uv sync` (optional `--group dev`)
- **Nix:** `nix develop`, then `uv sync --group dev`
- **venv:** `python3 -m venv .venv` → activate → `pip install -e .`

## 1. Configure

If you use Google, Spotify, Microsoft 365, GitHub, GitLab, or Plaid, create OAuth (and Plaid) apps first so client IDs and secrets are ready. Oura: personal access token or OAuth app.

```bash
pulse configure
```

**Menu:** Core (database, vault, timezone), **Connectors** (per-source creds + OAuth/Plaid/Oura when ●), Notifications, Model providers, LLM block in TOML, Full wizard. TTY: arrows + Enter; else digits `0`–`6` (`0` = Done). **`PULSE_*`** overrides top-level TOML when set in the environment.

**Config file:** Prefer **`.config/pulse.toml`** or repo-root **`pulse.toml`**. Override with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`**. Start from `pulse.toml.example`; connectors default to disabled until you enable them.

There is no separate `pulse auth` command. In **Configure → Connectors**, open each enabled OAuth/Plaid/Oura source and finish the browser flow (localhost callbacks on `8888`, `8890`–`8894` as applicable). Complete this **before** `pulse init` if the first pull should hit those APIs. Notion, Linear (API key), browser, and feeds skip browser OAuth here.

**Shortcut:** `pulse onboard` runs the same configure-style path plus auth when credentials and enabled connectors allow it. Use `pulse onboard --strict` to fail if any auth step fails. Profile flags match `pulse init` (`-f`, `--profile-text`); server: `--host`, `--port`, `--log-level`.

## 2. `pulse init`

```bash
pulse init
```

Ensures vault **`README.md`** and **`Meta/AGENTS.md`** exist (created once if missing), writes **`04-Config/profile.md`**, runs initial pulls, optional discovery when LLM + notification config allows.

## 3. `pulse run`

```bash
pulse run
```

Serves on `0.0.0.0:8000` by default (`--host` / `--port` / `--log-level` to change). **`/`** — operator page with Pull, Digest, Discover, Test Telegram (same pipelines as CLI where noted).

## 4. Inspect

```bash
pulse status
pulse insights
```

`status` — DB path, event counts, cursors. `insights` — discovery output; prompts you to run discovery first if empty.

| Command | Purpose |
| --- | --- |
| `pulse pull [sources…]` | Immediate connector pulls |
| `pulse digest [--date YYYY-MM-DD]` | Daily digest file for that day |
| `pulse discover [--cadence …]` | Manual discovery pass |
| `pulse test-telegram` | One-off Telegram test |

Re-open **Configure → Connectors** anytime to re-auth or edit `pulse.toml`.

## Connect Pulse to your coding agent (MCP) {#mcp-agent-paste}

Use the [Model Context Protocol](https://modelcontextprotocol.io/) so **Claude Code**, **OpenClaw**, **Cursor**, and other MCP clients can call Pulse tools (`pulse_events_for_day`, `pulse_digest`, `pulse_correct`, …) against the same database and vault as this install.

**Send your coding agent** — copy everything in the box into the agent chat (it will fetch the doc and do the work):

```text
Read https://raw.githubusercontent.com/JEFF7712/pulse/main/docs/self-hosting/mcp-agent-setup.md and follow every step to install Pulse (pulse-agent), ensure pulse.toml exists, and register pulse-mcp in my MCP settings for this machine.
```

## Vault (Obsidian)

Output lives under **`vault_path`** / **`PULSE_VAULT_PATH`**. Common patterns: dedicated folder as its own vault; subfolder inside an existing vault; or symlink (mobile/sync may not handle symlinks well). First vault use may create **`README.md`** (structure + reserved headings) and **`Meta/AGENTS.md`**.

Daily digests include **wikilinks** to the previous and next day as `[[01-Daily/YYYY-MM-DD]]` for navigation and graph edges in Obsidian.

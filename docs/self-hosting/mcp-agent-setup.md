# MCP agent setup (for AI assistants)

This page is written for **coding agents** (Claude Code, OpenClaw, Cursor, and similar). A human may paste a link or path to this file and ask you to execute it. Your job is to install Pulse, ensure configuration exists on disk, and register the **pulse-mcp** Model Context Protocol server in their environment.

## Outcomes

When you are done:

1. **`pulse-agent`** is installed so `pulse` and `pulse-mcp` are available (prefer **`pipx install pulse-agent`**; alternatives: `uv tool install pulse-agent`, `pip install pulse-agent`, or `uv sync` from a git clone with `uv run pulse-mcp`).
2. A real **`pulse.toml`** exists where Pulse resolves config (default **`~/.config/pulse/pulse.toml`**, or repo-root **`pulse.toml`**, or the path set by **`PULSE_CONFIG_FILE`** / **`PULSE_CONFIG_DIR`**). The MCP server calls `load_config(require_files=True)` and **will not start** without this file.
3. **`database_path`** and **`vault_path`** in that file (or **`PULSE_DATABASE_PATH`** / **`PULSE_VAULT_PATH`** in the MCP process environment) point at the SQLite DB and markdown vault the user intends to use.
4. The user’s MCP client has a server entry that runs **`pulse-mcp`** (or `uv run python -m pulse.mcp.server` from a clone) with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** set if the client’s working directory would not otherwise find `pulse.toml`.

## Steps

### 1. Install

- Prefer isolated install: `pipx install pulse-agent`.
- Verify: `pulse --help` and ensure `pulse-mcp` is on `PATH` (same prefix as `pulse`).

### 2. Create configuration

- If no `pulse.toml` exists, run **`pulse configure`** with the user (TTY) or guide them through non-interactive env + file creation using **`pulse.toml.example`** in the repository as a template.
- OAuth and API keys for connectors are optional for MCP to **start**; they are required for live connector data. Connector setup uses **Configure → Connectors** in `pulse configure` (browser flows on localhost ports such as **8888** as documented in the self-hosting quickstart).
- Optional combined path: **`pulse onboard`** / **`pulse onboard --strict`** with profile flags such as **`-f ./my-profile.txt`** or **`--profile-text`** when the user wants onboarding plus auth in one go.

### 3. Initialize (recommended)

- Run **`pulse init`** once so the vault layout and profile scaffolding exist, unless the user explicitly wants MCP-only without that step.

### 4. Register MCP in the client

**Prerequisites**

1. A real **`pulse.toml`** must exist where `load_config()` resolves (default **`~/.config/pulse/pulse.toml`**, repo-root **`pulse.toml`**, or **`PULSE_CONFIG_FILE`** / **`PULSE_CONFIG_DIR`**). MCP uses `load_config(require_files=True)` and **exits on startup** if the file is missing - env-only DB/vault paths are not enough without TOML on disk.
2. **`database_path`** and **`vault_path`** in that file (or **`PULSE_DATABASE_PATH`** / **`PULSE_VAULT_PATH`** in the MCP `env` block) must match the standalone app / scheduler.
3. If the client’s working directory would not find config, set **`PULSE_CONFIG_FILE`** (absolute path) or **`PULSE_CONFIG_DIR`** in `env`.

**Example: `pulse-mcp` on `PATH`** (after `pipx install pulse-agent` or `uv tool install pulse-agent`):

```json
{
  "mcpServers": {
    "pulse": {
      "command": "pulse-mcp",
      "env": {
        "PULSE_CONFIG_FILE": "/absolute/path/to/pulse.toml"
      }
    }
  }
}
```

Omit **`PULSE_CONFIG_FILE`** when default resolution already finds `pulse.toml` (typical: `~/.config/pulse/pulse.toml`).

**Example: git clone with uv**

```json
{
  "mcpServers": {
    "pulse": {
      "command": "uv",
      "args": ["run", "python", "-m", "pulse.mcp.server"],
      "cwd": "/absolute/path/to/pulse/repo",
      "env": {
        "PULSE_DATABASE_PATH": "/absolute/path/to/pulse.db",
        "PULSE_VAULT_PATH": "/absolute/path/to/Pulse-Vault"
      }
    }
  }
}
```

When using repo-root **`pulse.toml`**, set server **`cwd`** to that repo if the client supports it; otherwise use **`PULSE_CONFIG_FILE`**.

Exact client file locations differ (Claude Code, OpenClaw, Cursor, etc.); merge the block without duplicating the top-level `mcpServers` key.

### MCP tools

| Tool | Description |
| --- | --- |
| `pulse_longitudinal_profile` | Long-horizon structure: monthly composition drift per entity, sleep-phase drift, deep-versus-fragmented attention, and what quietly stopped |
| `pulse_change_surface` | What changed versus the user's own trailing baseline: new, returning and off-rate entities, plus clusters of events unlike anything in history |
| `pulse_query_events` | Query events by time range, source(s), and text; newest-first, paginated, trimmed (pass `full=true` for raw) |
| `pulse_digest` | Deterministic day digest: per-source counts + clustered activity (browsing, email, calendar, media, dev, health, finance) |
| `pulse_coverage` | Per-source event count, last-event freshness, and connector sync state |
| `pulse_events_for_day` | Query all events for a specific date, optionally filtered by source |
| `pulse_ingest_event` | Manually push an event into the store |
| `pulse_pattern_list` / `pulse_pattern_read` | List recorded patterns / read one in full |
| `pulse_pattern_upsert` | Record a pattern, subject to duplicate and restatement checks |
| `pulse_pattern_set_status` | Mark a pattern active or inactive (archives it) |
| `pulse_vault_read` / `pulse_vault_list` | Read a vault note / list all vault notes |
| `pulse_vault_write` / `pulse_vault_append_section` | Write a vault note / upsert a `## heading` section (agent memory) |

Pulse does not reason: these tools expose your data so your agent can.

**Looking for something the user does not already know?** Start with `pulse_longitudinal_profile`, then `pulse_pattern_list` for what is already recorded, then `pulse_query_events` to test a hypothesis. Note that `pulse_change_surface` is the wrong tool for this: what it returns is by construction what the user just did, and they remember doing it. **Answering a question about a specific time?** Orient with `pulse_digest`, then drill in with `pulse_query_events`.

`pulse_pattern_upsert` rejects a proposal that duplicates an existing pattern, or an update that merely restates the one on file. That is deliberate: it is what keeps recorded patterns meaningful rather than an append-only log of the same finding.

#### Semantic search (optional)

By default `pulse_query_events(text=...)` does a substring match. For local semantic ranking, install the extra and enable it:

```bash
pip install pulse-agent[semantic]   # or: uv tool install "pulse-agent[semantic]"
```

Add to `pulse.toml`:

```toml
[semantic]
enabled = true
```

Then run **`pulse embed`** once to backfill embeddings for existing events (re-run after large pulls). The first run downloads a ~30MB local model ([model2vec](https://github.com/MinishLab/model2vec)); nothing leaves your machine and no API key is used. When disabled or the extra is absent, `text=` falls back to substring match.

### MCP resources

| Resource | URI |
| --- | --- |
| Today's digest | `pulse://digest/today` |
| Source coverage | `pulse://coverage` |
| Vault index | `pulse://vault/index` |

### 5. Verify

- Run **`pulse status`** to confirm DB path and event counts.
- Confirm the MCP server process starts without `PulseConfigNotFoundError` or missing-module errors.
- Optional: invoke tool **`pulse_coverage`** or resource **`pulse://digest/today`** from the client if it exposes them.

## Reference

- Human-oriented walkthrough: [Self-Hosting Quickstart](https://pulseagent.dev/docs/self-hosting/quickstart.html).
- Config and env: [Configuration Reference](https://pulseagent.dev/docs/reference/configuration.html) (see *App, CLI, MCP* and *Runtime notes*).

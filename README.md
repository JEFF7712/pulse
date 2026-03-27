# Pulse

A self-hosted, push-first personal intelligence agent. Pulse continuously ingests data from your digital life — email, calendar, purchases, health, media — and proactively surfaces insights through notifications. No app to open. No daily check-ins.

The core philosophy: big data companies already collect and exploit your personal data. Pulse reclaims it, running entirely on your own infrastructure with full transparency into what the agent knows and how it reasons.

## How it works

```
Data Sources (Gmail, Calendar, ...)
        ↓
  Event Store (SQLite)
        ↓
  Analysis Engine ──→ Vault (Obsidian-compatible Markdown)
        ↓
  Notifications (Telegram)
        ↕
  User Corrections
```

1. **Connectors** pull data from your accounts and normalize it into timestamped events
2. **Event Store** persists everything in a local SQLite database
3. **Analysis Engine** generates daily digests and morning briefings
4. **Vault** writes human-readable markdown files you can browse in Obsidian
5. **Notifications** push insights to you via Telegram (more channels planned)
6. **Corrections** let you reply to fix anything the agent gets wrong

## Two ways to run

**Standalone** — Pulse runs as its own service with FastAPI, APScheduler, and Telegram notifications. Good for `docker run` deployments.

**Agent integration** — Pulse exposes an [MCP server](https://modelcontextprotocol.io/) so any compatible agent (Claude Code, OpenClaw, etc.) can query your events, generate digests, and record corrections using its own scheduling and LLM capabilities.

## Setup

**With [uv](https://docs.astral.sh/uv/) (recommended)**

```bash
uv sync
```

Include dev tools (pytest): `uv sync --group dev`.

**With Nix** — from the repo root, `nix develop` drops you into a shell with Python, uv, and a `.venv` kept in sync via `uv sync --group dev`.

**Classic venv** — `python3 -m venv .venv`, activate, then `pip install -e .` (and `pip install pytest` if you run tests). The [self-hosting quickstart](docs/self-hosting/quickstart.md) still documents a pip-oriented path for operators who prefer it.

Copy `.env.example` and set any values you need:

```bash
cp .env.example .env
```

| Variable | Runtime use | Default |
|----------|-------------|---------|
| `PULSE_DATABASE_PATH` | SQLite database path; also determines where OAuth token files are stored | `data/pulse.db` |
| `PULSE_VAULT_PATH` | Markdown vault output directory | `Pulse-Vault` |
| `PULSE_TIMEZONE` | Timezone used for current-day resolution and day boundaries inside jobs | `UTC` |
| `PULSE_TELEGRAM_BOT_TOKEN` | Enables outbound Telegram notifications when paired with chat ID | _(optional)_ |
| `PULSE_TELEGRAM_CHAT_ID` | Destination chat for Telegram notifications | _(optional)_ |
| `PULSE_GOOGLE_CLIENT_ID` | Google OAuth client ID for enabled Google connectors | _(optional)_ |
| `PULSE_GOOGLE_CLIENT_SECRET` | Google OAuth client secret | _(optional)_ |
| `PULSE_SPOTIFY_CLIENT_ID` | Spotify OAuth client ID for the Spotify connector | _(optional)_ |
| `PULSE_SPOTIFY_CLIENT_SECRET` | Spotify OAuth client secret | _(optional)_ |
| `PULSE_ANTHROPIC_API_KEY` | Enables discovery jobs instead of skipping them | _(optional)_ |

Connector toggles and nested connector settings live in `pulse.toml`, not in `.env`. The full runtime config reference is in [`docs/reference/configuration.md`](docs/reference/configuration.md).

Standalone app and CLI commands use `PULSE_DATABASE_PATH`. The MCP server uses `PULSE_DB_PATH`. If you run both surfaces against the same data, point both variables at the same SQLite file.

## Docs

Start with [docs/index.md](docs/index.md), the source-of-truth docs entry for repo readers.

[`/docs/`](/docs/) is the rendered version of that same docs set.

- [Self-hosting quickstart](docs/self-hosting/quickstart.md)
- [Configuration reference](docs/reference/configuration.md)
- [Operations runbook](docs/operations/runbook.md)
- [Connectors index](docs/connectors/index.md)

## Run tests

```bash
uv sync --group dev
uv run pytest
```

Continuous integration (`.github/workflows/ci.yml`) runs `uv sync --group dev --locked` and `uv run pytest` on pushes and pull requests to `main`, on Python 3.12 and 3.13.

## Start the standalone server

```bash
uv run uvicorn --app-dir src pulse.app.main:create_app --factory
```

## Use as an MCP server

Add to your agent's MCP config (e.g. `.claude/settings.json`):

This example uses the MCP server's own env surface, which differs slightly from the standalone app: keep `PULSE_VAULT_PATH`, but use `PULSE_DB_PATH` here instead of `PULSE_DATABASE_PATH`.

```json
{
  "mcpServers": {
    "pulse": {
      "command": "uv",
      "args": ["run", "python", "-m", "pulse.mcp.server"],
      "env": {
        "PULSE_DB_PATH": "/absolute/path/to/pulse.db",
        "PULSE_VAULT_PATH": "/absolute/path/to/Pulse-Vault"
      }
    }
  }
}
```

If `pulse-mcp` is on your `PATH` (after `uv sync`), you can use `"command": "pulse-mcp"` with empty `args` instead.

### Available tools

| Tool | Description |
|------|-------------|
| `pulse_events_for_day` | Query events for a specific date, optionally filtered by source |
| `pulse_ingest_event` | Manually push an event into the store |
| `pulse_correct` | Record a correction or feedback about an insight |
| `pulse_digest` | Generate a daily digest and save it to the vault |
| `pulse_read_digest` | Read an existing digest from the vault |
| `pulse_connector_status` | Check sync state of all connectors |

### Available resources

| Resource | URI |
|----------|-----|
| Today's events | `pulse://events/today` |
| Connector status | `pulse://connectors/status` |

## Project structure

```
src/pulse/
├── app/            # FastAPI server, config, dependencies
├── analysis/       # Summarizer, morning briefing builder
├── connectors/     # Gmail, Calendar, YouTube, Spotify, browser, RSS/Atom feeds, …
├── domain/         # Core types and protocols
├── jobs/           # Scheduled tasks (daily digest, morning briefing)
├── mcp/            # MCP server for agent integration
├── notifications/  # Telegram channel
├── services/       # Business logic (corrections)
├── store/          # SQLite repositories (events, sync state, corrections)
└── vault/          # Markdown renderer and file writer
```

## Design principles

1. **Push-first** — insights come to you as notifications
2. **Zero-effort integration** — connecting data sources takes minutes
3. **Full transparency** — all data stored as human-readable markdown in Obsidian
4. **Extensible** — clean interfaces for connectors, LLM providers, and notification channels
5. **Self-hosted** — runs on your hardware, data stays local

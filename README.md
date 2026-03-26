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

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pip install pytest uvicorn  # for dev
```

Copy `.env.example` and set any values you need:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `PULSE_DATABASE_PATH` | SQLite database location | `data/pulse.db` |
| `PULSE_VAULT_PATH` | Markdown vault directory | `Pulse-Vault` |
| `PULSE_TIMEZONE` | Timezone for scheduling | `UTC` |
| `PULSE_TELEGRAM_BOT_TOKEN` | Telegram bot token | _(optional)_ |
| `PULSE_TELEGRAM_CHAT_ID` | Your Telegram chat ID | _(optional)_ |
| `PULSE_GOOGLE_CLIENT_ID` | Google OAuth client ID | _(optional)_ |
| `PULSE_GOOGLE_CLIENT_SECRET` | Google OAuth client secret | _(optional)_ |

## Run tests

```bash
pytest
```

## Start the standalone server

```bash
uvicorn --app-dir src pulse.app.main:create_app --factory
```

## Use as an MCP server

Add to your agent's MCP config (e.g. `.claude/settings.json`):

```json
{
  "mcpServers": {
    "pulse": {
      "command": "python",
      "args": ["-m", "pulse.mcp.server"],
      "env": {
        "PULSE_DB_PATH": "/absolute/path/to/pulse.db",
        "PULSE_VAULT_PATH": "/absolute/path/to/Pulse-Vault"
      }
    }
  }
}
```

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
├── connectors/     # Data source integrations (Gmail, Calendar)
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

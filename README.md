# Pulse

A self-hosted, push-first personal intelligence agent. Pulse continuously ingests data from your digital life — email, calendar, purchases, health, media — and proactively surfaces insights through notifications. No app to open. No daily check-ins.

The core philosophy: big data companies already collect and exploit your personal data. Pulse reclaims it, running entirely on your own infrastructure with full transparency into what the agent knows and how it reasons.

## How it works

```
Data Sources (Gmail, Calendar, Notion, Linear, Oura, …)
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
5. **Notifications** push insights via Telegram, [ntfy](https://ntfy.sh), [Gotify](https://gotify.net/), email (SMTP), generic JSON webhooks, [Discord](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) / [Slack](https://api.slack.com/messaging/webhooks) incoming webhooks, [Pushover](https://pushover.net/)—configure one or more
6. **Corrections** let you reply to fix anything the agent gets wrong

## Two ways to run

**Standalone** — Pulse runs as its own service with FastAPI, APScheduler, and Telegram notifications. Good for `docker run` deployments.

**Agent integration** — Pulse exposes an [MCP server](https://modelcontextprotocol.io/) so any compatible agent (Claude Code, OpenClaw, etc.) can query your events, generate digests, and record corrections using its own scheduling and LLM capabilities.

## Installation

Install `pulse-agent` from PyPI. The package provides `pulse` and `pulse-mcp` commands.

```bash
pipx install pulse-agent   # recommended — isolated environment
# or
uv tool install pulse-agent
# or
pip install pulse-agent
```

Config defaults to `~/.config/pulse` (config files, `pulse.toml`) and `~/.local/share/pulse` (database, vault, token files). Override the config directory with `PULSE_CONFIG_DIR`.

## Developer setup

**With [uv](https://docs.astral.sh/uv/) (recommended)**

```bash
uv sync
```

Include dev tools (pytest): `uv sync --group dev`.

**With Nix** — from the repo root, `nix develop` drops you into a shell with Python, uv, and a `.venv` kept in sync via `uv sync --group dev`.

**Classic venv** — `python3 -m venv .venv`, activate, then `pip install -e .` (and `pip install pytest` if you run tests).

**Configuration file** — keep paths, secrets, connector blocks, and `[llm]` in **`pulse.toml`**, usually at **`.config/pulse.toml`** in your project (new default). A repo-root **`pulse.toml`** is still read if present and `.config/pulse.toml` does not exist. Override with **`PULSE_CONFIG_FILE`** (path to the TOML file) or **`PULSE_CONFIG_DIR`** (directory containing `pulse.toml`). See `pulse.toml.example`. Run `pulse configure` to edit the resolved file. Environment variables override the file: any `PULSE_*` name maps to the same snake_case root key (for example `PULSE_DATABASE_PATH` → `database_path`). `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` are also applied when the corresponding field is empty. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` are also applied when the corresponding field is empty.

For Docker and shell exports, the same settings are often passed as env vars:

| Variable | Runtime use | Default |
|----------|-------------|---------|
| `PULSE_DATABASE_PATH` | SQLite database path; also determines where OAuth token files are stored | `data/pulse.db` |
| `PULSE_VAULT_PATH` | Markdown vault output directory | `Pulse-Vault` |
| `PULSE_TIMEZONE` | Timezone used for current-day resolution and day boundaries inside jobs | `UTC` |
| `PULSE_TELEGRAM_BOT_TOKEN` | Enables outbound Telegram notifications when paired with chat ID | _(optional)_ |
| `PULSE_TELEGRAM_CHAT_ID` | Destination chat for Telegram notifications | _(optional)_ |
| `PULSE_CORRECTIONS_WEBHOOK_SECRET` | Enables `POST /webhooks/corrections` (Bearer or `X-Pulse-Signature` HMAC); omit to disable the route | _(optional)_ |
| `PULSE_NTFY_TOPIC` | ntfy topic name (public `ntfy.sh` or self-hosted server) | _(optional)_ |
| `PULSE_NTFY_BASE_URL` | ntfy server root URL (default `https://ntfy.sh`) | _(optional)_ |
| `PULSE_NOTIFICATION_WEBHOOK_URL` | POST JSON payloads for any compatible receiver | _(optional)_ |
| `PULSE_DISCORD_WEBHOOK_URL` | Discord server incoming webhook URL | _(optional)_ |
| `PULSE_SLACK_WEBHOOK_URL` | Slack incoming webhook URL | _(optional)_ |
| `PULSE_PUSHOVER_USER_KEY` | Pushover user key (use with API token) | _(optional)_ |
| `PULSE_PUSHOVER_API_TOKEN` | Pushover application API token | _(optional)_ |
| `PULSE_GOTIFY_URL` | Gotify server base URL | _(optional)_ |
| `PULSE_GOTIFY_APP_TOKEN` | Gotify application token | _(optional)_ |
| `PULSE_SMTP_HOST` | SMTP server for email notifications | _(optional)_ |
| `PULSE_SMTP_PORT` | SMTP port (default `587`) | `587` |
| `PULSE_SMTP_USER` / `PULSE_SMTP_PASSWORD` | SMTP auth (optional for local relay) | _(optional)_ |
| `PULSE_SMTP_FROM` / `PULSE_SMTP_TO` | From address and recipient(s); `PULSE_SMTP_TO` can be comma-separated | _(optional)_ |
| `PULSE_SMTP_USE_TLS` | Use STARTTLS after connect (typical for port 587) | `true` |
| `PULSE_SMTP_USE_SSL` | Use implicit TLS (typical for port 465) | `false` |
| `PULSE_GOOGLE_CLIENT_ID` | Google OAuth client ID for enabled Google connectors | _(optional)_ |
| `PULSE_GOOGLE_CLIENT_SECRET` | Google OAuth client secret | _(optional)_ |
| `PULSE_SPOTIFY_CLIENT_ID` | Spotify OAuth client ID for the Spotify connector | _(optional)_ |
| `PULSE_SPOTIFY_CLIENT_SECRET` | Spotify OAuth client secret | _(optional)_ |
| `PULSE_MICROSOFT_CLIENT_ID` / `PULSE_MICROSOFT_CLIENT_SECRET` | Microsoft Graph (Outlook mail / calendar) OAuth | _(optional)_ |
| `PULSE_MICROSOFT_TENANT_ID` | Azure AD tenant (`common` if omitted) | _(optional)_ |
| `PULSE_GITHUB_CLIENT_ID` / `PULSE_GITHUB_CLIENT_SECRET` | GitHub OAuth for the GitHub connector | _(optional)_ |
| `PULSE_GITLAB_CLIENT_ID` / `PULSE_GITLAB_CLIENT_SECRET` | GitLab OAuth (or set `PULSE_GITLAB_TOKEN` for a PAT) | _(optional)_ |
| `PULSE_GITLAB_TOKEN` | GitLab personal access token (skips OAuth when set) | _(optional)_ |
| `PULSE_PLAID_CLIENT_ID` / `PULSE_PLAID_SECRET` | Plaid API credentials for bank transactions | _(optional)_ |
| `PULSE_PLAID_ENV` | `sandbox`, `development`, or `production` | _(optional)_ |
| `PULSE_OURA_CLIENT_ID` / `PULSE_OURA_CLIENT_SECRET` | Oura Cloud API OAuth (or set `PULSE_OURA_PERSONAL_ACCESS_TOKEN`) | _(optional)_ |
| `PULSE_OURA_PERSONAL_ACCESS_TOKEN` | Oura personal access token (skips OAuth when set) | _(optional)_ |
| `PULSE_NOTION_TOKEN` | Notion internal integration secret for the Notion connector | _(optional)_ |
| `PULSE_LINEAR_API_KEY` | Linear personal API key for assigned-issue sync | _(optional)_ |
| `PULSE_ANTHROPIC_API_KEY` | Anthropic API key for `[llm.*]` with `provider = "anthropic"` (or use `anthropic_api_key` in `pulse.toml`) | _(optional)_ |

Connector toggles and nested connector settings live under `[connectors.*]` in `pulse.toml` (not separate per-connector files).

LLM features require **`[llm.summarization]`**, **`[llm.discovery]`**, and/or **`[llm.corrections]`** in `pulse.toml` (see `pulse.toml.example`). Set `[llm] provider` once and use different `model` values per role (e.g. fast summarization + stronger discovery), or set `provider` on each block when mixing vendors. Put API keys in `pulse.toml` (`anthropic_api_key`, `openai_api_key`, `gemini_api_key`) or use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` in the environment. For **up-to-date model id examples** (Claude 4.6 family, GPT-5.4 variants, Gemini 2.5, etc.) and links to each vendor’s model list, see [**LLM provider configuration** in the configuration reference](docs/reference/configuration.md#llm-provider-configuration).

The scheduled `daily_digest` job, `pulse digest`, the homepage **Digest** action, and MCP `pulse_digest` all use the same path: they aggregate stats, then run the digest job with the configured summarization provider when one resolves, otherwise they fall back to the non-LLM summarizer.

The full runtime config reference is in [`docs/reference/configuration.md`](docs/reference/configuration.md).

Standalone app, CLI commands, and the MCP server use `PULSE_DATABASE_PATH`. They resolve the rest of config via `load_config()` (default `.config/pulse.toml`, else repo-root `pulse.toml`, plus process environment overrides).

## Docs

Documentation lives under [docs/index.md](docs/index.md). The deployed site serves the same guides at [`/docs/`](/docs/).

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

This example uses the same config model as the standalone app: `pulse.mcp.server` calls the shared config loader, so use `PULSE_DATABASE_PATH` and `PULSE_VAULT_PATH` here too.

```json
{
  "mcpServers": {
    "pulse": {
      "command": "uv",
      "args": ["run", "python", "-m", "pulse.mcp.server"],
      "env": {
        "PULSE_DATABASE_PATH": "/absolute/path/to/pulse.db",
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
├── connectors/     # Gmail, Calendar, YouTube, Spotify, M365, GitHub, GitLab, Plaid, browser, feeds, …
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

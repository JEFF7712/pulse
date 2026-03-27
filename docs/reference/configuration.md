# Configuration Reference

Pulse builds its runtime configuration from two places:

This reference is part of the canonical docs set rooted at [Pulse Docs](../index.md).

- `pulse.toml` for connector selection and nested connector settings
- environment variables loaded from `.env` via `load_dotenv()` for top-level runtime fields

If the same top-level setting is present in both places, the `PULSE_...` environment variable wins.

## Runtime model

The live config model in `src/pulse/app/config.py` currently exposes these top-level fields:

| Field | Env var | Default | Notes |
| --- | --- | --- | --- |
| `database_path` | `PULSE_DATABASE_PATH` | `data/pulse.db` | SQLite file used by the API, scheduler, and CLI commands. |
| `vault_path` | `PULSE_VAULT_PATH` | `Pulse-Vault` | Output directory for markdown artifacts. |
| `timezone` | `PULSE_TIMEZONE` | `UTC` | Used when resolving the current day for scheduled jobs. |
| `telegram_bot_token` | `PULSE_TELEGRAM_BOT_TOKEN` | unset | Needed before Telegram notifications can be sent. |
| `telegram_chat_id` | `PULSE_TELEGRAM_CHAT_ID` | unset | Paired with the bot token for outbound Telegram delivery. |
| `google_client_id` | `PULSE_GOOGLE_CLIENT_ID` | unset | Enables Google OAuth-backed connectors when paired with the secret. |
| `google_client_secret` | `PULSE_GOOGLE_CLIENT_SECRET` | unset | Keep in `.env`, never in `pulse.toml`. |
| `spotify_client_id` | `PULSE_SPOTIFY_CLIENT_ID` | unset | Enables Spotify OAuth when paired with the secret. |
| `spotify_client_secret` | `PULSE_SPOTIFY_CLIENT_SECRET` | unset | Keep in `.env`, never in `pulse.toml`. |
| `microsoft_client_id` | `PULSE_MICROSOFT_CLIENT_ID` | unset | Microsoft Graph OAuth (mail/calendar). |
| `microsoft_client_secret` | `PULSE_MICROSOFT_CLIENT_SECRET` | unset | Keep in `.env`. |
| `microsoft_tenant_id` | `PULSE_MICROSOFT_TENANT_ID` | unset | Tenant id or `common` when unset. |
| `github_client_id` | `PULSE_GITHUB_CLIENT_ID` | unset | GitHub OAuth. |
| `github_client_secret` | `PULSE_GITHUB_CLIENT_SECRET` | unset | Keep in `.env`. |
| `gitlab_client_id` | `PULSE_GITLAB_CLIENT_ID` | unset | GitLab OAuth (optional if using PAT). |
| `gitlab_client_secret` | `PULSE_GITLAB_CLIENT_SECRET` | unset | Keep in `.env`. |
| `gitlab_token` | `PULSE_GITLAB_TOKEN` | unset | PAT; when set, OAuth is not used. |
| `plaid_client_id` | `PULSE_PLAID_CLIENT_ID` | unset | Plaid Link + transactions. |
| `plaid_secret` | `PULSE_PLAID_SECRET` | unset | Keep in `.env`. |
| `plaid_env` | `PULSE_PLAID_ENV` | unset | `sandbox`, `development`, or `production`. |
| `anthropic_api_key` | `PULSE_ANTHROPIC_API_KEY` | unset | Optional; discovery jobs skip themselves when this is missing. |
| `summarization_model` | `PULSE_SUMMARIZATION_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model id for daily digests, profile structuring, and parts of discovery when an LLM is used. |
| `discovery_model` | `PULSE_DISCOVERY_MODEL` | `claude-sonnet-4-6` | Anthropic model id for the main discovery pass. |

You can also set `summarization_model` and `discovery_model` as top-level keys in `pulse.toml` (same names, string values); environment variables override file values when both are present.

## `pulse.toml`

`config_loader.py` reads `pulse.toml` from the current working directory by default. The file is optional, but when present it is the source of truth for the nested `connectors` map because those settings are not flattened into `PULSE_...` overrides.

The checked-in template matches `pulse.toml.example` (Spotify starts disabled so you opt in after OAuth setup):

```toml
[connectors.gmail]
enabled = true
poll_interval = "15m"

[connectors.calendar]
enabled = true
poll_interval = "30m"

[connectors.youtube]
enabled = true
poll_interval = "1h"

[connectors.spotify]
enabled = false
poll_interval = "30m"
supplementary_interval = "6h"

[connectors.microsoft_mail]
enabled = false
poll_interval = "15m"

[connectors.microsoft_calendar]
enabled = false
poll_interval = "30m"
calendar_id = "primary"

[connectors.github]
enabled = false
poll_interval = "30m"

[connectors.gitlab]
enabled = false
poll_interval = "30m"
gitlab_base_url = "https://gitlab.com"

[connectors.plaid]
enabled = false
poll_interval = "6h"
omit_amounts_in_digest = false

[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"  # or "firefox"

[connectors.feeds]
enabled = false
poll_interval = "1h"
urls = []
```

The full checked-in template is `pulse.toml.example` at the repository root. Set `[connectors.spotify] enabled = true` when you are ready to use Spotify. For RSS/Atom feeds, set `[connectors.feeds] enabled = true` and list URLs in `urls` (see [Connectors Index](../connectors/index.md)). `pulse configure` writes a fresh `pulse.toml` from your answers and may enable more connectors than the example file.

Each connector entry is parsed into a `ConnectorConfig` model with:

- `enabled` defaulting to `true`
- `poll_interval` defaulting to `15m`
- extra connector-specific keys preserved as-is

That extra-field behavior is what allows settings such as `browser = "chrome"`, `db_path`, `urls` for feeds, `calendar_id` / `gitlab_base_url` / `omit_amounts_in_digest`, or Spotify supplementary cadence to live in `pulse.toml` without changing the top-level config loader.

## Secret and token files

The runtime keeps secrets and refresh tokens in different places:

- client credentials stay in `.env` (Google, Spotify, Microsoft, GitHub, GitLab, Plaid, Anthropic, Telegram) — never commit `.env`
- OAuth-style token files beside the database: `google_tokens.json`, `spotify_tokens.json`, `microsoft_tokens.json`, `github_tokens.json`, `gitlab_tokens.json`, `plaid_tokens.json` (Plaid stores `access_token` and transaction sync cursor; treat like other secrets)

Because the token paths are derived from `Path(config.database_path).parent`, changing `PULSE_DATABASE_PATH` also changes where those `*.json` token files are written.

## MCP server vs standalone app

The FastAPI app and CLI load config through `load_dotenv()` and use `PULSE_DATABASE_PATH` for the SQLite file.

The MCP entrypoint (`python -m pulse.mcp.server`) reads **`PULSE_DB_PATH`** and **`PULSE_VAULT_PATH`** from the environment only (see the repository README for a sample agent config). If you run both surfaces against one database, point `PULSE_DATABASE_PATH` and `PULSE_DB_PATH` at the same file path.

The MCP `pulse_digest` tool uses the non-LLM `DailySummarizer` path; it does not read `PULSE_ANTHROPIC_API_KEY`.

## Runtime consequences

- `/health` only checks that the app booted with a valid config object; it does not prove that external connectors are authenticated
- the scheduler always wires `daily_digest`, `morning_briefing`, and discovery jobs, but some of them return a skipped result when Telegram or Anthropic settings are absent
- the **scheduled** `daily_digest` job still fires every 24 hours; when `PULSE_ANTHROPIC_API_KEY` is set it passes an LLM into the digest runner and uses `summarization_model`, otherwise it uses the non-LLM summarizer
- **`pulse digest` and the web “Digest” action** invoke the same digest runner **without** an LLM client, so they always produce the non-LLM summary even when an API key is configured (only the scheduler’s digest job uses the LLM)
- `morning_briefing` needs both Telegram settings to deliver notifications
- discovery jobs need `PULSE_ANTHROPIC_API_KEY`; otherwise they skip with a no-provider message

## Minimal `.env`

```dotenv
PULSE_DATABASE_PATH=data/pulse.db
PULSE_VAULT_PATH=Pulse-Vault
PULSE_TIMEZONE=UTC
PULSE_TELEGRAM_BOT_TOKEN=
PULSE_TELEGRAM_CHAT_ID=
PULSE_GOOGLE_CLIENT_ID=
PULSE_GOOGLE_CLIENT_SECRET=
PULSE_SPOTIFY_CLIENT_ID=
PULSE_SPOTIFY_CLIENT_SECRET=
PULSE_MICROSOFT_CLIENT_ID=
PULSE_MICROSOFT_CLIENT_SECRET=
PULSE_MICROSOFT_TENANT_ID=
PULSE_GITHUB_CLIENT_ID=
PULSE_GITHUB_CLIENT_SECRET=
PULSE_GITLAB_CLIENT_ID=
PULSE_GITLAB_CLIENT_SECRET=
PULSE_GITLAB_TOKEN=
PULSE_PLAID_CLIENT_ID=
PULSE_PLAID_SECRET=
PULSE_PLAID_ENV=
PULSE_ANTHROPIC_API_KEY=
# Optional overrides:
# PULSE_SUMMARIZATION_MODEL=claude-haiku-4-5-20251001
# PULSE_DISCOVERY_MODEL=claude-sonnet-4-6
```

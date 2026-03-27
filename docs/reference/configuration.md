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
| `anthropic_api_key` | `PULSE_ANTHROPIC_API_KEY` | unset | Optional; discovery jobs skip themselves when this is missing. |

## `pulse.toml`

`config_loader.py` reads `pulse.toml` from the current working directory by default. The file is optional, but when present it is the source of truth for the nested `connectors` map because those settings are not flattened into `PULSE_...` overrides.

The repository default looks like this in practice:

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
enabled = true
poll_interval = "30m"
supplementary_interval = "6h"

[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"
```

Each connector entry is parsed into a `ConnectorConfig` model with:

- `enabled` defaulting to `true`
- `poll_interval` defaulting to `15m`
- extra connector-specific keys preserved as-is

That extra-field behavior is what allows settings such as `browser = "chrome"`, `db_path`, or Spotify supplementary cadence to live in `pulse.toml` without changing the top-level config loader.

## Secret and token files

The runtime keeps secrets and refresh tokens in different places:

- client credentials stay in `.env` as `PULSE_GOOGLE_CLIENT_ID`, `PULSE_GOOGLE_CLIENT_SECRET`, `PULSE_SPOTIFY_CLIENT_ID`, `PULSE_SPOTIFY_CLIENT_SECRET`, and `PULSE_ANTHROPIC_API_KEY`
- Google OAuth tokens are persisted beside the database as `google_tokens.json`
- Spotify OAuth tokens are persisted beside the database as `spotify_tokens.json`

Because the token paths are derived from `Path(config.database_path).parent`, changing `PULSE_DATABASE_PATH` also changes where `google_tokens.json` and `spotify_tokens.json` are written.

## Runtime consequences

- `/health` only checks that the app booted with a valid config object; it does not prove that external connectors are authenticated
- the scheduler always wires `daily_digest`, `morning_briefing`, and discovery jobs, but some of them return a skipped result when Telegram or Anthropic settings are absent
- `morning_briefing` needs both Telegram settings to deliver notifications
- discovery jobs need `PULSE_ANTHROPIC_API_KEY`; otherwise they skip with a no-provider message

## Minimal `.env`

```dotenv
PULSE_DATABASE_PATH=data/pulse.db
PULSE_VAULT_PATH=Pulse-Vault
PULSE_TIMEZONE=UTC
PULSE_GOOGLE_CLIENT_ID=
PULSE_GOOGLE_CLIENT_SECRET=
PULSE_SPOTIFY_CLIENT_ID=
PULSE_SPOTIFY_CLIENT_SECRET=
PULSE_ANTHROPIC_API_KEY=
```

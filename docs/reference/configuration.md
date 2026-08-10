# Configuration Reference

**`pulse.toml`** - root keys and `[connectors.*]`. Resolution: **`.config/pulse.toml`** first, else **`./pulse.toml`**, else create under `.config/`. Override path with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** (file = `<dir>/pulse.toml`).

**Precedence:** XDG defaults → `pulse.toml` → **`PULSE_*`** (overrides file).

**Secrets:** Keep OAuth/API values in gitignored `pulse.toml` or env. Connector tables are not overridden by env - edit TOML.

## Installed vs repo layout

PyPI install uses XDG paths:

| Purpose | Default path |
| --- | --- |
| Config file (`pulse.toml`) | `~/.config/pulse` |
| Data files (database, vault, OAuth token files) | `~/.local/share/pulse` |

```bash
PULSE_CONFIG_DIR=/etc/pulse pulse run
```

If `PULSE_CONFIG_DIR` is unset, repo-root `./pulse.toml` still works. Docker: env vars or bind-mount `pulse.toml` into the config dir.

## Top-level fields

`src/pulse/app/config.py` - reference:

| Field | Env var | Default | Notes |
| --- | --- | --- | --- |
| `database_path` | `PULSE_DATABASE_PATH` | `data/pulse.db` | SQLite file used by the API, scheduler, and CLI commands. |
| `vault_path` | `PULSE_VAULT_PATH` | `Pulse-Vault` | Output directory for markdown artifacts. |
| `timezone` | `PULSE_TIMEZONE` | `UTC` | Used when resolving the current day for scheduled jobs. |
| `telegram_bot_token` | `PULSE_TELEGRAM_BOT_TOKEN` | unset | Needed before Telegram notifications can be sent. |
| `telegram_chat_id` | `PULSE_TELEGRAM_CHAT_ID` | unset | Paired with the bot token for outbound Telegram delivery. |
| `ntfy_topic` | `PULSE_NTFY_TOPIC` | unset | ntfy topic; set to enable push via [ntfy.sh](https://ntfy.sh) or your own server. |
| `ntfy_base_url` | `PULSE_NTFY_BASE_URL` | unset | ntfy server root (defaults to `https://ntfy.sh` when topic is set). |
| `notification_webhook_url` | `PULSE_NOTIFICATION_WEBHOOK_URL` | unset | HTTPS URL that receives JSON `POST` bodies for each outbound notification. |
| `discord_webhook_url` | `PULSE_DISCORD_WEBHOOK_URL` | unset | Discord incoming webhook URL (embed per notification). |
| `slack_webhook_url` | `PULSE_SLACK_WEBHOOK_URL` | unset | Slack incoming webhook URL (`text` payload). |
| `pushover_user_key` | `PULSE_PUSHOVER_USER_KEY` | unset | Pushover user key; enable Pushover only when both user key and API token are set. |
| `pushover_api_token` | `PULSE_PUSHOVER_API_TOKEN` | unset | Pushover application API token from the Pushover dashboard. |
| `gotify_url` | `PULSE_GOTIFY_URL` | unset | Gotify server base URL (no trailing path). |
| `gotify_app_token` | `PULSE_GOTIFY_APP_TOKEN` | unset | Gotify application token; enable Gotify only when both URL and token are set. |
| `smtp_host` | `PULSE_SMTP_HOST` | unset | Outbound SMTP host for email notifications. |
| `smtp_port` | `PULSE_SMTP_PORT` | `587` | SMTP port (`587` + STARTTLS is default; use `465` with `smtp_use_ssl`). |
| `smtp_user` | `PULSE_SMTP_USER` | unset | SMTP username if the server requires auth. |
| `smtp_password` | `PULSE_SMTP_PASSWORD` | unset | SMTP password. |
| `smtp_from` | `PULSE_SMTP_FROM` | unset | `From` address for notification email. |
| `smtp_to` | `PULSE_SMTP_TO` | unset | Recipient(s); comma-separated for multiple. Email channel is enabled when `smtp_host`, `smtp_from`, and `smtp_to` are all set. |
| `smtp_use_tls` | `PULSE_SMTP_USE_TLS` | `true` | Use STARTTLS after connect (typical for submission on port 587). |
| `smtp_use_ssl` | `PULSE_SMTP_USE_SSL` | `false` | Use implicit TLS (`SMTP_SSL`, typical for port 465). |
| `notify_on_job_failure` | `PULSE_NOTIFY_ON_JOB_FAILURE` | `false` | When `true`, Pulse sends an **operations** notification when a **scheduled** job throws: hourly aggregation or a connector pull. No alert is sent if no notification channel is configured. |
| `job_failure_alert_cooldown` | `PULSE_JOB_FAILURE_ALERT_COOLDOWN` | `6h` | Minimum time between failure alerts for the **same** job key (format like connector `poll_interval`: `30m`, `2h`, `1d`). |
| `google_client_id` | `PULSE_GOOGLE_CLIENT_ID` | unset | Enables Google OAuth-backed connectors when paired with the secret. |
| `google_client_secret` | `PULSE_GOOGLE_CLIENT_SECRET` | unset | OAuth secret (env or gitignored TOML). |

**Google OAuth on a headless server or over SSH:** `pulse onboard` / `pulse configure` starts a small **localhost** redirect server. With no GUI, Pulse skips auto-opening a browser and prints the authorize URL. If you open that URL on your **laptop**, Google redirects to **your laptop’s** `localhost` - so you must **forward the callback port** to the server, e.g. `ssh -L 8765:localhost:8765 user@server` (use the port Pulse prints; default fallback is **8765** when no browser is found). Optional env: `PULSE_GOOGLE_OAUTH_PORT` (fixed port), `PULSE_GOOGLE_OAUTH_FALLBACK_PORT` (default `8765` when auto-detecting headless), `PULSE_OAUTH_NO_BROWSER=1` (never call `webbrowser`). If Google returns **redirect_uri_mismatch**, add the exact `http://localhost:<port>/` URI in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) for your OAuth client.
| `spotify_client_id` | `PULSE_SPOTIFY_CLIENT_ID` | unset | Enables Spotify OAuth when paired with the secret. |
| `spotify_client_secret` | `PULSE_SPOTIFY_CLIENT_SECRET` | unset | OAuth secret. |
| `github_client_id` | `PULSE_GITHUB_CLIENT_ID` | unset | GitHub OAuth. |
| `github_client_secret` | `PULSE_GITHUB_CLIENT_SECRET` | unset | OAuth secret. |
| `plaid_client_id` | `PULSE_PLAID_CLIENT_ID` | unset | Plaid Link + transactions. |
| `plaid_secret` | `PULSE_PLAID_SECRET` | unset | Plaid secret. |
| `plaid_env` | `PULSE_PLAID_ENV` | unset | `sandbox`, `development`, or `production`. |
| `oura_client_id` | `PULSE_OURA_CLIENT_ID` | unset | Oura OAuth (optional if using PAT). |
| `oura_client_secret` | `PULSE_OURA_CLIENT_SECRET` | unset | OAuth secret. |
| `oura_personal_access_token` | `PULSE_OURA_PERSONAL_ACCESS_TOKEN` | unset | Oura personal access token; when set, OAuth is not used. |

## `pulse.toml`

Loader: `.config/pulse.toml` → `./pulse.toml` → default `.config/` for new saves. Optional file; **`PULSE_*`** overrides root scalars only. Template = repo **`pulse.toml.example`** (all connectors `enabled = false` in the template; the example may enable a core spine by default).

```toml
[connectors.gmail]
enabled = false
poll_interval = "15m"

[connectors.calendar]
enabled = false
poll_interval = "30m"

[connectors.youtube]
enabled = false
poll_interval = "1h"

[connectors.spotify]
enabled = false
poll_interval = "30m"
supplementary_interval = "6h"

[connectors.github]
enabled = false
poll_interval = "30m"

[connectors.plaid]
enabled = false
poll_interval = "6h"
omit_amounts_in_digest = false

[connectors.browser]
enabled = false
poll_interval = "15m"
browser = "chrome"  # or "firefox"

[connectors.oura]
enabled = false
poll_interval = "6h"
```

**`ConnectorConfig`:** `enabled` defaults false, `poll_interval` default `15m`; extra keys (`browser`, `calendar_id`, …) pass through.

## Optional `[semantic]`

Local embedding ranking for `pulse_query_events(text=...)`. Off by default; no base-package dependency. Install the extra first: `pip install pulse-agent[semantic]` (or `uv tool install "pulse-agent[semantic]"`).

| Field | Default | Notes |
| --- | --- | --- |
| `enabled` | `false` | When `true`, text queries rank by cosine similarity over stored embeddings. |
| `model` | `minishlab/potion-base-32M` | [model2vec](https://github.com/MinishLab/model2vec) model id; first use downloads ~30MB locally. |

```toml
[semantic]
enabled = true
# model = "minishlab/potion-base-32M"
```

After enabling, run **`pulse embed`** once to backfill embeddings for existing events (re-run after large pulls). When disabled or the extra is absent, `text=` falls back to substring match. See [MCP agent setup](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html).

## Optional `[discovery]`

Long-horizon pattern discovery via **your** agent CLI - Pulse does not call an LLM API. Requires a configured notification channel (Telegram, ntfy, …).

Discovery looks for structure the user **cannot see about themselves**, not for a summary of the week. You already remember your week; what you cannot hold in your head is how the mix of what you do has drifted over a year, whether your interests rotate rather than accumulate, how far your sleep phase has moved, what actually holds your attention versus what you only ever touch in fragments, and what quietly stopped. `pulse_longitudinal_profile` computes all of that deterministically; the agent interprets it.

You are notified **only** when the agent records a genuinely new or changed pattern in the vault. Prose that records nothing produces silence.

| Field | Default | Notes |
| --- | --- | --- |
| `enabled` | `false` | When `true`, `pulse run` schedules the discovery pass. |
| `command` | `["claude", "-p"]` | Headless agent argv; must be on `PATH`. |
| `prompt` | (built-in discovery prompt) | Points the agent at `pulse_longitudinal_profile` and `pulse_pattern_*`. |
| `at` | `"09:00"` | Local time in config `timezone`. |
| `timeout_seconds` | `900` | Subprocess timeout. |
| `interval_days` | `7` | Structure over months does not change daily; re-deriving it every morning only rediscovers what is already on file. |
| `history_days` | `400` | How far back the profile reaches. A year lets rotation and seasonality show; a quarter is the practical minimum. |

```toml
[discovery]
enabled = true
command = ["claude", "-p"]
at = "09:00"
```

There is deliberately **no gate on recent activity**. A quiet week is not a reason to skip a pass - the profile can shift while nothing notable happens, and a busy week is no evidence that anything is newly knowable. What keeps you from being spammed is the novelty check on the agent's output, not a check on its input.

Force a pass with **`pulse review`**. Each run spends your agent subscription. Enabling `[discovery]` alongside `[semantic]` also registers a 6-hourly embedding job.

> **Migrating from `[proactive]`:** the section was removed and Pulse fails to start if it is still present. Rename it to `[discovery]`; `command`, `prompt`, `at` and `timeout_seconds` carry over. Replace a review-style prompt with a discovery-style one, or drop `prompt` to take the built-in default.

## Token files

OAuth refresh tokens live next to the DB: `google_tokens.json`, `spotify_tokens.json`, `github_tokens.json`, `plaid_tokens.json`. Directory = parent of **`database_path`** - changing **`PULSE_DATABASE_PATH`** moves them.

## App, CLI, MCP

Same **`load_config()`**: `pulse.toml` + env. The standalone app, CLI, and MCP server share the same database and vault paths.

**MCP-only:** the `pulse-mcp` process calls **`load_config(require_files=True)`**, so a **`pulse.toml` file must exist** at the resolved location before the server starts. If your agent spawns MCP with an unexpected working directory, set **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** in the MCP server `env` so Pulse finds the same config as `pulse` / `uvicorn`.

## Runtime notes

- **`/health`** - process up; not connector proof.
- Scheduler registers hourly aggregation and per-connector pull jobs (see [Runbook](https://pulseagent.dev/docs/operations/runbook.html)).
- Operations notifications: sent when a scheduled job fails and a notify channel is configured (`notify_on_job_failure`).

## Env-only deploy

Docker/systemd/CI: export **`PULSE_*`**. Example:

```bash
export PULSE_DATABASE_PATH=data/pulse.db
export PULSE_VAULT_PATH=Pulse-Vault
export PULSE_TIMEZONE=UTC
```

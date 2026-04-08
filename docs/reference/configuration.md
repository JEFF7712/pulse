# Configuration Reference

**`pulse.toml`** — root keys, `[connectors.*]`, `[llm]` / `[llm.*]`. Resolution: **`.config/pulse.toml`** first, else **`./pulse.toml`**, else create under `.config/`. Override path with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** (file = `<dir>/pulse.toml`).

**Precedence:** XDG defaults → `pulse.toml` → **`PULSE_*`** (overrides file) → **`ANTHROPIC_API_KEY`** / **`OPENAI_API_KEY`** / **`GEMINI_API_KEY`** only to fill still-empty matching fields.

**Secrets:** Keep OAuth/API values in gitignored `pulse.toml` or env. Connector tables are not overridden by env—edit TOML.

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

`src/pulse/app/config.py` — reference:

| Field | Env var | Default | Notes |
| --- | --- | --- | --- |
| `database_path` | `PULSE_DATABASE_PATH` | `data/pulse.db` | SQLite file used by the API, scheduler, and CLI commands. |
| `vault_path` | `PULSE_VAULT_PATH` | `Pulse-Vault` | Output directory for markdown artifacts. |
| `timezone` | `PULSE_TIMEZONE` | `UTC` | Used when resolving the current day for scheduled jobs. |
| `telegram_bot_token` | `PULSE_TELEGRAM_BOT_TOKEN` | unset | Needed before Telegram notifications can be sent. |
| `telegram_chat_id` | `PULSE_TELEGRAM_CHAT_ID` | unset | Paired with the bot token for outbound Telegram delivery. |
| `corrections_webhook_secret` | `PULSE_CORRECTIONS_WEBHOOK_SECRET` | unset | When set, enables `POST /webhooks/corrections` with `Authorization: Bearer <secret>` or `X-Pulse-Signature: sha256=<hmac>` (HMAC-SHA256 of the raw body). JSON body: `context_id`, `message`. Returns 404 when unset. |
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
| `google_client_id` | `PULSE_GOOGLE_CLIENT_ID` | unset | Enables Google OAuth-backed connectors when paired with the secret. |
| `google_client_secret` | `PULSE_GOOGLE_CLIENT_SECRET` | unset | OAuth secret (env or gitignored TOML). |

**Google OAuth on a headless server or over SSH:** `pulse onboard` / `pulse configure` starts a small **localhost** redirect server. With no GUI, Pulse skips auto-opening a browser and prints the authorize URL. If you open that URL on your **laptop**, Google redirects to **your laptop’s** `localhost` — so you must **forward the callback port** to the server, e.g. `ssh -L 8765:localhost:8765 user@server` (use the port Pulse prints; default fallback is **8765** when no browser is found). Optional env: `PULSE_GOOGLE_OAUTH_PORT` (fixed port), `PULSE_GOOGLE_OAUTH_FALLBACK_PORT` (default `8765` when auto-detecting headless), `PULSE_OAUTH_NO_BROWSER=1` (never call `webbrowser`). If Google returns **redirect_uri_mismatch**, add the exact `http://localhost:<port>/` URI in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) for your OAuth client.
| `spotify_client_id` | `PULSE_SPOTIFY_CLIENT_ID` | unset | Enables Spotify OAuth when paired with the secret. |
| `spotify_client_secret` | `PULSE_SPOTIFY_CLIENT_SECRET` | unset | OAuth secret. |
| `microsoft_client_id` | `PULSE_MICROSOFT_CLIENT_ID` | unset | Microsoft Graph OAuth (mail/calendar). |
| `microsoft_client_secret` | `PULSE_MICROSOFT_CLIENT_SECRET` | unset | OAuth secret. |
| `microsoft_tenant_id` | `PULSE_MICROSOFT_TENANT_ID` | unset | Tenant id or `common` when unset. |
| `github_client_id` | `PULSE_GITHUB_CLIENT_ID` | unset | GitHub OAuth. |
| `github_client_secret` | `PULSE_GITHUB_CLIENT_SECRET` | unset | OAuth secret. |
| `gitlab_client_id` | `PULSE_GITLAB_CLIENT_ID` | unset | GitLab OAuth (optional if using PAT). |
| `gitlab_client_secret` | `PULSE_GITLAB_CLIENT_SECRET` | unset | OAuth secret. |
| `gitlab_token` | `PULSE_GITLAB_TOKEN` | unset | PAT; when set, OAuth is not used. |
| `plaid_client_id` | `PULSE_PLAID_CLIENT_ID` | unset | Plaid Link + transactions. |
| `plaid_secret` | `PULSE_PLAID_SECRET` | unset | Plaid secret. |
| `plaid_env` | `PULSE_PLAID_ENV` | unset | `sandbox`, `development`, or `production`. |
| `oura_client_id` | `PULSE_OURA_CLIENT_ID` | unset | Oura OAuth (optional if using PAT). |
| `oura_client_secret` | `PULSE_OURA_CLIENT_SECRET` | unset | OAuth secret. |
| `oura_personal_access_token` | `PULSE_OURA_PERSONAL_ACCESS_TOKEN` | unset | Oura personal access token; when set, OAuth is not used. |
| `notion_token` | `PULSE_NOTION_TOKEN` | unset | Notion internal integration secret for workspace search / database query. |
| `linear_api_key` | `PULSE_LINEAR_API_KEY` | unset | Linear personal API key; syncs issues assigned to the key’s user. |
| `anthropic_api_key` | `PULSE_ANTHROPIC_API_KEY` | unset | API key for `[llm.*]` roles with `provider = "anthropic"`; environment fallback `ANTHROPIC_API_KEY` when empty. |
| `openai_api_key` | `PULSE_OPENAI_API_KEY` | unset | API key for `[llm.*]` with `provider = "openai"` or `"ollama"` (OpenAI-compatible); environment fallback `OPENAI_API_KEY` when empty. |
| `gemini_api_key` | `PULSE_GEMINI_API_KEY` | unset | API key for `[llm.*]` with `provider = "gemini"`; environment fallback `GEMINI_API_KEY` when empty. |
| `llm` | _(set in `pulse.toml`)_ | unset | Nested per-role provider config for `summarization`, `discovery`, and `corrections`; supports `anthropic`, `openai`, `gemini`, and `ollama`. |

### LLM blocks

**`[llm.summarization]`**, **`[llm.discovery]`**, **`[llm.corrections]`** — each has `model`, optional `provider`, `base_url`. Set **`[llm] provider`** / **`base_url`** once; per-role `base_url` inherits only for **`openai`** and **`ollama`**. One configured role can cover both summarization and discovery if the other is omitted.

Providers: **`anthropic`**, **`openai`**, **`gemini`**, **`ollama`**. Keys in TOML or **`ANTHROPIC_API_KEY`** / **`OPENAI_API_KEY`** / **`GEMINI_API_KEY`** / **`PULSE_*`**. `ollama` uses OpenAI-compatible transport; placeholder API key ok if unset.

Discovery, scheduled jobs, and MCP `pulse_discovery` need a resolved LLM role (summarization + discovery; they may share one block). **`pulse init`** profile structuring uses Anthropic only when summarization or discovery is already Anthropic.

**Corrections:** `[llm.corrections]` first, else inherits discovery; if neither resolves, corrections are stored but vault application is skipped.

**Anthropic example** ([model ids](https://docs.anthropic.com/en/docs/about-claude/models/overview)):

```toml
[llm]
provider = "anthropic"

[llm.summarization]
model = "claude-haiku-4-5-20251001"

[llm.discovery]
model = "claude-opus-4-6"
```

**OpenAI** ([models](https://platform.openai.com/docs/models) — confirm ids in your account):

```toml
[llm]
provider = "openai"

[llm.summarization]
model = "gpt-5.4-nano"

[llm.discovery]
model = "gpt-5.4"
```

**Gemini** ([models](https://ai.google.dev/gemini-api/docs/models)):

```toml
[llm]
provider = "gemini"

[llm.summarization]
model = "gemini-2.5-flash"

[llm.discovery]
model = "gemini-2.5-pro"
```

**Mixed providers:**

```toml
[llm.summarization]
provider = "ollama"
model = "llama3.3"
base_url = "http://localhost:11434/v1"

[llm.discovery]
provider = "anthropic"
model = "claude-sonnet-4-6"

[llm.corrections]
provider = "openai"
model = "gpt-5.4-mini"
```

## `pulse.toml`

Loader: `.config/pulse.toml` → `./pulse.toml` → default `.config/` for new saves. Optional file; **`PULSE_*`** overrides root scalars only. Template = repo **`pulse.toml.example`** (all connectors `enabled = false`).

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

[connectors.linear]
enabled = false
poll_interval = "30m"

[connectors.gitlab]
enabled = false
poll_interval = "30m"
gitlab_base_url = "https://gitlab.com"

[connectors.plaid]
enabled = false
poll_interval = "6h"
omit_amounts_in_summary = false

[connectors.browser]
enabled = false
poll_interval = "15m"
browser = "chrome"  # or "firefox"

[connectors.feeds]
enabled = false
poll_interval = "1h"
urls = []
```

Optional commented **`[llm.corrections]`** in the example — omit to inherit discovery’s model.

**`ConnectorConfig`:** `enabled` defaults false, `poll_interval` default `15m`; extra keys (`browser`, `urls`, `calendar_id`, …) pass through.

## Companion app

| Env var | Default | Notes |
| --- | --- | --- |
| `PULSE_COMPANION_TOKEN` | unset | Bearer for companion API; or `companion_token` in TOML. Unset = no auth check (avoid in prod). |
| `PULSE_FCM_SERVICE_ACCOUNT_PATH` | unset | Firebase JSON for FCM; unset skips push. |

Enable companion:

```toml
[connectors.companion]
enabled = true
# The companion app pushes location and health events to /webhooks/companion.
# Set companion_token here or PULSE_COMPANION_TOKEN in the environment for API auth.
```

Disabled → `/webhooks/companion` not mounted.

When the companion connector (and API routes) are enabled, the mobile app reads patterns via **`GET /api/insights`** and **`GET /api/insights/{id}`** using the same **`X-Pulse-Token`** / `companion_token` as corrections and device registration.

## Token files

OAuth refresh tokens live next to the DB: `google_tokens.json`, `spotify_tokens.json`, `microsoft_tokens.json`, `github_tokens.json`, `gitlab_tokens.json`, `plaid_tokens.json`. Directory = parent of **`database_path`** — changing **`PULSE_DATABASE_PATH`** moves them.

## App, CLI, MCP

Same **`load_config()`**: `pulse.toml` + env. Telegram, MCP **`pulse_correct`**, and **`POST /webhooks/corrections`** share the corrections pipeline (store text, `correction_applications` row, optional vault edit when LLM + target resolve). MCP **`pulse_discovery`** matches CLI/scheduler discovery.

**MCP-only:** the `pulse-mcp` process calls **`load_config(require_files=True)`**, so a **`pulse.toml` file must exist** at the resolved location before the server starts. If your agent spawns MCP with an unexpected working directory, set **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** in the MCP server `env` so Pulse finds the same config as `pulse` / `uvicorn`.

## Runtime notes

- **`/health`** — process up; not connector/LLM proof.
- Scheduler registers aggregation and discovery jobs; discovery **skips** when no LLM role resolves (see [Runbook](../operations/runbook.md)).
- Discovery: per-source summaries use the summarization role; the main insight pass uses the discovery role; either may inherit the other when one block is omitted.
- Insight notifications: sent when discovery emits them and a notify channel is configured.

## Env-only deploy

Docker/systemd/CI: export **`PULSE_*`** (+ optional vendor API keys). Example:

```bash
export PULSE_DATABASE_PATH=data/pulse.db
export PULSE_VAULT_PATH=Pulse-Vault
export PULSE_TIMEZONE=UTC
```

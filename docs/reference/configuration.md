# Configuration Reference

Pulse builds its runtime configuration from two places:

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
| `anthropic_api_key` | `PULSE_ANTHROPIC_API_KEY` | unset | Legacy single-provider fallback for profile structuring, digest summarization, and discovery when `[llm.*]` role config is not set. Uses fixed ids `claude-haiku-4-5-20251001` (summarization) and `claude-sonnet-4-6` (discovery and corrections fallback when no `[llm.*]` is set) — customize models only via `[llm.*]`. |
| `llm` | _(set in `pulse.toml`)_ | unset | Nested per-role provider config for `summarization`, `discovery`, and `corrections`; supports `anthropic`, `openai`, `gemini`, and `ollama`. |

### LLM provider configuration

Pulse supports two LLM configuration paths:

1. **Legacy Anthropic fallback** via `PULSE_ANTHROPIC_API_KEY` only (no per-model env vars). Pulse uses `claude-haiku-4-5-20251001` for summarization and `claude-sonnet-4-6` for discovery (see [Anthropic models](https://docs.anthropic.com/en/docs/about-claude/models/overview)). This is also what `pulse init` uses for profile structuring.
2. **Per-role provider config** in `pulse.toml` via `[llm.summarization]`, `[llm.discovery]`, and `[llm.corrections]`. Each block sets `model` and optional `provider` and `base_url`. You can set **`[llm] provider`** (and optional **`[llm] base_url`**) once, then list only **`model`** under each role — for example Haiku for digest summarization and Opus for discovery on Anthropic, or a smaller vs larger OpenAI model id. If you configure only one of summarization/discovery, Pulse reuses it for both summarization and discovery. **`[llm] base_url`** is inherited only for `openai` and `ollama` roles so a local Ollama URL is not applied to Anthropic or Gemini.

Supported providers are `anthropic`, `openai`, `gemini`, and `ollama`.

**Same provider, different models** (set `ANTHROPIC_API_KEY` in `.env`). These ids match the current Claude API family ([Anthropic model overview](https://docs.anthropic.com/en/docs/about-claude/models/overview)): Haiku 4.5 for fast summarization, Opus 4.6 for heavier discovery.

```toml
[llm]
provider = "anthropic"

[llm.summarization]
model = "claude-haiku-4-5-20251001"

[llm.discovery]
model = "claude-opus-4-6"
```

**OpenAI example** — flagship `gpt-5.4` plus smaller `gpt-5.4-nano` / `gpt-5.4-mini` as documented on [OpenAI Models](https://platform.openai.com/docs/models) (verify ids in your project before deploying):

```toml
[llm]
provider = "openai"

[llm.summarization]
model = "gpt-5.4-nano"

[llm.discovery]
model = "gpt-5.4"
```

**Gemini example** (set `GEMINI_API_KEY`; stable ids from [Gemini models](https://ai.google.dev/gemini-api/docs/models)):

```toml
[llm]
provider = "gemini"

[llm.summarization]
model = "gemini-2.5-flash"

[llm.discovery]
model = "gemini-2.5-pro"
```

**Mixed providers** (each role supplies its own `provider`):

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

Provider API keys come from standard environment variables, not `PULSE_...` names:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

`ollama` uses the OpenAI-compatible transport and defaults to a placeholder key when no `OPENAI_API_KEY` is set.

Corrections use a different fallback chain than digest/discovery creation: `llm.corrections` is used first, then `llm.discovery`, then the legacy `PULSE_ANTHROPIC_API_KEY` fallback with the same fixed Sonnet model id used for discovery. In short: corrections -> discovery -> legacy `PULSE_ANTHROPIC_API_KEY` fallback.

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

The example file also includes a commented `llm.corrections` block. Leave it out if you want corrections to inherit discovery behavior; add it when correction interpretation should use a different provider or model than discovery.

Each connector entry is parsed into a `ConnectorConfig` model with:

- `enabled` defaulting to `true`
- `poll_interval` defaulting to `15m`
- extra connector-specific keys preserved as-is

That extra-field behavior is what allows settings such as `browser = "chrome"`, `db_path`, `urls` for feeds, `calendar_id` / `gitlab_base_url` / `omit_amounts_in_digest`, or Spotify supplementary cadence to live in `pulse.toml` without changing the top-level config loader.

## Companion app

The companion mobile app pushes location and health events to the Pulse backend via a shared-secret webhook. Two environment variables control this integration:

| Env var | Default | Notes |
| --- | --- | --- |
| `PULSE_COMPANION_TOKEN` | unset | Shared secret for app ↔ server authentication. Set this in `.env`; requests without a matching `Authorization: Bearer <token>` header are rejected with HTTP 401. Leave unset to disable token enforcement (not recommended in production). |
| `PULSE_FCM_SERVICE_ACCOUNT_PATH` | unset | Path to the Firebase service account JSON file used to send FCM push notifications to companion app users. Required for push delivery; notifications are silently skipped when unset. |

Enable the companion connector in `pulse.toml` to mount the webhook route and allow the app to send events:

```toml
[connectors.companion]
enabled = true
# The companion app pushes location and health events to /webhooks/companion.
# Set PULSE_COMPANION_TOKEN in .env to enable API auth.
```

When `[connectors.companion]` is disabled (the default), the `/webhooks/companion` route is not mounted and companion events are not accepted.

## Secret and token files

The runtime keeps secrets and refresh tokens in different places:

- client credentials stay in `.env` (Google, Spotify, Microsoft, GitHub, GitLab, Plaid, Telegram, plus any provider API keys such as Anthropic/OpenAI/Gemini) — never commit `.env`
- OAuth-style token files beside the database: `google_tokens.json`, `spotify_tokens.json`, `microsoft_tokens.json`, `github_tokens.json`, `gitlab_tokens.json`, `plaid_tokens.json` (Plaid stores `access_token` and transaction sync cursor; treat like other secrets)

Because the token paths are derived from `Path(config.database_path).parent`, changing `PULSE_DATABASE_PATH` also changes where those `*.json` token files are written.

## MCP server vs standalone app

The FastAPI app, CLI, and MCP entrypoint all call the same `load_config()` path. MCP server now loads the same `pulse.toml` + `.env` config path as the app/CLI, so corrections behavior is driven by the same `PULSE_DATABASE_PATH`, `PULSE_VAULT_PATH`, and `[llm.*]` settings.

That matters for the corrections workflow:

- Telegram replies and MCP `pulse_correct` calls always store the raw correction text in `corrections.message_text`; authenticated `POST /webhooks/corrections` requests do the same
- both surfaces also initialize the `correction_applications` table and record the correction status there (`applied`, `needs_review`, `skipped`, or `failed`)
- when a corrections provider is configured, the interpreter may apply one bounded vault update to the resolved target (daily digest note append, pattern notes/status update, `profile.md` learned corrections section replace, or `routines.md` correction updates section replace)
- when no corrections provider is configured, the raw correction is still stored and the audit/status row explains that application was skipped

The MCP `pulse_digest` tool uses the same aggregation + digest job path as the CLI and scheduler, including the configured summarization provider when one resolves.

## Runtime consequences

- `/health` only checks that the app booted with a valid config object; it does not prove that external connectors are authenticated
- the scheduler always wires `daily_digest`, `morning_briefing`, and discovery jobs, but some of them return a skipped result when no notification channel or discovery-provider settings are configured
- the **scheduled** `daily_digest` job still fires every 24 hours; when a summarization provider is configured it passes an LLM into the digest runner, otherwise it uses the non-LLM summarizer
- `pulse digest`, the web **Digest** action, and MCP `pulse_digest` use that same summarization-provider path (aggregate first, then digest); when no provider resolves, all of them fall back to the non-LLM summarizer
- `morning_briefing` uses the same summarization LLM path as the daily digest (then sends the briefing text); it needs at least one outbound channel among Telegram, ntfy, Gotify, SMTP email, generic webhook, Discord webhook, Slack webhook, or Pushover (user key + API token together); when several are set, Pulse broadcasts the same notification to all of them
- discovery jobs resolve the same way as digest/discovery provider creation: a single configured summarization/discovery role is reused for both, otherwise Pulse uses the legacy `PULSE_ANTHROPIC_API_KEY` fallback; if neither path resolves, discovery skips with a no-provider message
- corrections application needs `correction_applications`, a vault path, and a corrections provider resolved from `llm.corrections`, then `llm.discovery`, then the legacy Anthropic fallback; otherwise the system keeps the raw correction and records a skipped or needs-review status instead of editing vault files

## Minimal `.env`

```dotenv
PULSE_DATABASE_PATH=data/pulse.db
PULSE_VAULT_PATH=Pulse-Vault
PULSE_TIMEZONE=UTC
PULSE_TELEGRAM_BOT_TOKEN=
PULSE_TELEGRAM_CHAT_ID=
PULSE_CORRECTIONS_WEBHOOK_SECRET=
PULSE_NTFY_TOPIC=
PULSE_NTFY_BASE_URL=
PULSE_NOTIFICATION_WEBHOOK_URL=
PULSE_DISCORD_WEBHOOK_URL=
PULSE_SLACK_WEBHOOK_URL=
PULSE_PUSHOVER_USER_KEY=
PULSE_PUSHOVER_API_TOKEN=
PULSE_GOTIFY_URL=
PULSE_GOTIFY_APP_TOKEN=
PULSE_SMTP_HOST=
PULSE_SMTP_PORT=587
PULSE_SMTP_USER=
PULSE_SMTP_PASSWORD=
PULSE_SMTP_FROM=
PULSE_SMTP_TO=
PULSE_SMTP_USE_TLS=true
PULSE_SMTP_USE_SSL=false
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
# Legacy single-provider fallback:
PULSE_ANTHROPIC_API_KEY=
# Per-role provider API keys (used by [llm.*] in pulse.toml):
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

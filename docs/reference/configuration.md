# Configuration Reference

Pulse builds its runtime configuration primarily from a **TOML file named `pulse.toml`**, by default at **`.config/pulse.toml`** in the current working directory. A **repo-root `pulse.toml`** is still used when that path does not exist but `./pulse.toml` does (fallback layout). Set **`PULSE_CONFIG_FILE`** to point at a specific TOML file, or **`PULSE_CONFIG_DIR`** if the file lives at ``<dir>/pulse.toml``. The file holds root keys (paths, secrets, notifications, OAuth clients, LLM API keys), `[connectors.*]` blocks, and `[llm]` / `[llm.*]`.

Merge order: values from the resolved `pulse.toml` file, then **`PULSE_*`** environment variables (which override the file), then **`ANTHROPIC_API_KEY`**, **`OPENAI_API_KEY`**, and **`GEMINI_API_KEY`** only for the matching field when that field is still empty after the previous steps. Pulse does **not** read a `.env` file; set variables in your shell, process manager, or container instead.

## Installed vs repo-checkout layout

When you install `pulse-agent` from PyPI, config and data live under standard XDG directories rather than inside the repository:

| Purpose | Default path |
| --- | --- |
| Config files (`pulse.toml`, `.env`) | `~/.config/pulse` |
| Data files (database, vault, OAuth token files) | `~/.local/share/pulse` |

`PULSE_CONFIG_DIR` overrides the config directory. Set it when you want Pulse to read config from a non-default location (for example a Docker bind-mount or a shared NFS path):

```bash
PULSE_CONFIG_DIR=/etc/pulse pulse run
```

Repo-root `.env` and `pulse.toml` lookup still works as a compatibility fallback when `PULSE_CONFIG_DIR` is not set and the current working directory looks like a checkout (i.e. a `pulse.toml` or `.env` exists there). This means existing developer workflows and Docker setups using `--env-file` continue to work without change.

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
| `google_client_secret` | `PULSE_GOOGLE_CLIENT_SECRET` | unset | Treat as a secret; keep `pulse.toml` gitignored or inject via env in CI. |
| `spotify_client_id` | `PULSE_SPOTIFY_CLIENT_ID` | unset | Enables Spotify OAuth when paired with the secret. |
| `spotify_client_secret` | `PULSE_SPOTIFY_CLIENT_SECRET` | unset | Secret; prefer gitignored `pulse.toml` or env injection. |
| `microsoft_client_id` | `PULSE_MICROSOFT_CLIENT_ID` | unset | Microsoft Graph OAuth (mail/calendar). |
| `microsoft_client_secret` | `PULSE_MICROSOFT_CLIENT_SECRET` | unset | Secret; prefer gitignored `pulse.toml` or env injection. |
| `microsoft_tenant_id` | `PULSE_MICROSOFT_TENANT_ID` | unset | Tenant id or `common` when unset. |
| `github_client_id` | `PULSE_GITHUB_CLIENT_ID` | unset | GitHub OAuth. |
| `github_client_secret` | `PULSE_GITHUB_CLIENT_SECRET` | unset | Secret; prefer gitignored `pulse.toml` or env injection. |
| `gitlab_client_id` | `PULSE_GITLAB_CLIENT_ID` | unset | GitLab OAuth (optional if using PAT). |
| `gitlab_client_secret` | `PULSE_GITLAB_CLIENT_SECRET` | unset | Secret; prefer gitignored `pulse.toml` or env injection. |
| `gitlab_token` | `PULSE_GITLAB_TOKEN` | unset | PAT; when set, OAuth is not used. |
| `plaid_client_id` | `PULSE_PLAID_CLIENT_ID` | unset | Plaid Link + transactions. |
| `plaid_secret` | `PULSE_PLAID_SECRET` | unset | Secret; prefer gitignored `pulse.toml` or env injection. |
| `plaid_env` | `PULSE_PLAID_ENV` | unset | `sandbox`, `development`, or `production`. |
| `oura_client_id` | `PULSE_OURA_CLIENT_ID` | unset | Oura Cloud API OAuth client id (optional if using PAT). |
| `oura_client_secret` | `PULSE_OURA_CLIENT_SECRET` | unset | Oura OAuth secret; prefer gitignored `pulse.toml` or env injection. |
| `oura_personal_access_token` | `PULSE_OURA_PERSONAL_ACCESS_TOKEN` | unset | Oura personal access token; when set, OAuth is not used. |
| `notion_token` | `PULSE_NOTION_TOKEN` | unset | Notion internal integration secret for workspace search / database query. |
| `linear_api_key` | `PULSE_LINEAR_API_KEY` | unset | Linear personal API key; syncs issues assigned to the key’s user. |
| `anthropic_api_key` | `PULSE_ANTHROPIC_API_KEY` | unset | API key for `[llm.*]` roles with `provider = "anthropic"`; environment fallback `ANTHROPIC_API_KEY` when empty. |
| `openai_api_key` | `PULSE_OPENAI_API_KEY` | unset | API key for `[llm.*]` with `provider = "openai"` or `"ollama"` (OpenAI-compatible); environment fallback `OPENAI_API_KEY` when empty. |
| `gemini_api_key` | `PULSE_GEMINI_API_KEY` | unset | API key for `[llm.*]` with `provider = "gemini"`; environment fallback `GEMINI_API_KEY` when empty. |
| `llm` | _(set in `pulse.toml`)_ | unset | Nested per-role provider config for `summarization`, `discovery`, and `corrections`; supports `anthropic`, `openai`, `gemini`, and `ollama`. |

### LLM provider configuration

Configure LLMs in `pulse.toml` via **`[llm.summarization]`**, **`[llm.discovery]`**, and **`[llm.corrections]`**. Each block sets `model` and optional `provider` and `base_url`. You can set **`[llm] provider`** (and optional **`[llm] base_url`**) once, then list only **`model`** under each role — for example Haiku for digest summarization and Opus for discovery on Anthropic, or a smaller vs larger OpenAI model id. If you configure only one of summarization/discovery, Pulse reuses it for both. **`[llm] base_url`** is inherited only for `openai` and `ollama` roles so a local Ollama URL is not applied to Anthropic or Gemini.

Digest, discovery, MCP digest, and the scheduler require these roles (or a single shared role) to resolve an LLM; there is no separate “API key only” mode. **`pulse init`** profile structuring uses an Anthropic client only when an Anthropic model is already configured for summarization or discovery.

Supported providers are `anthropic`, `openai`, `gemini`, and `ollama`.

**Same provider, different models** (set `anthropic_api_key` in `pulse.toml` or `ANTHROPIC_API_KEY` in the environment). These ids match the current Claude API family ([Anthropic model overview](https://docs.anthropic.com/en/docs/about-claude/models/overview)): Haiku 4.5 for fast summarization, Opus 4.6 for heavier discovery.

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

Put API keys in `pulse.toml` (`anthropic_api_key`, `openai_api_key`, `gemini_api_key`) or set **`ANTHROPIC_API_KEY`**, **`OPENAI_API_KEY`**, **`GEMINI_API_KEY`**, or matching **`PULSE_*`** names in the environment (see the field table above).

`ollama` uses the OpenAI-compatible transport and defaults to a placeholder key when no `OPENAI_API_KEY` is set.

Corrections: **`[llm.corrections]`** is used first, then **`[llm.discovery]`** if corrections is omitted. If neither resolves a provider, corrections stay stored but vault application is skipped.

## `pulse.toml`

`config_loader.default_pulse_config_path()` picks the config file: ``.config/pulse.toml`` first if it exists, otherwise ``./pulse.toml``, otherwise it targets ``.config/pulse.toml`` for new installs (the directory is created when the CLI saves). The file is optional; when present it supplies root scalars, the nested `connectors` map, and `llm`. `PULSE_*` environment variables override root fields; connector tables are not overridden by env (only by editing the TOML file).

The checked-in template matches `pulse.toml.example`: every connector starts with `enabled = false` so you opt in explicitly.

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
omit_amounts_in_digest = false

[connectors.browser]
enabled = false
poll_interval = "15m"
browser = "chrome"  # or "firefox"

[connectors.feeds]
enabled = false
poll_interval = "1h"
urls = []
```

The full checked-in template is `pulse.toml.example` at the repository root. Set `enabled = true` on each connector you want (for example Spotify after OAuth setup, or feeds after adding `urls`). `pulse configure` writes a fresh `pulse.toml` from your answers.

The example file also includes a commented `llm.corrections` block. Leave it out if you want corrections to inherit discovery behavior; add it when correction interpretation should use a different provider or model than discovery.

Each connector entry is parsed into a `ConnectorConfig` model with:

- `enabled` defaulting to `false` when the key is omitted (opt-in)
- `poll_interval` defaulting to `15m`
- extra connector-specific keys preserved as-is

That extra-field behavior is what allows settings such as `browser = "chrome"`, `db_path`, `urls` for feeds, `calendar_id` / `gitlab_base_url` / `omit_amounts_in_digest`, or Spotify supplementary cadence to live in `pulse.toml` without changing the top-level config loader.

## Companion app

The companion mobile app pushes location and health events to the Pulse backend via a shared-secret webhook. Two environment variables control this integration:

| Env var | Default | Notes |
| --- | --- | --- |
| `PULSE_COMPANION_TOKEN` | unset | Shared secret for app ↔ server authentication. Set `companion_token` in `pulse.toml` or this env var; requests without a matching `Authorization: Bearer <token>` header are rejected with HTTP 401. Leave unset to disable token enforcement (not recommended in production). |
| `PULSE_FCM_SERVICE_ACCOUNT_PATH` | unset | Path to the Firebase service account JSON file used to send FCM push notifications to companion app users. Required for push delivery; notifications are silently skipped when unset. |

Enable the companion connector in `pulse.toml` to mount the webhook route and allow the app to send events:

```toml
[connectors.companion]
enabled = true
# The companion app pushes location and health events to /webhooks/companion.
# Set companion_token here or PULSE_COMPANION_TOKEN in the environment for API auth.
```

When `[connectors.companion]` is disabled (the default), the `/webhooks/companion` route is not mounted and companion events are not accepted.

## Secret and token files

The runtime keeps secrets and refresh tokens in different places:

- client credentials live in gitignored `pulse.toml` and/or the process environment (same sources as `pulse configure` writes); never commit real secrets
- OAuth-style token files beside the database: `google_tokens.json`, `spotify_tokens.json`, `microsoft_tokens.json`, `github_tokens.json`, `gitlab_tokens.json`, `plaid_tokens.json` (Plaid stores `access_token` and transaction sync cursor; treat like other secrets)

Because the token paths are derived from `Path(config.database_path).parent`, changing `PULSE_DATABASE_PATH` also changes where those `*.json` token files are written.

## MCP server vs standalone app

The FastAPI app, CLI, and MCP server call the same `load_config()` path: the resolved `pulse.toml` file (default `.config/pulse.toml` with repository-root fallback), plus process environment overrides as described above.

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
- discovery jobs resolve the same way as digest/discovery provider creation: a single configured summarization/discovery role is reused for both; if no role resolves, discovery skips with a no-provider message
- corrections application needs `correction_applications`, a vault path, and a corrections provider resolved from `llm.corrections` or `llm.discovery`; otherwise the system keeps the raw correction and records a skipped or needs-review status instead of editing vault files

## Environment-only deployment

For Docker, systemd, or CI, you can skip putting secrets in TOML and export the same **`PULSE_*`** names (and optional **`ANTHROPIC_API_KEY`** / **`OPENAI_API_KEY`** / **`GEMINI_API_KEY`**) in the process environment. See the README variable table for the full list. Example:

```bash
export PULSE_DATABASE_PATH=data/pulse.db
export PULSE_VAULT_PATH=Pulse-Vault
export PULSE_TIMEZONE=UTC
```

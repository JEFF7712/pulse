# Operations Runbook

## Triage

1. **`GET /health`** → `{"status":"ok"}` when the process is up (not connector auth or LLM).
2. **`pulse status`** — DB path, event counts, time range, cursors.
3. **`pulse logs`** — recent events (`-n`, `--source`, `--all` as needed).
4. Re-read **`pulse.toml`** and env if jobs skip unexpectedly.

## Web UI (`GET /`)

Paths, timezone, scheduler + connector counts. **POST** actions return to `/` with a flash:

| Action | Effect |
| --- | --- |
| `/actions/pull` | Pull all active pull connectors |
| `/actions/discover` | **Daily** discovery only — use `pulse discover` for weekly/monthly |
| `/actions/test-telegram` | Test Telegram (needs tokens) |

## Webhooks and MCP

- **`POST /webhooks/telegram`** — always mounted; valid replies → 202, bad payload → 400. Stores correction + `correction_applications`; vault updates when corrections LLM + target resolve. **`pulse_correct`** (MCP) uses the same pipeline.
- **`POST /webhooks/corrections`** — only if `PULSE_CORRECTIONS_WEBHOOK_SECRET` set; else 404. Body: `{"context_id","message_text"}` preferred; `message` still works as a compatibility alias when `message_text` is absent. Auth: `Authorization: Bearer <secret>` or `X-Pulse-Signature: sha256=<hmac(raw body)>`.

Default install: pull connectors only unless you register push connectors with webhook paths.

## Companion

- `POST /webhooks/companion` — mounted only when `[connectors.companion]` is enabled; auth is `X-Pulse-Token: <token>` or `Authorization: Bearer <token>` from `PULSE_COMPANION_TOKEN`
- `GET /api/insights`, `GET /api/insights/{id}` — pattern metadata + markdown for the companion app; same token auth
- `POST /api/corrections`, `POST /api/device-token` — same token auth (FCM delivery when `PULSE_FCM_SERVICE_ACCOUNT_PATH` set); corrections prefer `message_text`, with `message` accepted only for compatibility when `message_text` is absent

Disabled companion connector → `/webhooks/companion` not mounted (404).

## Scheduler (baseline jobs)

`aggregation` (hourly), `discovery_daily` (23:00), `discovery_weekly` (Sun 20:00), `discovery_monthly` (1st 10:00).

**Skips:** discovery without a resolved LLM role. Cron uses **host** timezone; **`PULSE_TIMEZONE`** affects “today” inside jobs, not cron. Pull jobs only for enabled connectors.

## Recovery

- **`pulse reset <source>`** — reset one connector cursor (full re-pull next time).
- **`pulse reset`** (no arg) — list all cursors, confirm, clear all.
- Check **`pulse logs`** before reset if you need timestamps/context.

## Failure hints

| Symptom | Likely cause |
| --- | --- |
| `/health` OK, empty logs | Connectors off, missing creds, or no pulls yet |
| Ingest OK, no insight notifications | No notification channel configured (discovery still writes the vault) |
| Ingest OK, no discovery | No summarization/discovery LLM (or missing API key) |
| Telegram webhook 400 | Reply missing thread/context for correction |
| Corrections in DB, no vault edit | Status `skipped` / `needs_review` — check `correction_applications` |
| **`publish-pypi` fails with `invalid-publisher`** | PyPI trusted publisher does not match the tag workflow — see [PyPI trusted publishing](pypi-trusted-publishing.md). |

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
| `/actions/digest` | Today’s digest (LLM if configured, else fallback) |
| `/actions/discover` | **Daily** discovery only — use `pulse discover` for weekly/monthly |
| `/actions/test-telegram` | Test Telegram (needs tokens) |

## Webhooks and MCP

- **`POST /webhooks/telegram`** — always mounted; valid replies → 202, bad payload → 400. Stores correction + `correction_applications`; vault updates when corrections LLM + target resolve. **`pulse_correct`** (MCP) uses the same pipeline.
- **`POST /webhooks/corrections`** — only if `PULSE_CORRECTIONS_WEBHOOK_SECRET` set; else 404. Body: `{"context_id","message"}`. Auth: `Authorization: Bearer <secret>` or `X-Pulse-Signature: sha256=<hmac(raw body)>`.

Default install: pull connectors only unless you register push connectors with webhook paths.

## Companion (when `[connectors.companion]` enabled)

- `POST /webhooks/companion` — events (Bearer if `PULSE_COMPANION_TOKEN` set)
- `GET /api/digests`, `GET /api/digests/{date}`
- `POST /api/corrections`, `POST /api/device-token` (FCM when `PULSE_FCM_SERVICE_ACCOUNT_PATH` set)

Disabled → routes not mounted (404).

## Scheduler (baseline jobs)

`daily_digest` (24h), `morning_briefing` (08:00 daily), `aggregation` (hourly), `discovery_daily` (23:00), `discovery_weekly` (Sun 20:00), `discovery_monthly` (1st 10:00).

**Skips:** `morning_briefing` without any notify channel; discovery without a resolved LLM role. Cron uses **host** timezone; **`PULSE_TIMEZONE`** affects “today” inside jobs, not cron. Pull jobs only for enabled connectors.

## Recovery

- **`pulse reset <source>`** — reset one connector cursor (full re-pull next time).
- **`pulse reset`** (no arg) — list all cursors, confirm, clear all.
- Check **`pulse logs`** before reset if you need timestamps/context.

## Failure hints

| Symptom | Likely cause |
| --- | --- |
| `/health` OK, empty logs | Connectors off, missing creds, or no pulls yet |
| Ingest OK, no briefing | No notification channel configured |
| Ingest OK, no discovery | No summarization/discovery LLM (or missing API key) |
| Telegram webhook 400 | Reply missing thread/context for correction |
| Corrections in DB, no vault edit | Status `skipped` / `needs_review` — check `correction_applications` |

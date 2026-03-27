# Operations Runbook

This runbook is anchored to the current FastAPI app, config loader, and scheduler wiring.

For the broader self-hosted guide set, use [Pulse Docs](../index.md) as the docs home.

## Fast health checks

Start with the two lowest-cost checks:

- `GET /health` should return `{"status": "ok"}` when the app is up
- `pulse status` shows the active database path, total event count, observed time range, and connector sync cursors
- `pulse logs` shows recent events from the SQLite store and is the fastest way to confirm that ingestion is still moving

`/health` is only a process-level check. It does not verify connector auth, Telegram delivery, or LLM availability.

## Webhook behavior

The app always mounts `POST /webhooks/telegram`.

- valid Telegram reply payloads are accepted with HTTP 202
- malformed payloads fail with HTTP 400 when the message body, reply text, reply target, or extracted context is missing
- accepted replies are written into the corrections store using the configured `PULSE_DATABASE_PATH`

If you run any push connectors through the registry, Pulse also mounts their connector-specific webhook paths at startup.

## Scheduler expectations

The scheduler always wires these baseline jobs:

- `daily_digest` every 24 hours
- `morning_briefing` on a daily cron at 08:00
- `aggregation` every hour
- `discovery_daily` on a daily cron at 23:00
- `discovery_weekly` on Sundays at 20:00
- `discovery_monthly` on day 1 at 10:00

Operationally, the key skip conditions are:

- `morning_briefing` skips when Telegram is not configured
- discovery jobs skip when `PULSE_ANTHROPIC_API_KEY` is absent
- connector pull jobs only exist for connectors that are enabled in `pulse.toml`
- because the cron jobs are created without an explicit APScheduler timezone, their trigger times follow the scheduler host timezone and process timezone
- `PULSE_TIMEZONE` affects current-day resolution inside jobs, not the cron trigger definitions themselves

## Routine operator flow

Use this order for normal checks and triage:

1. hit `/health`
2. run `pulse status`
3. run `pulse logs -n 20` or `pulse logs --source <connector>`
4. inspect `pulse.toml` and `.env` if jobs are skipping unexpectedly

## Recovery commands

- `pulse reset <source>` clears one connector sync cursor and forces the next pull to fetch from scratch; use it when one source is stuck or needs a clean re-import
- after `pulse reset`, watch `pulse logs` and `pulse status` to confirm fresh events and a new cursor
- if you need to investigate suspicious data, use `pulse logs --source <connector>` before resetting so you can see the affected records and timestamps

## Failure patterns

- healthy `/health` plus empty `pulse logs` usually points to disabled connectors, missing credentials, or no scheduled pulls yet
- successful ingestion plus skipped `morning_briefing` usually means `PULSE_TELEGRAM_BOT_TOKEN` or `PULSE_TELEGRAM_CHAT_ID` is unset
- successful ingestion plus skipped discovery runs usually means `PULSE_ANTHROPIC_API_KEY` is unset
- Telegram webhook 400 responses usually mean the reply payload is missing the original context-bearing message

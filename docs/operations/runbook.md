# Operations Runbook

This runbook is anchored to the current FastAPI app, config loader, and scheduler wiring.

## Fast health checks

Start with the two lowest-cost checks:

- `GET /health` should return `{"status": "ok"}` when the app is up
- `pulse status` shows the active database path, total event count, observed time range, and connector sync cursors
- `pulse logs` shows recent events from the SQLite store and is the fastest way to confirm that ingestion is still moving

`/health` is only a process-level check. It does not verify connector auth, Telegram delivery, or LLM availability.

## Operator web UI

`GET /` returns an HTML home page (bound to the same `--host` / `--port` as the API). It summarizes the configured database path, vault path, timezone, number of registered scheduler jobs, and how many pull vs push connectors are active. Form posts go to:

- `POST /actions/pull` — incremental pull for all active pull connectors
- `POST /actions/digest` — aggregate and generate the daily digest for the current day in `PULSE_TIMEZONE` (non-LLM digest path; the scheduled `daily_digest` job is what uses the LLM when an API key is configured)
- `POST /actions/discover` — aggregate and run **daily**-cadence discovery for the current day (works when a discovery provider resolves; a single configured summarization/discovery role is reused for both, otherwise Pulse falls back to the legacy `PULSE_ANTHROPIC_API_KEY` path, and if neither path resolves the action shows an error notice); use `pulse discover --cadence weekly|monthly` from the CLI for other cadences
- `POST /actions/test-telegram` — send a test notification (requires Telegram env vars)

Redirects return to `/` with a short success or error banner. This complements the CLI; it does not replace `pulse status`, `pulse logs`, or `pulse insights` for inspection.

## Webhook behavior

The app always mounts `POST /webhooks/telegram`.

- valid Telegram reply payloads are accepted with HTTP 202
- malformed payloads fail with HTTP 400 when the message body, reply text, reply target, or extracted context is missing
- accepted replies store the raw correction text in `corrections.message_text` using the configured `PULSE_DATABASE_PATH`
- each accepted reply also records a `correction_applications` audit/status row so operators can tell whether the correction was `applied`, `needs_review`, `skipped`, or `failed`
- when `llm.corrections` (or its fallback provider) is configured and the target resolves safely, Telegram replies can trigger bounded vault updates for digests, patterns, `profile.md`, or `routines.md`

The stock `register_all` hook only registers **pull** connectors today, so a default install has zero push connectors and no extra webhook routes beyond Telegram. If you extend Pulse and register push connectors on the registry, the app mounts their `get_webhook_path()` routes at startup.

## MCP corrections workflow

The MCP tool `pulse_correct` uses the same config loader and correction service as the FastAPI webhook path.

- `pulse_correct` stores raw correction text in the same `corrections` table as Telegram replies
- it also writes a `correction_applications` record for audit/status tracking
- if the configured corrections workflow has a safe target plus an LLM interpreter, it may apply the same bounded vault updates as Telegram replies
- if provider config, vault context, or safe target resolution is missing, the correction is still stored and the status row explains why no vault update happened

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
- discovery jobs use the same provider resolution path as digest/discovery creation: a single configured summarization/discovery role is reused for both, otherwise Pulse falls back to the legacy `PULSE_ANTHROPIC_API_KEY` path; if neither path resolves, discovery skips
- the scheduled `daily_digest` job always runs, and both the scheduler and manual `pulse digest` use the configured summarization provider when one resolves; the web Digest action and MCP `pulse_digest` tool still use the non-LLM digest path today
- connector pull jobs only exist for connectors that are enabled in `pulse.toml`
- because the cron jobs are created without an explicit APScheduler timezone, their trigger times follow the scheduler host timezone and process timezone
- `PULSE_TIMEZONE` affects current-day resolution inside jobs, not the cron trigger definitions themselves

## Routine operator flow

Use this order for normal checks and triage:

1. hit `/health`
2. run `pulse status`
3. run `pulse logs -n 20` or `pulse logs --source <connector>` (add `--all` if you need rows with timestamps after “now”, for example clock skew or imported data)
4. inspect `pulse.toml` and `.env` if jobs are skipping unexpectedly

## Recovery commands

- `pulse reset <source>` clears one connector sync cursor and forces the next pull to fetch from scratch; use it when one source is stuck or needs a clean re-import
- `pulse reset` with no source lists every cursor and, after confirmation, clears **all** of them (full re-pull for every connector on the next pull)
- after `pulse reset`, watch `pulse logs` and `pulse status` to confirm fresh events and a new cursor
- if you need to investigate suspicious data, use `pulse logs --source <connector>` before resetting so you can see the affected records and timestamps

## Failure patterns

- healthy `/health` plus empty `pulse logs` usually points to disabled connectors, missing credentials, or no scheduled pulls yet
- successful ingestion plus skipped `morning_briefing` usually means `PULSE_TELEGRAM_BOT_TOKEN` or `PULSE_TELEGRAM_CHAT_ID` is unset
- successful ingestion plus skipped discovery runs usually means neither a reusable summarization/discovery role nor the legacy `PULSE_ANTHROPIC_API_KEY` fallback is configured
- Telegram webhook 400 responses usually mean the reply payload is missing the original context-bearing message
- corrections present in `corrections` but no vault change usually mean `correction_applications` recorded `skipped` or `needs_review`; inspect the latest status/summary before retrying with a different prompt or config

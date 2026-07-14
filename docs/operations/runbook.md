# Operations Runbook

## Triage

1. **`GET /health`** → `{"status":"ok"}` when the process is up (not connector auth).
2. **`pulse status`** — DB path, event counts, time range, cursors.
3. **`pulse logs`** — recent events (`-n`, `--source`, `--all` as needed).
4. Re-read **`pulse.toml`** and env if jobs skip unexpectedly.

## Web UI (`GET /`)

Paths, timezone, scheduler + connector counts. **POST** actions return to `/` with a flash:

| Action | Effect |
| --- | --- |
| `/actions/pull` | Pull all active pull connectors |
| `/actions/test-telegram` | Test Telegram (needs tokens) |

## Webhooks and MCP

- **`POST /webhooks/telegram`** — always mounted; valid message payload → 202, bad payload → 400.

Default install: pull connectors only unless you register push connectors with webhook paths.

## Scheduler (baseline jobs)

`aggregation` (hourly), plus pull jobs for each enabled connector.

Cron uses **host** timezone; **`PULSE_TIMEZONE`** affects “today” inside jobs, not cron. Pull jobs only for enabled connectors.

**Failures:** set **`notify_on_job_failure = true`** (and at least one outbound channel: Telegram, ntfy, …) to receive **rate-limited** alerts when a scheduled job throws (per-job cooldown **`job_failure_alert_cooldown`**, default `6h`). Category **`operations`**. Connector **401 / missing OAuth** paths that used to return empty now raise **`ConnectorAuthError`** so the same path can alert on **`pull_<source>`** failures.

## Recovery

- **`pulse reset <source>`** — reset one connector cursor (full re-pull next time).
- **`pulse reset`** (no arg) — list all cursors, confirm, clear all.
- Check **`pulse logs`** before reset if you need timestamps/context.

## Failure hints

| Symptom | Likely cause |
| --- | --- |
| `/health` OK, empty logs | Connectors off, missing creds, or no pulls yet |
| Telegram webhook 400 | Missing or empty message text in payload |
| **`publish-pypi` fails with `invalid-publisher`** | PyPI trusted publisher does not match the tag workflow — see [pypi-trusted-publishing.md](./pypi-trusted-publishing.md) or the [deployed copy](https://pulseagent.dev/docs/operations/pypi-trusted-publishing.html). |

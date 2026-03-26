# Backend-First MVP Design

**Date:** 2026-03-22
**Status:** Approved
**Source Context:** `DESIGN.md`

---

## Goal

Build the first useful Pulse backend as a single Python service that proves the core product loop:

1. ingest normalized events,
2. persist them in SQLite,
3. generate a daily digest markdown note in the Obsidian vault,
4. send a morning notification through Telegram,
5. accept a correction reply and persist/apply it.

This MVP intentionally excludes the Flutter companion app and Chrome extension from the first milestone. Those clients should attach to stable backend interfaces after the backend loop works end-to-end.

## Approach

Use a vertical-slice-first architecture with a thin but real foundation. The backend owns the domain model, persistence, scheduling, vault rendering, and orchestration logic. External systems such as Google APIs, Telegram, and LLM providers are adapters around that core.

This keeps the most important contracts stable early:

- normalized `Event` objects,
- SQLite persistence APIs,
- vault write APIs,
- connector interfaces,
- LLM provider interface,
- notification channel interface.

The first working slice should use real implementations for the core and the simplest useful implementation for external adapters.

## Runtime Architecture

The backend runs as a single Python process and contains these runtime components:

- **FastAPI app** for health endpoints, ingestion endpoints, connector-trigger endpoints, and Telegram webhook/callback handling.
- **Core services** for ingestion, daily digest generation, notification dispatch, and correction handling.
- **SQLite store** for raw events, geofences, corrections, connector sync state, and notification context metadata.
- **Vault writer** for markdown output to a local Obsidian-compatible directory.
- **Scheduler** for connector syncs, nightly digests, and morning briefings.
- **Adapters** for Gmail, Google Calendar, Telegram, and LLM providers.

All scheduled jobs and HTTP-triggered flows should call the same service layer so business logic exists in one place.

## Proposed Repository Shape

```text
src/pulse/
  app/
    config.py
    dependencies.py
    main.py
  domain/
    events.py
    connectors.py
    llm.py
    notifications.py
    corrections.py
  store/
    schema.py
    db.py
    events.py
    corrections.py
    sync_state.py
  connectors/
    base.py
    google_auth.py
    calendar.py
    gmail.py
  analysis/
    queries.py
    summarizer.py
    briefing.py
  vault/
    paths.py
    renderer.py
    writer.py
  notifications/
    telegram.py
  jobs/
    scheduler.py
    runners.py
tests/
  unit/
  integration/
  e2e/
```

## Data Flow

### Ingestion

1. A connector fetches source records from Gmail or Google Calendar.
2. The connector normalizes those records into domain `Event` objects.
3. The ingestion service validates and upserts the events into SQLite.
4. The service updates connector sync state with last successful pull metadata.

### Daily Digest

1. A nightly job queries one day's worth of events from SQLite.
2. The summarizer groups and structures the data into a digest payload.
3. The payload is rendered into markdown using a vault renderer.
4. The vault writer writes `01-Daily/YYYY-MM-DD.md`.

### Morning Briefing

1. A scheduled job reads recent digest data plus structured signals.
2. The briefing service composes a compact message.
3. The notification channel sends it through Telegram.
4. Notification context is stored so user replies can be mapped back to a source record.

### Corrections

1. Telegram forwards a reply webhook containing message metadata.
2. The correction service resolves the reply to a prior context record.
3. The correction is stored in SQLite first.
4. The service applies the side effect, such as updating a vault note or marking a geofence label change request.

## Error Handling Principles

- Connector failures should not stop unrelated jobs.
- Event ingestion must be idempotent using stable source-derived event IDs.
- Corrections must be append-first: persist the correction before applying downstream updates.
- Jobs should emit structured results: `success`, `partial_success`, or `failed`.
- User-facing outputs stay concise even when internal logs contain detailed failure context.

## Testing Strategy

The MVP test pyramid should be:

- **Unit tests** for domain models, markdown rendering, correction parsing, and query helpers.
- **Integration tests** for SQLite repositories, vault writing, FastAPI endpoints, and Telegram webhook handling.
- **End-to-end test** for the vertical slice: ingest fixture events -> generate daily digest -> send briefing -> accept correction.

Most tests should use fake connectors, fake LLM providers, and fake notification channels. Live Google/Telegram tests should be optional and gated behind environment variables.

## Multiple-Agent Execution Model

The best way to parallelize implementation is by subsystem ownership after contracts are frozen.

### Shared contract pass

One lead agent defines and documents:

- config schema,
- `Event` model,
- connector interface,
- LLM provider interface,
- notification interface,
- repository APIs,
- job names and payload contracts.

### Parallel agents

- **Agent A:** platform skeleton and dependency wiring
- **Agent B:** SQLite schema and repositories
- **Agent C:** vault renderer, writer, and summarizer pipeline
- **Agent D:** Google auth and connectors
- **Agent E:** Telegram notifications and correction intake

### Integration pass

One integration/review agent verifies that agents did not drift on:

- field names,
- config keys,
- method signatures,
- scheduler registration,
- test fixtures.

The rule is: agents share contracts, not files.

## Milestone Order

1. Scaffold the Python package, toolchain, and config system.
2. Implement domain contracts and SQLite event persistence.
3. Implement vault rendering and daily digest generation.
4. Implement Telegram notifications and correction intake.
5. Add Google Calendar sync.
6. Add Gmail sync.
7. Wire scheduler jobs and harden the end-to-end path.

## Out of Scope for This Milestone

- Flutter companion app
- Chrome extension
- Plaid, Spotify, YouTube, and other post-MVP connectors
- Local LLM providers beyond the initial abstraction
- Advanced anomaly detection and monthly reviews

## Success Criteria

The backend-first MVP is complete when a developer can:

1. start the service locally,
2. ingest fixture or real Gmail/Calendar events,
3. inspect persisted events in SQLite,
4. generate a daily digest markdown file in a local vault,
5. send a Telegram morning briefing,
6. reply with a correction and see it stored and applied.

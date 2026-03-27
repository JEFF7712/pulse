# Home Operator Console Design

**Date:** 2026-03-26
**Status:** Approved
**Source Context:** `src/pulse/app/homepage.py`, `src/pulse/app/main.py`, `src/pulse/app/cli.py`, `src/pulse/jobs/scheduler.py`

---

## Goal

Evolve the `/` homepage from a minimal status card into a compact operator console that provides three things at once:

1. live operational data,
2. safe quick actions,
3. slightly richer visual polish.

The page should remain small, readable, and intentionally non-destructive.

## Approach

Keep the server-rendered HTML approach and extend it with lightweight server-side status gathering plus a few safe POST action endpoints. The homepage should still load as a single FastAPI-rendered document without turning into a frontend application.

Status information should be computed from the existing config, registry, and scheduler setup already used by `pulse run`. Safe actions should call existing operational routines or thin wrappers around them, then return the operator to the same page with a compact success or failure notice.

## Information Architecture

The page should have four compact sections.

### 1. Status Header

- keep `Pulse`
- keep `server online`
- keep `self-hosted node`
- retain the subtle pulse animation
- add a few tight badges such as scheduler state and connector counts

### 2. Operational Data

Show a compact grid of real runtime facts, such as:

- database path
- vault path
- timezone
- scheduler job count
- active pull connector count
- active push connector count
- whether Telegram is configured
- whether Anthropic is configured

The data should be concise and primarily text-oriented.

### 3. Safe Actions

Add POST-backed operator actions for safe, non-destructive tasks:

- run pull cycle
- run daily digest
- run discovery pass
- send test Telegram message
- refresh the page state

No reset, cleanup, or destructive controls should appear here.

### 4. Endpoints / Runtime Surface

Keep the current operational surface visible:

- `/health` as a clickable link
- `POST /webhooks/telegram` as text only

## Runtime Behavior

The console should remain useful without requiring a JavaScript app.

- GET `/` renders the full console with runtime status
- safe actions post to dedicated endpoints and redirect back to `/`
- the redirected page shows a small flash-style status message describing the outcome
- actions should fail gracefully with a compact error message if a dependency is not configured

## Data Sources

Status data should come from existing server/runtime structures where possible:

- `PulseConfig` for filesystem paths, timezone, and configuration flags
- `ConnectorRegistry` for active pull/push connector counts
- scheduler instance for job count and running state

If an action depends on unconfigured services, the UI should reflect that state rather than hiding the action entirely.

## Visual Direction

Keep the current black/cream/green identity and animated pulse motif, then add modest polish:

- clearer section hierarchy
- stronger hover/focus states for buttons and links
- cleaner spacing between blocks
- consistent utility-card treatment for data and actions

The result should still feel restrained, not like a full admin dashboard.

## Error Handling

- action failures should not crash the page
- invalid or unavailable operations should render a clear status notice after redirect
- exceptions should be surfaced as short operator-facing messages, not stack traces

## Testing Strategy

Add focused coverage at two levels.

### Homepage rendering

Update the root UI test to assert the new sections and stable status labels, for example:

- `scheduler`
- `connectors`
- `database`
- `vault`
- `run pull`
- `run digest`
- `run discovery`
- `test telegram`

### Action endpoints

Add focused tests for the safe action routes:

- POST action returns a redirect to `/`
- resulting page shows a success or skipped/failure message
- unconfigured integrations produce a safe operator-facing notice

## Success Criteria

The operator-console upgrade is successful when:

1. `/` shows real runtime data instead of only static text,
2. the page exposes a handful of safe quick actions,
3. action results are communicated inline after redirect,
4. no destructive operations are exposed,
5. the page remains compact, server-rendered, and visually consistent.

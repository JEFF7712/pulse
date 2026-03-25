# Phase 1: Connector Infrastructure + Google Ecosystem

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Infrastructure for scalable connector development + YouTube connector + Gmail/Calendar migration

---

## Context

Pulse's core value scales with data breadth — cross-source patterns only emerge when correlating across domains. The project currently has two connectors (Gmail, Calendar) wired in ad-hoc. This phase establishes the infrastructure for 13+ planned connectors and adds YouTube as the third.

### Decisions Made

- **Approach:** Infrastructure-first — build the framework, then add YouTube and migrate existing connectors
- **Registry model:** Config-driven (pulse.toml for connector settings, env vars for secrets)
- **Push support:** New `PushConnector` interface alongside existing pull-based `Connector`
- **Auth strategy:** Shared Google OAuth module with single consent flow for all Google services
- **Phased rollout:** This is Phase 1 of 4. Future phases: Media & Browsing, Financial, Health & Location

---

## 1. Connector Interfaces

### Pull Connector (enhanced)

```python
class Connector(ABC):
    @abstractmethod
    async def pull(self, since: datetime | None = None) -> list[Event]:
        """Pull new events from the data source."""

    @abstractmethod
    def get_source_name(self) -> str:
        """Unique identifier for this data source (e.g. 'gmail')."""

    def get_default_interval(self) -> timedelta:
        """How often this connector should be polled. Override per-connector."""
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        """Check that required credentials/config are present. Called at startup."""
        return True
```

### Push Connector (new)

```python
class PushConnector(ABC):
    @abstractmethod
    def get_source_name(self) -> str:
        """Unique identifier for this data source."""

    @abstractmethod
    def get_webhook_path(self) -> str:
        """URL path this connector listens on (e.g. '/webhooks/location')."""

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> list[Event]:
        """Parse incoming webhook payload into events."""

    async def validate_config(self) -> bool:
        return True
```

### Design Rationale

- Both connector types produce `list[Event]` — the rest of the pipeline (store, analysis, vault) is agnostic to how events arrived.
- `validate_config()` enables graceful degradation at startup: connectors with missing credentials are skipped with a warning rather than crashing.
- `get_default_interval()` provides a sensible default that can be overridden in `pulse.toml`.
- The `Event` model is unchanged — its flexible `data` and `metadata` dicts already accommodate any source.

---

## 2. Config-Driven Registry

### Configuration Model

```python
class ConnectorConfig(BaseModel):
    enabled: bool = True
    poll_interval: str = "15m"  # parsed to timedelta, ignored for push connectors
    model_config = ConfigDict(extra="allow")  # connector-specific settings

class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    connectors: dict[str, ConnectorConfig] = {}
```

### Config File (pulse.toml)

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
```

Secrets (OAuth tokens, API keys) remain in env vars / `.env` — never in the config file.

### Registry

```python
class ConnectorRegistry:
    def register_pull(self, name: str, connector_class: type[Connector]) -> None
    def register_push(self, name: str, connector_class: type[PushConnector]) -> None
    def build_active_connectors(self, config: PulseConfig) -> None
    def get_pull_connectors(self) -> list[tuple[Connector, ConnectorConfig]]
    def get_push_connectors(self) -> list[tuple[PushConnector, ConnectorConfig]]
```

`build_active_connectors` iterates over config entries where `enabled=True`, instantiates the class, calls `validate_config()`, and skips with a warning if invalid.

### Connector Registration

Explicit registration in `connectors/__init__.py` — one line per connector, no autodiscovery magic:

```python
def register_all(registry: ConnectorRegistry) -> None:
    registry.register_pull("gmail", GmailConnector)
    registry.register_pull("calendar", GoogleCalendarConnector)
    registry.register_pull("youtube", YouTubeConnector)
```

### Design Rationale

- `pulse.toml` over env vars for connector config because per-connector nested settings don't map well to flat env vars.
- `tomllib` is stdlib since Python 3.11 — no new dependency.
- Explicit registration avoids decorator magic while keeping a single place to see all connectors.
- Adding a future connector = write the class, add one registration line, document the config keys.

---

## 3. Google OAuth2 Flow

### Overview

Gmail, Calendar, and YouTube all use Google OAuth2. A shared auth module handles the flow once for all Google connectors.

### Token Storage

Tokens persisted to `data/google_tokens.json`. Encryption at rest is a future improvement.

### Auth Flow

1. User runs `pulse auth google` (new CLI entry point)
2. Pulse opens browser to Google consent screen, requesting scopes for all enabled Google connectors
3. User approves → redirect to localhost callback
4. Pulse exchanges code for tokens, stores refresh token to `data/google_tokens.json`
5. On subsequent runs, connectors call `get_credentials()` which auto-refreshes the access token

### Shared Auth Module

```python
# connectors/google_auth.py

SCOPES_BY_CONNECTOR = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "youtube": ["https://www.googleapis.com/auth/youtube.readonly"],
}

class GoogleAuthManager:
    def __init__(self, client_id: str, client_secret: str, token_path: Path): ...
    def get_required_scopes(self, active_connectors: list[str]) -> list[str]: ...
    async def authorize(self) -> None: ...
    async def get_credentials(self) -> Credentials: ...
    def is_authorized(self) -> bool: ...
```

### Design Rationale

- Single OAuth consent for all Google services — user doesn't authorize three times.
- Scopes dynamically built from enabled Google connectors — minimal permissions.
- CLI command (`pulse auth google`) over web UI — simpler for self-hosted.
- If tokens are missing or expired beyond refresh, `validate_config()` returns `False` and the connector is skipped gracefully.

### Dependencies

- `google-auth-oauthlib` — OAuth2 flow
- `google-api-python-client` — Gmail, Calendar, YouTube API clients

---

## 4. Scheduler Integration

### Pull Connector Scheduling

```python
class PulseScheduler:
    def __init__(self, registry: ConnectorRegistry, event_repo: EventRepository,
                 sync_state: SyncStateRepository): ...

    def start(self) -> None:
        # Schedule each active pull connector at its configured interval
        for connector, config in self._registry.get_pull_connectors():
            interval = parse_interval(config.poll_interval)
            self._scheduler.add_job(
                self._run_pull,
                trigger=IntervalTrigger(seconds=interval.total_seconds()),
                args=[connector],
                id=f"pull_{connector.get_source_name()}",
            )
        # Keep existing analysis/briefing jobs
        ...

    async def _run_pull(self, connector: Connector) -> None:
        source = connector.get_source_name()
        cursor = await self._sync_state.load(source)
        since = datetime.fromisoformat(cursor) if cursor else None
        events = await connector.pull(since=since)
        if events:
            await self._event_repo.upsert_events(events)
            latest = max(e.timestamp for e in events)
            await self._sync_state.save(source, latest.isoformat())
```

### Push Connector Webhook Routing

Push connectors auto-register their HTTP routes at FastAPI startup:

```python
for push_conn, config in registry.get_push_connectors():
    path = push_conn.get_webhook_path()
    # Register POST route at path → call handle_webhook → upsert events
    app.add_api_route(path, handler, methods=["POST"])
```

### Design Rationale

- `_run_pull` is generic — works for any pull connector. No more per-connector job functions.
- Sync state (cursor) management is centralized, not duplicated per connector.
- Existing analysis/briefing jobs remain unchanged — they consume from the event store regardless of event origin.
- APScheduler handles retry/error logging on pull failures.

---

## 5. YouTube Connector

### API Approach

YouTube Data API v3 provides:
- **Activities** (likes, subscriptions, etc.)
- **Liked videos** playlist
- **Subscriptions** list

Note: Google removed direct watch history API access in 2016. Full watch history requires Google Takeout import (future phase — file ingestion connector).

### Event Types

| Event Type | Data Fields | Source |
|-----------|-------------|--------|
| `media.youtube.watch` | title, channel, video_id, duration, category | Activities API |
| `media.youtube.like` | title, channel, video_id | Liked videos playlist |
| `media.youtube.subscription` | channel_name, channel_id | Subscriptions API |

### Implementation

```python
class YouTubeConnector(Connector):
    def get_source_name(self) -> str:
        return "youtube"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=1)

    async def validate_config(self) -> bool:
        return self._auth_manager.is_authorized()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        creds = await self._auth_manager.get_credentials()
        # Fetch activities, liked videos, subscriptions
        # Convert to Event objects
        ...
```

---

## 6. Gmail & Calendar Migration

Both existing connectors are migrated to the new infrastructure:

- **Auth:** Replace hardcoded Google API client construction with `GoogleAuthManager.get_credentials()`
- **Scheduling:** Remove manual wiring from job runners — registry handles it
- **Pull logic:** Unchanged — the actual API querying and Event construction stays the same

---

## 7. MCP Server Updates

The existing `pulse_connector_status` MCP tool is enhanced to show:
- Which connectors are registered
- Which are enabled vs disabled
- Which passed `validate_config()`
- Last sync time and event count per source

No new MCP tools needed — `pulse_events_for_day` and `pulse_ingest_event` already work regardless of event source.

---

## 8. Testing Strategy

### Unit Tests

- `ConnectorRegistry` — registration, config filtering, validate_config skip behavior
- `GoogleAuthManager` — token refresh logic, scope merging (mock Google API)
- `YouTubeConnector` — response parsing into Events (mock API responses)
- `PulseScheduler` — correct jobs created for active connectors
- Config parsing — `pulse.toml` → `PulseConfig` with connector settings

### Integration Tests

- Full pull cycle: connector → event store → sync state update
- Push connector webhook → event store
- Registry startup with mixed valid/invalid connectors (graceful degradation)

### E2E Tests

- `tests/e2e/test_google_live.py` — manual run with real Google credentials
- Skipped by default via `pytest.mark.skipunless`
- Not run in CI

---

## 9. New Dependencies

| Package | Purpose |
|---------|---------|
| `google-auth-oauthlib` | OAuth2 flow for Google services |
| `google-api-python-client` | Gmail, Calendar, YouTube API clients |
| `tomllib` (stdlib 3.11+) | Parse `pulse.toml` |

---

## 10. Future Phases

| Phase | Scope | Connectors |
|-------|-------|------------|
| 2 | Media & Browsing | Spotify, Chrome/Firefox history |
| 3 | Financial | Plaid (bank transactions) |
| 4 | Health & Location | HealthKit, fitness trackers, location webhooks |

Each phase follows its own spec → plan → implementation cycle, building on the infrastructure established here.

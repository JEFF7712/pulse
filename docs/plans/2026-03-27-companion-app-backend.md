# Companion App Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backend API surface that the Pulse companion app needs: a companion push connector for location/health events, an FCM notification channel, REST endpoints for digest reading and corrections, token-based auth, and device token storage.

**Architecture:** The companion app is treated as another push connector in Pulse's existing connector registry. Location and health events flow through the same Event → store → analysis pipeline as every other source. A new `FCMChannel` implements the existing `NotificationChannel` protocol alongside Telegram. New REST endpoints for digest reading and corrections reuse existing services. Auth is a shared secret token checked via a FastAPI dependency.

**Tech Stack:** Python 3.12+, FastAPI, SQLite via `aiosqlite`, Pydantic config, `google-auth` for FCM service account credentials, `httpx` for FCM HTTP v1 API, pytest.

---

### Task 1: Add companion token auth dependency

**Files:**
- Create: `src/pulse/app/auth.py`
- Modify: `src/pulse/app/config.py`
- Test: `tests/unit/test_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulse.app.config import PulseConfig


def test_auth_dependency_passes_with_valid_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")
    dep = build_require_companion_token(lambda: settings)

    app = FastAPI()

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)

    response = client.get(
        "/protected", headers={"X-Pulse-Token": "test-secret-123"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_dependency_rejects_missing_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/protected")
    assert response.status_code == 401


def test_auth_dependency_rejects_wrong_token():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token="test-secret-123")

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/protected", headers={"X-Pulse-Token": "wrong-token"}
    )
    assert response.status_code == 401


def test_auth_dependency_rejects_when_no_token_configured():
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(companion_token=None)

    app = FastAPI()
    dep = build_require_companion_token(lambda: settings)

    @app.get("/protected")
    async def protected(_=dep):
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/protected", headers={"X-Pulse-Token": "anything"}
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: FAIL with missing module `pulse.app.auth`.

- [ ] **Step 3: Add `companion_token` to config**

In `src/pulse/app/config.py`, add after `plaid_env`:

```python
    companion_token: str | None = None
    fcm_service_account_path: str | None = None
```

- [ ] **Step 4: Write auth dependency**

```python
# src/pulse/app/auth.py
"""Token-based auth for the companion app API."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from pulse.app.config import PulseConfig


def build_require_companion_token(
    get_settings: Callable[[], PulseConfig],
) -> Depends:
    """Build a FastAPI dependency that verifies the X-Pulse-Token header."""

    async def _verify(
        x_pulse_token: Annotated[str | None, Header()] = None,
    ) -> None:
        settings = get_settings()
        expected = settings.companion_token

        if not expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Companion API is not configured.",
            )

        if x_pulse_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Pulse-Token header.",
            )

        if not hmac.compare_digest(x_pulse_token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token.",
            )

    return Depends(_verify)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/app/auth.py src/pulse/app/config.py tests/unit/test_auth.py
git commit -m "feat: add companion token auth dependency"
```

---

### Task 2: Add companion push connector

**Files:**
- Create: `src/pulse/connectors/companion.py`
- Modify: `src/pulse/connectors/__init__.py`
- Test: `tests/unit/test_companion_connector.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from datetime import UTC, datetime


def test_companion_connector_source_name():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()
    assert connector.get_source_name() == "companion"


def test_companion_connector_webhook_path():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()
    assert connector.get_webhook_path() == "/webhooks/companion"


def test_companion_connector_parses_location_enter_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:05:00Z",
                        "data": {
                            "place": "office",
                            "lat": 40.7128,
                            "lng": -74.006,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].source == "companion"
    assert events[0].event_type == "location.enter"
    assert events[0].data["place"] == "office"
    assert events[0].timestamp == datetime(2026, 3, 27, 9, 5, tzinfo=UTC)


def test_companion_connector_parses_location_exit_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.exit",
                        "timestamp": "2026-03-27T18:15:00Z",
                        "data": {
                            "place": "office",
                            "duration_minutes": 550,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "location.exit"
    assert events[0].data["duration_minutes"] == 550


def test_companion_connector_parses_health_steps_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "health.steps",
                        "timestamp": "2026-03-27T23:59:00Z",
                        "data": {"count": 8420},
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "health.steps"
    assert events[0].data["count"] == 8420


def test_companion_connector_parses_health_sleep_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "health.sleep",
                        "timestamp": "2026-03-27T07:15:00Z",
                        "data": {
                            "in_bed_minutes": 465,
                            "asleep_minutes": 410,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "health.sleep"
    assert events[0].data["asleep_minutes"] == 410


def test_companion_connector_parses_batch_of_mixed_events():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:00:00Z",
                        "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                    },
                    {
                        "type": "health.steps",
                        "timestamp": "2026-03-27T23:59:00Z",
                        "data": {"count": 8420},
                    },
                ]
            }
        )
    )

    assert len(events) == 2
    types = {e.event_type for e in events}
    assert types == {"location.enter", "health.steps"}


def test_companion_connector_rejects_unknown_event_type():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "unknown.type",
                        "timestamp": "2026-03-27T09:00:00Z",
                        "data": {},
                    }
                ]
            }
        )
    )

    assert len(events) == 0


def test_companion_connector_returns_empty_for_missing_events_key():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(connector.handle_webhook({}))
    assert events == []


def test_companion_connector_generates_deterministic_event_ids():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:05:00Z",
                        "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                    }
                ]
            }
        )
    )

    assert events[0].id.startswith("companion:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_companion_connector.py -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/connectors/companion.py
"""Companion app push connector — ingests location and health events."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pulse.domain.connectors import PushConnector
from pulse.domain.events import Event

_ALLOWED_EVENT_TYPES = {
    "location.enter",
    "location.exit",
    "health.steps",
    "health.sleep",
}


class CompanionConnector(PushConnector):
    def get_source_name(self) -> str:
        return "companion"

    def get_webhook_path(self) -> str:
        return "/webhooks/companion"

    async def handle_webhook(self, payload: dict[str, Any]) -> list[Event]:
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return []

        events: list[Event] = []
        for raw in raw_events:
            event = self._parse_event(raw)
            if event is not None:
                events.append(event)
        return events

    def _parse_event(self, raw: dict[str, Any]) -> Event | None:
        event_type = raw.get("type", "")
        if event_type not in _ALLOWED_EVENT_TYPES:
            return None

        timestamp_str = raw.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            return None

        data = raw.get("data", {})

        return Event(
            id=f"companion:{uuid4()}",
            timestamp=timestamp,
            source="companion",
            event_type=event_type,
            data=data,
            metadata={},
        )
```

- [ ] **Step 4: Register the connector**

In `src/pulse/connectors/__init__.py`, add the import and registration at the end of `register_all()`:

```python
    from pulse.connectors.companion import CompanionConnector

    registry.register_push("companion", CompanionConnector)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_companion_connector.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/companion.py src/pulse/connectors/__init__.py tests/unit/test_companion_connector.py
git commit -m "feat: add companion push connector for location and health events"
```

---

### Task 3: Add device token storage

**Files:**
- Create: `src/pulse/store/device_tokens.py`
- Modify: `src/pulse/store/schema.py`
- Test: `tests/integration/test_device_token_repository.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from datetime import UTC, datetime


def test_device_token_repository_stores_and_retrieves_tokens(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 1
            assert tokens[0]["token"] == "fcm-token-abc"
            assert tokens[0]["platform"] == "ios"

    asyncio.run(exercise())


def test_device_token_repository_upsert_replaces_existing_token(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")
            await repo.upsert("fcm-token-abc", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 1

    asyncio.run(exercise())


def test_device_token_repository_supports_multiple_tokens(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")
            await repo.upsert("fcm-token-def", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 2

    asyncio.run(exercise())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_device_token_repository.py -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Add device_tokens table to schema**

In `src/pulse/store/schema.py`, add after the `correction_applications` table creation:

```python
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS device_tokens (
            token TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            registered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
```

- [ ] **Step 4: Write device token repository**

```python
# src/pulse/store/device_tokens.py
"""Repository for FCM device token storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiosqlite


class DeviceTokenRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, token: str, platform: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO device_tokens (token, platform, registered_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET updated_at = ?
            """,
            (token, platform, now, now, now),
        )
        await self._db.commit()

    async def list_active(self) -> list[dict[str, Any]]:
        cursor = await self._db.execute(
            "SELECT token, platform, registered_at, updated_at FROM device_tokens ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "token": row[0],
                "platform": row[1],
                "registered_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_device_token_repository.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/store/device_tokens.py src/pulse/store/schema.py tests/integration/test_device_token_repository.py
git commit -m "feat: add device token storage for FCM push"
```

---

### Task 4: Add FCM notification channel

**Files:**
- Create: `src/pulse/notifications/fcm.py`
- Test: `tests/unit/test_fcm_channel.py`

- [ ] **Step 1: Write the failing tests**

```python
from pulse.domain.notifications import Notification


class FakeHTTPClient:
    def __init__(self, status_code: int = 200):
        self.sent: list[dict] = []
        self.status_code = status_code

    def post(self, url: str, *, headers: dict, json: dict) -> "FakeResponse":
        self.sent.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.status_code)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class FakeCredentials:
    def __init__(self):
        self.token = "fake-access-token"
        self.valid = True

    def refresh(self, request):
        self.token = "refreshed-access-token"
        self.valid = True


def test_fcm_channel_sends_notification_to_all_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    result = channel.send(
        Notification(
            title="Morning Briefing",
            body="You have 3 meetings today.",
            category="briefing",
            context_id="2026-03-27",
        )
    )

    assert result is True
    assert len(http.sent) == 1
    payload = http.sent[0]["json"]
    assert payload["message"]["token"] == "device-a"
    assert payload["message"]["notification"]["title"] == "Morning Briefing"
    assert payload["message"]["notification"]["body"] == "You have 3 meetings today."
    assert payload["message"]["data"]["context_id"] == "2026-03-27"


def test_fcm_channel_sends_to_multiple_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [
        {"token": "device-a", "platform": "ios"},
        {"token": "device-b", "platform": "ios"},
    ]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert len(http.sent) == 2
    assert http.sent[0]["json"]["message"]["token"] == "device-a"
    assert http.sent[1]["json"]["message"]["token"] == "device-b"


def test_fcm_channel_returns_false_when_no_tokens():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=[],
        http_client=http,
    )

    result = channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert result is False
    assert len(http.sent) == 0


def test_fcm_channel_includes_authorization_header():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test")
    )

    assert http.sent[0]["headers"]["Authorization"] == "Bearer fake-access-token"


def test_fcm_channel_omits_context_id_from_data_when_none():
    from pulse.notifications.fcm import FCMChannel

    http = FakeHTTPClient()
    creds = FakeCredentials()
    tokens = [{"token": "device-a", "platform": "ios"}]

    channel = FCMChannel(
        project_id="test-project",
        credentials=creds,
        device_tokens=tokens,
        http_client=http,
    )

    channel.send(
        Notification(title="Test", body="Body", category="test", context_id=None)
    )

    data = http.sent[0]["json"]["message"].get("data", {})
    assert "context_id" not in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_fcm_channel.py -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/notifications/fcm.py
"""FCM notification channel — sends push notifications via Firebase Cloud Messaging."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pulse.domain.notifications import Notification

logger = logging.getLogger(__name__)

_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class HTTPClient(Protocol):
    def post(self, url: str, *, headers: dict, json: dict) -> Any: ...


class FCMChannel:
    def __init__(
        self,
        project_id: str,
        credentials: Any,
        device_tokens: list[dict[str, str]],
        http_client: HTTPClient | None = None,
    ) -> None:
        self._project_id = project_id
        self._credentials = credentials
        self._device_tokens = device_tokens
        self._url = _FCM_SEND_URL.format(project_id=project_id)

        if http_client is None:
            import httpx

            self._http: HTTPClient = httpx
        else:
            self._http = http_client

    def send(self, notification: Notification) -> bool:
        if not self._device_tokens:
            return False

        self._ensure_valid_credentials()

        headers = {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

        for device in self._device_tokens:
            message: dict[str, Any] = {
                "token": device["token"],
                "notification": {
                    "title": notification.title,
                    "body": notification.body,
                },
            }

            data: dict[str, str] = {"category": notification.category}
            if notification.context_id is not None:
                data["context_id"] = notification.context_id
            if data:
                message["data"] = data

            try:
                response = self._http.post(
                    self._url,
                    headers=headers,
                    json={"message": message},
                )
                response.raise_for_status()
            except Exception:
                logger.warning(
                    "FCM send failed for token %s…",
                    device["token"][:8],
                    exc_info=True,
                )

        return True

    def _ensure_valid_credentials(self) -> None:
        if not self._credentials.valid:
            import google.auth.transport.requests

            self._credentials.refresh(google.auth.transport.requests.Request())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_fcm_channel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/notifications/fcm.py tests/unit/test_fcm_channel.py
git commit -m "feat: add FCM notification channel"
```

---

### Task 5: Add REST API router for digests, corrections, and device tokens

**Files:**
- Create: `src/pulse/app/api.py`
- Test: `tests/integration/test_companion_api.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulse.app.config import PulseConfig


def _build_test_app(tmp_path: Path, companion_token: str = "test-token") -> FastAPI:
    from pulse.app.api import build_api_router
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(
        database_path=str(tmp_path / "test.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token=companion_token,
    )

    app = FastAPI()
    auth_dep = build_require_companion_token(lambda: settings)
    router = build_api_router(lambda: settings, auth_dep)
    app.include_router(router)
    return app


def test_get_digest_returns_markdown(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-27.md").write_text(
        "# Daily Digest\n\n- Met with Sam.", encoding="utf-8"
    )

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert "Met with Sam" in response.json()["markdown"]


def test_get_digest_returns_404_for_missing_date(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 404


def test_get_latest_digest_returns_most_recent(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-26.md").write_text("# March 26", encoding="utf-8")
    (vault / "2026-03-27.md").write_text("# March 27", encoding="utf-8")

    response = client.get(
        "/api/digests/latest",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert "March 27" in response.json()["markdown"]


def test_post_correction_records_and_returns_id(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/corrections",
        headers={"X-Pulse-Token": "test-token"},
        json={
            "context_id": "2026-03-27",
            "message_text": "The deadline is Friday.",
        },
    )
    assert response.status_code == 202
    assert "correction_id" in response.json()


def test_post_device_token_stores_token(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/device-token",
        headers={"X-Pulse-Token": "test-token"},
        json={"token": "fcm-device-abc", "platform": "ios"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "registered"

    async def check_db():
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "test.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)
            tokens = await repo.list_active()
            return tokens

    tokens = asyncio.run(check_db())
    assert len(tokens) == 1
    assert tokens[0]["token"] == "fcm-device-abc"


def test_api_rejects_unauthenticated_request(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get("/api/digests/2026-03-27")
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_companion_api.py -v`
Expected: FAIL with missing module.

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/app/api.py
"""REST API router for the companion app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from pulse.app.config import PulseConfig
from pulse.services.corrections import build_correction_service
from pulse.store.correction_applications import CorrectionApplicationRepository
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.device_tokens import DeviceTokenRepository
from pulse.store.schema import bootstrap_schema


def build_api_router(
    get_settings: Callable[[], PulseConfig],
    auth_dependency: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api", dependencies=[auth_dependency])

    @router.get("/digests/latest")
    async def get_latest_digest() -> dict[str, str]:
        settings = get_settings()
        daily_dir = Path(settings.vault_path) / "01-Daily"
        if not daily_dir.exists():
            raise HTTPException(status_code=404, detail="No digests found.")
        files = sorted(daily_dir.glob("*.md"), reverse=True)
        if not files:
            raise HTTPException(status_code=404, detail="No digests found.")
        date_slug = files[0].stem
        return {
            "date": date_slug,
            "markdown": files[0].read_text(encoding="utf-8"),
        }

    @router.get("/digests/{date_slug}")
    async def get_digest(date_slug: str) -> dict[str, str]:
        settings = get_settings()
        path = Path(settings.vault_path) / "01-Daily" / f"{date_slug}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Digest not found.")
        return {"date": date_slug, "markdown": path.read_text(encoding="utf-8")}

    @router.post("/corrections", status_code=status.HTTP_202_ACCEPTED)
    async def post_correction(body: dict[str, str]) -> dict[str, str]:
        settings = get_settings()
        context_id = body.get("context_id", "")
        message_text = body.get("message_text", "")
        if not context_id or not message_text:
            raise HTTPException(
                status_code=400, detail="context_id and message_text required."
            )

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            service = build_correction_service(
                CorrectionRepository(db),
                config=settings,
                correction_applications=CorrectionApplicationRepository(db),
                vault_path=settings.vault_path,
            )
            correction = await service.record_correction(context_id, message_text)

        return {"status": "accepted", "correction_id": correction.id}

    @router.post("/device-token")
    async def post_device_token(body: dict[str, str]) -> dict[str, str]:
        settings = get_settings()
        token = body.get("token", "")
        platform = body.get("platform", "")
        if not token or not platform:
            raise HTTPException(
                status_code=400, detail="token and platform required."
            )

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)
            await repo.upsert(token, platform)

        return {"status": "registered"}

    return router
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_companion_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/api.py tests/integration/test_companion_api.py
git commit -m "feat: add REST API for digests, corrections, and device tokens"
```

---

### Task 6: Wire API router and companion connector into main app

**Files:**
- Modify: `src/pulse/app/main.py`
- Test: `tests/integration/test_companion_api.py` (add wiring test)

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_companion_api.py`:

```python
def test_companion_webhook_and_api_wired_in_full_app(tmp_path):
    from pulse.app.config import PulseConfig
    from pulse.app.dependencies import get_settings
    from pulse.app.main import create_app
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry

    settings = PulseConfig(
        database_path=str(tmp_path / "full.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token="integration-token",
        connectors={"companion": ConnectorConfig(enabled=True)},
    )

    registry = ConnectorRegistry()
    register_all(registry, settings)

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    # Companion webhook should be wired
    response = client.post(
        "/webhooks/companion",
        json={
            "events": [
                {
                    "type": "location.enter",
                    "timestamp": "2026-03-27T09:00:00Z",
                    "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["events_received"] == 1

    # API digest route should be wired
    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-27.md").write_text("# Test Digest", encoding="utf-8")

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "integration-token"},
    )
    assert response.status_code == 200
```

Add the missing import at the top of the file:

```python
from pulse.app.config import ConnectorConfig
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_companion_api.py::test_companion_webhook_and_api_wired_in_full_app -v`
Expected: FAIL because `create_app` does not mount the API router yet.

- [ ] **Step 3: Wire API router into main.py**

In `src/pulse/app/main.py`, add the import at the top:

```python
from pulse.app.api import build_api_router
from pulse.app.auth import build_require_companion_token
```

Then inside `create_app()`, after the webhook routes and before `return app`, add:

```python
    # Wire companion app API
    auth_dep = build_require_companion_token(settings_dependency)
    api_router = build_api_router(settings_dependency, auth_dep)
    app.include_router(api_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_companion_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/main.py tests/integration/test_companion_api.py
git commit -m "feat: wire companion API and connector into main app"
```

---

### Task 7: Update config examples and documentation contract

**Files:**
- Modify: `pulse.toml.example`
- Modify: `.env.example`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/operations/runbook.md`
- Modify: `tests/unit/test_documentation_contract.py`

- [ ] **Step 1: Write the failing docs contract test additions**

Add to `CONFIG_REFERENCE_REQUIRED_SNIPPETS`:

```python
    "PULSE_COMPANION_TOKEN",
    "PULSE_FCM_SERVICE_ACCOUNT_PATH",
    "[connectors.companion]",
```

Add to `RUNBOOK_REQUIRED_SNIPPETS`:

```python
    "/webhooks/companion",
    "/api/digests",
    "/api/corrections",
    "/api/device-token",
    "device_tokens",
```

Add to `PULSE_TOML_EXAMPLE_REQUIRED_SNIPPETS`:

```python
    "[connectors.companion]",
```

Add to `ENV_EXAMPLE_REQUIRED_SNIPPETS`:

```python
    "PULSE_COMPANION_TOKEN=",
    "PULSE_FCM_SERVICE_ACCOUNT_PATH=",
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v`
Expected: FAIL because the new snippets are not documented yet.

- [ ] **Step 3: Update pulse.toml.example**

Add after the `[connectors.feeds]` section:

```toml
[connectors.companion]
enabled = false
# The companion app pushes location and health events to /webhooks/companion.
# Set PULSE_COMPANION_TOKEN in .env to enable API auth.
```

- [ ] **Step 4: Update .env.example**

Add after `PULSE_ANTHROPIC_API_KEY=`:

```
PULSE_COMPANION_TOKEN=
PULSE_FCM_SERVICE_ACCOUNT_PATH=
```

- [ ] **Step 5: Update docs/reference/configuration.md**

Add a section documenting:
- `PULSE_COMPANION_TOKEN` — shared secret for app ↔ server auth
- `PULSE_FCM_SERVICE_ACCOUNT_PATH` — path to Firebase service account JSON for push notifications
- `[connectors.companion]` — enables the companion webhook

- [ ] **Step 6: Update docs/operations/runbook.md**

Add a section documenting:
- `/webhooks/companion` — where the app pushes location/health events
- `/api/digests` — digest reading endpoints
- `/api/corrections` — correction submission endpoint
- `/api/device-token` — FCM token registration
- `device_tokens` table — stores registered push tokens

- [ ] **Step 7: Run verification**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v && uv run pytest`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pulse.toml.example .env.example docs/reference/configuration.md docs/operations/runbook.md tests/unit/test_documentation_contract.py
git commit -m "docs: document companion app backend configuration"
```

# Backend-First MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first working Pulse backend vertical slice that ingests normalized events, stores them in SQLite, writes daily digest markdown into a vault, sends Telegram briefings, and records corrections.

**Architecture:** Implement a single Python package with a thin FastAPI app over a service-oriented core. Keep domain models, repositories, vault rendering, job orchestration, and adapters separate so multiple agents can implement subsystems in parallel without conflicting.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, aiosqlite, APScheduler, httpx, pytest, pytest-asyncio

---

### Task 1: Project Skeleton And Tooling

**Files:**
- Create: `pyproject.toml`
- Create: `src/pulse/__init__.py`
- Create: `src/pulse/app/main.py`
- Create: `tests/unit/test_imports.py`

**Step 1: Write the failing test**

```python
from pulse.app.main import create_app


def test_create_app_exists():
    app = create_app()
    assert app is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_imports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse'`

**Step 3: Write minimal implementation**

```python
# src/pulse/app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(title="Pulse")
```

```toml
# pyproject.toml
[project]
name = "pulse"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi", "pydantic", "aiosqlite", "apscheduler", "httpx"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_imports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml src/pulse/__init__.py src/pulse/app/main.py tests/unit/test_imports.py
git commit -m "feat: scaffold pulse backend package"
```

### Task 2: Configuration Model

**Files:**
- Create: `src/pulse/app/config.py`
- Create: `tests/unit/test_config.py`

**Step 1: Write the failing test**

```python
from pulse.app.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.database_path == "data/pulse.db"
    assert settings.vault_path == "Pulse-Vault"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL with `ImportError` for `pulse.app.config`

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel


class Settings(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/config.py tests/unit/test_config.py
git commit -m "feat: add application settings model"
```

### Task 3: Domain Event Contracts

**Files:**
- Create: `src/pulse/domain/events.py`
- Create: `src/pulse/domain/connectors.py`
- Create: `tests/unit/test_events.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, UTC

from pulse.domain.events import Event


def test_event_model_captures_source_and_type():
    event = Event(
        id="evt-1",
        timestamp=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
        source="gmail",
        event_type="email.received",
        data={"subject": "Hello"},
    )
    assert event.source == "gmail"
    assert event.event_type == "email.received"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_events.py -v`
Expected: FAIL with `ImportError` for `pulse.domain.events`

**Step 3: Write minimal implementation**

```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    timestamp: datetime
    source: str
    event_type: str
    data: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataConnector(ABC):
    @abstractmethod
    async def pull(self, since: datetime | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/domain/events.py src/pulse/domain/connectors.py tests/unit/test_events.py
git commit -m "feat: add core event and connector contracts"
```

### Task 4: SQLite Bootstrap And Event Repository

**Files:**
- Create: `src/pulse/store/db.py`
- Create: `src/pulse/store/schema.py`
- Create: `src/pulse/store/events.py`
- Create: `tests/integration/test_event_repository.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, UTC

import pytest

from pulse.domain.events import Event
from pulse.store.db import Database
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema


@pytest.mark.asyncio
async def test_event_repository_inserts_and_lists_events(tmp_path):
    db = Database(tmp_path / "pulse.db")
    await bootstrap_schema(db)
    repo = EventRepository(db)

    await repo.upsert_events([
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Demo"},
        )
    ])

    events = await repo.list_events_for_day("2026-03-22")
    assert len(events) == 1
    assert events[0].id == "evt-1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_event_repository.py -v`
Expected: FAIL with missing database modules

**Step 3: Write minimal implementation**

```python
# src/pulse/store/schema.py
CREATE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    data TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""
```

```python
# src/pulse/store/events.py
import json

from pulse.domain.events import Event


class EventRepository:
    async def upsert_events(self, events: list[Event]) -> None:
        ...

    async def list_events_for_day(self, day: str) -> list[Event]:
        ...
```

Implement these methods fully using `INSERT OR REPLACE` and `json.dumps/json.loads`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_event_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/store/db.py src/pulse/store/schema.py src/pulse/store/events.py tests/integration/test_event_repository.py
git commit -m "feat: add sqlite event persistence"
```

### Task 5: Health Endpoint And Dependency Wiring

**Files:**
- Create: `src/pulse/app/dependencies.py`
- Modify: `src/pulse/app/main.py`
- Create: `tests/integration/test_health_api.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from pulse.app.main import create_app


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_health_api.py -v`
Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Pulse")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_health_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/dependencies.py src/pulse/app/main.py tests/integration/test_health_api.py
git commit -m "feat: add app wiring and health endpoint"
```

### Task 6: Vault Renderer And Writer

**Files:**
- Create: `src/pulse/vault/renderer.py`
- Create: `src/pulse/vault/writer.py`
- Create: `tests/unit/test_vault_renderer.py`
- Create: `tests/integration/test_vault_writer.py`

**Step 1: Write the failing test**

```python
from pulse.vault.renderer import render_daily_digest


def test_render_daily_digest_contains_sections():
    markdown = render_daily_digest(
        date_label="2026-03-22 (Sunday)",
        timeline=["07:30 - Wake up"],
        email_lines=["1 email received"],
        spending_lines=["Total: $0.00"],
        health_lines=["Steps: 1000"],
        media_lines=["Spotify: 0m"],
        tags=["#test"],
    )
    assert "## Timeline" in markdown
    assert "## Email Highlights" in markdown
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_vault_renderer.py -v`
Expected: FAIL with missing vault renderer

**Step 3: Write minimal implementation**

```python
def render_daily_digest(
    date_label: str,
    timeline: list[str],
    email_lines: list[str],
    spending_lines: list[str],
    health_lines: list[str],
    media_lines: list[str],
    tags: list[str],
) -> str:
    return f"""# {date_label}

## Timeline
- {timeline[0] if timeline else 'No notable activity'}

## Email Highlights
- {email_lines[0] if email_lines else 'No email activity'}

## Spending
- {spending_lines[0] if spending_lines else 'No spending activity'}

## Health
- {health_lines[0] if health_lines else 'No health activity'}

## Media
- {media_lines[0] if media_lines else 'No media activity'}

## Tags
{' '.join(tags) if tags else '#pulse'}
"""
```

Add a writer that creates parent directories and writes to `01-Daily/YYYY-MM-DD.md`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_vault_renderer.py tests/integration/test_vault_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/vault/renderer.py src/pulse/vault/writer.py tests/unit/test_vault_renderer.py tests/integration/test_vault_writer.py
git commit -m "feat: add vault digest rendering and writing"
```

### Task 7: Summarizer Service

**Files:**
- Create: `src/pulse/domain/llm.py`
- Create: `src/pulse/analysis/summarizer.py`
- Create: `tests/unit/test_summarizer.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, UTC

import pytest

from pulse.analysis.summarizer import DailySummarizer
from pulse.domain.events import Event


class FakeLLM:
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs):
        return "- 09:00 - Calendar event\n- 1 email received"


@pytest.mark.asyncio
async def test_summarizer_builds_digest_sections():
    summarizer = DailySummarizer(llm=FakeLLM())
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Standup"},
        )
    ]
    summary = await summarizer.summarize("2026-03-22", events)
    assert "Timeline" in summary.markdown
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_summarizer.py -v`
Expected: FAIL with missing summarizer implementation

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass
class DailySummary:
    markdown: str


class DailySummarizer:
    def __init__(self, llm):
        self.llm = llm

    async def summarize(self, day: str, events: list) -> DailySummary:
        markdown = render_daily_digest(
            date_label=f"{day} (Unknown)",
            timeline=[f"{event.timestamp:%H:%M} - {event.event_type}" for event in events],
            email_lines=["No email activity"],
            spending_lines=["Total: $0.00"],
            health_lines=["No health activity"],
            media_lines=["No media activity"],
            tags=["#pulse"],
        )
        return DailySummary(markdown=markdown)
```

Expand it enough to classify `calendar.event` and `email.received` into the right sections.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_summarizer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/domain/llm.py src/pulse/analysis/summarizer.py tests/unit/test_summarizer.py
git commit -m "feat: add daily summarizer service"
```

### Task 8: Daily Digest Job Runner

**Files:**
- Create: `src/pulse/jobs/runners.py`
- Create: `tests/integration/test_daily_digest_job.py`

**Step 1: Write the failing test**

```python
import pytest

from pulse.jobs.runners import run_daily_digest_job


@pytest.mark.asyncio
async def test_daily_digest_job_writes_markdown(tmp_path):
    result = await run_daily_digest_job(
        day="2026-03-22",
        database_path=tmp_path / "pulse.db",
        vault_path=tmp_path / "vault",
    )
    assert result.status == "success"
    assert (tmp_path / "vault" / "01-Daily" / "2026-03-22.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_daily_digest_job.py -v`
Expected: FAIL with missing job runner

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass
class JobResult:
    status: str
    detail: str


async def run_daily_digest_job(day, database_path, vault_path):
    return JobResult(status="success", detail=f"wrote {day}")
```

Then replace the stub with real repository + summarizer + writer wiring.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_daily_digest_job.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/jobs/runners.py tests/integration/test_daily_digest_job.py
git commit -m "feat: add daily digest job runner"
```

### Task 9: Notification Contracts And Telegram Channel

**Files:**
- Create: `src/pulse/domain/notifications.py`
- Create: `src/pulse/notifications/telegram.py`
- Create: `tests/unit/test_telegram_channel.py`

**Step 1: Write the failing test**

```python
import pytest

from pulse.domain.notifications import Notification
from pulse.notifications.telegram import TelegramChannel


class FakeTelegramClient:
    async def send_message(self, chat_id: str, text: str):
        return {"ok": True, "result": {"message_id": 10}}


@pytest.mark.asyncio
async def test_telegram_channel_sends_message():
    channel = TelegramChannel(bot_token="token", chat_id="123", client=FakeTelegramClient())
    result = await channel.send(Notification(title="Pulse", body="Hello", category="briefing"))
    assert result is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_telegram_channel.py -v`
Expected: FAIL with missing notification modules

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass


@dataclass
class Notification:
    title: str
    body: str
    category: str
    context_id: str | None = None
    priority: str = "normal"
```

```python
class TelegramChannel:
    def __init__(self, bot_token: str, chat_id: str, client):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = client

    async def send(self, notification):
        await self.client.send_message(self.chat_id, f"*{notification.title}*\n\n{notification.body}")
        return True
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_telegram_channel.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/domain/notifications.py src/pulse/notifications/telegram.py tests/unit/test_telegram_channel.py
git commit -m "feat: add telegram notification channel"
```

### Task 10: Morning Briefing Job

**Files:**
- Create: `src/pulse/analysis/briefing.py`
- Modify: `src/pulse/jobs/runners.py`
- Create: `tests/integration/test_morning_briefing_job.py`

**Step 1: Write the failing test**

```python
import pytest

from pulse.jobs.runners import run_morning_briefing_job


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, notification):
        self.sent.append(notification)
        return True


@pytest.mark.asyncio
async def test_morning_briefing_job_sends_notification(tmp_path):
    channel = FakeChannel()
    result = await run_morning_briefing_job(
        day="2026-03-22",
        database_path=tmp_path / "pulse.db",
        vault_path=tmp_path / "vault",
        channel=channel,
    )
    assert result.status == "success"
    assert len(channel.sent) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_morning_briefing_job.py -v`
Expected: FAIL with missing briefing job

**Step 3: Write minimal implementation**

```python
async def run_morning_briefing_job(day, database_path, vault_path, channel):
    notification = Notification(
        title="Pulse Morning Briefing",
        body=f"Your digest for {day} is ready.",
        category="briefing",
        context_id=day,
    )
    await channel.send(notification)
    return JobResult(status="success", detail="briefing sent")
```

Then expand it so the body includes key lines from the generated digest.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_morning_briefing_job.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/analysis/briefing.py src/pulse/jobs/runners.py tests/integration/test_morning_briefing_job.py
git commit -m "feat: add morning briefing notification job"
```

### Task 11: Corrections Repository And Service

**Files:**
- Create: `src/pulse/domain/corrections.py`
- Create: `src/pulse/store/corrections.py`
- Create: `src/pulse/services/corrections.py`
- Create: `tests/integration/test_corrections_service.py`

**Step 1: Write the failing test**

```python
import pytest

from pulse.services.corrections import CorrectionService


@pytest.mark.asyncio
async def test_correction_service_records_correction(tmp_path):
    service = CorrectionService(database_path=tmp_path / "pulse.db")
    result = await service.record_reply(
        context_id="digest-2026-03-22",
        message_text="That was my dentist, not doctor",
    )
    assert result.target_type == "insight"
    assert result.correction == "That was my dentist, not doctor"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_corrections_service.py -v`
Expected: FAIL with missing correction service

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class CorrectionRecord:
    id: str
    target_type: str
    target_id: str | None
    correction: str


class CorrectionService:
    async def record_reply(self, context_id: str, message_text: str) -> CorrectionRecord:
        return CorrectionRecord(
            id=str(uuid4()),
            target_type="insight",
            target_id=context_id,
            correction=message_text,
        )
```

Then replace the stub with real SQLite persistence and append-first behavior.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_corrections_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/domain/corrections.py src/pulse/store/corrections.py src/pulse/services/corrections.py tests/integration/test_corrections_service.py
git commit -m "feat: add correction persistence service"
```

### Task 12: Telegram Reply Webhook

**Files:**
- Modify: `src/pulse/app/main.py`
- Create: `tests/integration/test_telegram_webhook.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from pulse.app.main import create_app


def test_telegram_webhook_accepts_reply_payload():
    client = TestClient(create_app())
    response = client.post(
        "/webhooks/telegram",
        json={
            "message": {
                "text": "That was my dentist, not doctor",
                "reply_to_message": {"message_id": 10},
            }
        },
    )
    assert response.status_code == 202
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_telegram_webhook.py -v`
Expected: FAIL with `404 Not Found`

**Step 3: Write minimal implementation**

```python
@app.post("/webhooks/telegram", status_code=202)
async def telegram_webhook(payload: dict) -> dict[str, str]:
    return {"status": "accepted"}
```

Then wire it to the correction service and add validation for reply payloads.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_telegram_webhook.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/main.py tests/integration/test_telegram_webhook.py
git commit -m "feat: add telegram correction webhook"
```

### Task 13: Google Connector Sync State

**Files:**
- Create: `src/pulse/store/sync_state.py`
- Create: `tests/integration/test_sync_state_repository.py`

**Step 1: Write the failing test**

```python
import pytest

from pulse.store.db import Database
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


@pytest.mark.asyncio
async def test_sync_state_round_trip(tmp_path):
    db = Database(tmp_path / "pulse.db")
    await bootstrap_schema(db)
    repo = SyncStateRepository(db)

    await repo.save("calendar", "2026-03-22T09:00:00Z")
    assert await repo.load("calendar") == "2026-03-22T09:00:00Z"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_sync_state_repository.py -v`
Expected: FAIL with missing sync state repository

**Step 3: Write minimal implementation**

```python
class SyncStateRepository:
    async def save(self, source: str, cursor: str) -> None:
        ...

    async def load(self, source: str) -> str | None:
        ...
```

Back this with a `connector_sync_state` table and `INSERT OR REPLACE` semantics.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_sync_state_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/store/sync_state.py tests/integration/test_sync_state_repository.py
git commit -m "feat: add connector sync state storage"
```

### Task 14: Google Calendar Connector

**Files:**
- Create: `src/pulse/connectors/google_auth.py`
- Create: `src/pulse/connectors/calendar.py`
- Create: `tests/unit/test_calendar_connector.py`

**Step 1: Write the failing test**

```python
from pulse.connectors.calendar import GoogleCalendarConnector


class FakeCalendarClient:
    async def list_events(self, since=None):
        return [
            {
                "id": "abc",
                "summary": "Standup",
                "start": {"dateTime": "2026-03-22T09:00:00Z"},
            }
        ]


async def test_calendar_connector_normalizes_events():
    connector = GoogleCalendarConnector(client=FakeCalendarClient())
    events = await connector.pull()
    assert events[0].event_type == "calendar.event"
    assert events[0].data["title"] == "Standup"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_calendar_connector.py -v`
Expected: FAIL with missing calendar connector

**Step 3: Write minimal implementation**

```python
from datetime import datetime

from pulse.domain.events import Event


class GoogleCalendarConnector:
    def __init__(self, client):
        self.client = client

    async def pull(self, since=None) -> list[Event]:
        rows = await self.client.list_events(since=since)
        return [
            Event(
                id=f"calendar:{row['id']}",
                timestamp=datetime.fromisoformat(row["start"]["dateTime"].replace("Z", "+00:00")),
                source="calendar",
                event_type="calendar.event",
                data={"title": row.get("summary", "Untitled")},
            )
            for row in rows
        ]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_calendar_connector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/connectors/google_auth.py src/pulse/connectors/calendar.py tests/unit/test_calendar_connector.py
git commit -m "feat: add google calendar connector"
```

### Task 15: Gmail Connector

**Files:**
- Create: `src/pulse/connectors/gmail.py`
- Create: `tests/unit/test_gmail_connector.py`

**Step 1: Write the failing test**

```python
from pulse.connectors.gmail import GmailConnector


class FakeGmailClient:
    async def list_messages(self, since=None):
        return [
            {
                "id": "msg-1",
                "internalDate": "1774173600000",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Advisor update"},
                        {"name": "From", "value": "advisor@example.com"},
                    ]
                },
            }
        ]


async def test_gmail_connector_normalizes_email_events():
    connector = GmailConnector(client=FakeGmailClient())
    events = await connector.pull()
    assert events[0].event_type == "email.received"
    assert events[0].data["subject"] == "Advisor update"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail_connector.py -v`
Expected: FAIL with missing Gmail connector

**Step 3: Write minimal implementation**

```python
from datetime import UTC, datetime

from pulse.domain.events import Event


class GmailConnector:
    def __init__(self, client):
        self.client = client

    async def pull(self, since=None) -> list[Event]:
        rows = await self.client.list_messages(since=since)
        events = []
        for row in rows:
            headers = {item["name"].lower(): item["value"] for item in row["payload"]["headers"]}
            timestamp = datetime.fromtimestamp(int(row["internalDate"]) / 1000, tz=UTC)
            events.append(
                Event(
                    id=f"gmail:{row['id']}",
                    timestamp=timestamp,
                    source="gmail",
                    event_type="email.received",
                    data={"subject": headers.get("subject", ""), "sender": headers.get("from", "")},
                )
            )
        return events
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gmail_connector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/connectors/gmail.py tests/unit/test_gmail_connector.py
git commit -m "feat: add gmail connector"
```

### Task 16: End-To-End Vertical Slice

**Files:**
- Create: `tests/e2e/test_backend_first_mvp.py`
- Modify: `src/pulse/jobs/runners.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

```python
import pytest


@pytest.mark.asyncio
async def test_backend_first_vertical_slice(tmp_path):
    """Ingest events, write digest, send briefing, and record a correction."""
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_backend_first_mvp.py -v`
Expected: FAIL with `assert False`

**Step 3: Write minimal implementation**

Replace the placeholder with a real e2e test that:

```python
1. boots a temporary SQLite database,
2. inserts one calendar event and one email event,
3. runs `run_daily_digest_job`,
4. runs `run_morning_briefing_job` with a fake channel,
5. POSTs a Telegram-style reply payload to `/webhooks/telegram`,
6. asserts the correction exists in SQLite,
7. asserts `01-Daily/2026-03-22.md` exists.
```

Implement only the missing glue required to make this test pass.

**Step 4: Run test to verify it passes**

Run: `pytest tests/e2e/test_backend_first_mvp.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/e2e/test_backend_first_mvp.py src/pulse/jobs/runners.py src/pulse/app/main.py
git commit -m "feat: prove backend-first mvp vertical slice"
```

### Task 17: Scheduler Registration

**Files:**
- Create: `src/pulse/jobs/scheduler.py`
- Create: `tests/unit/test_scheduler.py`

**Step 1: Write the failing test**

```python
from pulse.jobs.scheduler import build_scheduler


def test_scheduler_registers_core_jobs():
    scheduler = build_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "daily_digest" in job_ids
    assert "morning_briefing" in job_ids
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: FAIL with missing scheduler module

**Step 3: Write minimal implementation**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: None, "cron", hour=23, minute=0, id="daily_digest")
    scheduler.add_job(lambda: None, "cron", hour=7, minute=30, id="morning_briefing")
    return scheduler
```

Then replace lambda stubs with job runner callables once the dependencies are available.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/jobs/scheduler.py tests/unit/test_scheduler.py
git commit -m "feat: register scheduled backend jobs"
```

### Task 18: Developer Docs And Env Sample

**Files:**
- Create: `.env.example`
- Create: `README.md`

**Step 1: Write the failing test**

There is no code test for this task. Use a manual verification step instead.

**Step 2: Run manual verification to confirm docs are missing**

Run: `python -c "from pathlib import Path; print(Path('.env.example').exists(), Path('README.md').exists())"`
Expected: `False False`

**Step 3: Write minimal implementation**

Create `.env.example` with:

```dotenv
PULSE_DATABASE_PATH=data/pulse.db
PULSE_VAULT_PATH=Pulse-Vault
PULSE_TIMEZONE=UTC
PULSE_TELEGRAM_BOT_TOKEN=
PULSE_TELEGRAM_CHAT_ID=
PULSE_GOOGLE_CLIENT_ID=
PULSE_GOOGLE_CLIENT_SECRET=
```

Create `README.md` with:

```markdown
# Pulse

Backend-first MVP for a self-hosted personal intelligence agent.

## Run tests

`pytest`

## Start app

`uvicorn pulse.app.main:create_app --factory --reload`
```

**Step 4: Run manual verification to confirm docs exist**

Run: `python -c "from pathlib import Path; print(Path('.env.example').exists(), Path('README.md').exists())"`
Expected: `True True`

**Step 5: Commit**

```bash
git add .env.example README.md
git commit -m "docs: add backend mvp setup documentation"
```

### Task 19: Full Verification

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

No new code test. This task is for final verification and any documentation updates required by failures.

**Step 2: Run verification to expose remaining issues**

Run: `pytest -v`
Expected: all tests pass; if not, capture failing modules and fix them before continuing.

**Step 3: Write minimal implementation**

Make only the smallest fixes required for any failing tests uncovered by the full suite. If behavior changed, update `README.md` commands or setup notes.

**Step 4: Run verification to confirm success**

Run: `pytest -v`
Expected: PASS for the full suite

**Step 5: Commit**

```bash
git add README.md src tests
git commit -m "test: verify backend-first mvp end to end"
```

## Multi-Agent Execution Recommendation

If multiple agents implement this plan, split ownership like this:

- Agent 1: Tasks 1-5
- Agent 2: Tasks 6-8
- Agent 3: Tasks 9-12
- Agent 4: Tasks 13-15
- Agent 5: Tasks 16-19 after the earlier task groups merge cleanly

Shared rules for all agents:

- do not change the `Event` schema without updating all dependent tests,
- do not bypass TDD,
- prefer fakes over live APIs in tests,
- integrate frequently after each task group,
- run the narrowest relevant test command before handing work back.

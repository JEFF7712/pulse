# Google OAuth2 & LLM-Powered Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable real Google Calendar/Gmail data ingestion via OAuth2 and upgrade the daily summarizer to produce LLM-powered digests with insights using Claude as the default provider.

**Architecture:** Extend the existing backend-first MVP with four layers: (1) OAuth2 token management in SQLite, (2) real Google API clients using httpx, (3) a provider-agnostic LLM abstraction with a Claude adapter, (4) LLM-powered summarization that falls back to raw listings when no API key is configured.

**Tech Stack:** Python 3.12+, FastAPI, httpx, aiosqlite, anthropic SDK, pytest, pytest-asyncio

---

### Task 1: OAuth Token Storage

**Files:**
- Create: `src/pulse/store/oauth.py`
- Modify: `src/pulse/store/schema.py`
- Create: `tests/integration/test_oauth_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_oauth_store.py
from datetime import datetime, UTC

import pytest

from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema
from pulse.store.oauth import OAuthTokenRepository


@pytest.mark.asyncio
async def test_oauth_token_round_trip(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)

        await repo.save(
            provider="google",
            access_token="access-123",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
            scopes="calendar.readonly gmail.readonly",
        )

        token = await repo.load("google")
        assert token is not None
        assert token["access_token"] == "access-123"
        assert token["refresh_token"] == "refresh-456"
        assert token["scopes"] == "calendar.readonly gmail.readonly"


@pytest.mark.asyncio
async def test_oauth_token_returns_none_when_missing(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)
        assert await repo.load("google") is None


@pytest.mark.asyncio
async def test_oauth_token_upsert_updates_existing(tmp_path):
    async with connect_db(tmp_path / "pulse.db") as db:
        await bootstrap_schema(db)
        repo = OAuthTokenRepository(db)

        await repo.save(
            provider="google",
            access_token="old",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
            scopes="calendar.readonly",
        )
        await repo.save(
            provider="google",
            access_token="new",
            refresh_token="refresh-456",
            expires_at=datetime(2026, 3, 23, 13, 0, tzinfo=UTC),
            scopes="calendar.readonly",
        )

        token = await repo.load("google")
        assert token["access_token"] == "new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/integration/test_oauth_store.py -v`
Expected: FAIL with `ImportError` for `pulse.store.oauth`

- [ ] **Step 3: Write minimal implementation**

Add the `oauth_tokens` table to `src/pulse/store/schema.py`:

```python
# Append after the corrections table creation in bootstrap_schema:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            provider TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            scopes TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
```

Create `src/pulse/store/oauth.py`:

```python
from datetime import datetime

import aiosqlite


class OAuthTokenRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(
        self,
        provider: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        scopes: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at, scopes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                scopes = excluded.scopes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (provider, access_token, refresh_token, expires_at.isoformat(), scopes),
        )
        await self._db.commit()

    async def load(self, provider: str) -> dict[str, str] | None:
        cursor = await self._db.execute(
            "SELECT access_token, refresh_token, expires_at, scopes FROM oauth_tokens WHERE provider = ?",
            (provider,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return {
            "access_token": row[0],
            "refresh_token": row[1],
            "expires_at": row[2],
            "scopes": row[3],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/integration/test_oauth_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/store/oauth.py src/pulse/store/schema.py tests/integration/test_oauth_store.py
git commit -m "feat: add oauth token storage in sqlite"
```

---

### Task 2: Google OAuth2 Auth Module

**Files:**
- Replace: `src/pulse/connectors/google_auth.py`
- Create: `tests/unit/test_google_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_auth.py
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock

import pytest

from pulse.connectors.google_auth import GoogleOAuth, build_authorization_url


def test_build_authorization_url_includes_state_and_scopes():
    url, state = build_authorization_url(
        client_id="test-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )
    assert "test-client-id" in url
    assert "calendar.readonly" in url
    assert "gmail.readonly" in url
    assert state  # non-empty random string
    assert f"state={state}" in url


@pytest.mark.asyncio
async def test_exchange_code_stores_tokens():
    mock_http = AsyncMock()
    mock_http.post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly",
        },
        raise_for_status=lambda: None,
    )

    mock_repo = AsyncMock()

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=mock_http,
    )

    await oauth.exchange_code("auth-code-123")

    mock_http.post.assert_called_once()
    mock_repo.save.assert_called_once()
    call_kwargs = mock_repo.save.call_args
    assert call_kwargs.kwargs["access_token"] == "access-new"
    assert call_kwargs.kwargs["refresh_token"] == "refresh-new"


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expired():
    expired = datetime.now(UTC) - timedelta(minutes=5)
    mock_repo = AsyncMock()
    mock_repo.load.return_value = {
        "access_token": "old-access",
        "refresh_token": "refresh-tok",
        "expires_at": expired.isoformat(),
        "scopes": "calendar.readonly",
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "new-access",
            "expires_in": 3600,
        },
        raise_for_status=lambda: None,
    )

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=mock_http,
    )

    token = await oauth.get_access_token()
    assert token == "new-access"
    mock_http.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_access_token_returns_cached_when_valid():
    future = datetime.now(UTC) + timedelta(hours=1)
    mock_repo = AsyncMock()
    mock_repo.load.return_value = {
        "access_token": "still-valid",
        "refresh_token": "refresh-tok",
        "expires_at": future.isoformat(),
        "scopes": "calendar.readonly",
    }

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=AsyncMock(),
    )

    token = await oauth.get_access_token()
    assert token == "still-valid"


@pytest.mark.asyncio
async def test_get_access_token_returns_none_when_no_tokens():
    mock_repo = AsyncMock()
    mock_repo.load.return_value = None

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=AsyncMock(),
    )

    token = await oauth.get_access_token()
    assert token is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_auth.py -v`
Expected: FAIL with `ImportError` for `pulse.connectors.google_auth.GoogleOAuth`

- [ ] **Step 3: Write minimal implementation**

Replace `src/pulse/connectors/google_auth.py`:

```python
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/gmail.readonly"
)


def build_authorization_url(
    client_id: str, redirect_uri: str
) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH_URL}?{params}", state


class GoogleOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_repo,
        http_client,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_repo = token_repo
        self._http_client = http_client

    async def exchange_code(self, code: str) -> None:
        response = await self._http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()

        expires_at = datetime.now(UTC) + timedelta(seconds=data["expires_in"])
        await self._token_repo.save(
            provider="google",
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=expires_at,
            scopes=data.get("scope", SCOPES),
        )

    async def get_access_token(self) -> str | None:
        token_data = await self._token_repo.load("google")
        if token_data is None:
            return None

        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if expires_at > datetime.now(UTC) + timedelta(minutes=2):
            return token_data["access_token"]

        return await self._refresh(token_data["refresh_token"])

    async def _refresh(self, refresh_token: str) -> str:
        response = await self._http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

        expires_at = datetime.now(UTC) + timedelta(seconds=data["expires_in"])
        await self._token_repo.save(
            provider="google",
            access_token=data["access_token"],
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=data.get("scope", SCOPES),
        )
        return data["access_token"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/connectors/google_auth.py tests/unit/test_google_auth.py
git commit -m "feat: implement google oauth2 auth module"
```

---

### Task 3: OAuth Endpoints In FastAPI

**Files:**
- Modify: `src/pulse/app/main.py`
- Modify: `src/pulse/app/config.py`
- Create: `tests/integration/test_google_auth_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_google_auth_endpoints.py
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.main import create_app


def test_auth_google_redirects_to_google():
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
    )
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]
    assert "test-cid" in response.headers["location"]


def test_auth_google_returns_503_when_not_configured():
    settings = Settings()  # no google_client_id
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google")
    assert response.status_code == 503


def test_auth_google_callback_rejects_missing_state():
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
    )
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google/callback?code=abc&state=wrong")
    assert response.status_code == 400


def test_auth_google_callback_happy_path(tmp_path, monkeypatch):
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
        database_path=str(tmp_path / "pulse.db"),
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    # Step 1: initiate OAuth to capture the state token
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    import re
    state_match = re.search(r"state=([^&]+)", location)
    assert state_match is not None
    state = state_match.group(1)

    # Step 2: mock the token exchange HTTP call
    from unittest.mock import AsyncMock, patch
    mock_response = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "access-ok",
            "refresh_token": "refresh-ok",
            "expires_in": 3600,
            "scope": "calendar.readonly gmail.readonly",
        },
        raise_for_status=lambda: None,
    )
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        response = client.get(f"/auth/google/callback?code=authcode123&state={state}")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/integration/test_google_auth_endpoints.py -v`
Expected: FAIL with missing endpoints (404)

- [ ] **Step 3: Write minimal implementation**

Add to `src/pulse/app/config.py`:

```python
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
```

(LLM config fields `anthropic_api_key` and `llm_model` are added later in Task 9.)

Add OAuth endpoints to `src/pulse/app/main.py`. Add these imports at the top:

```python
from fastapi.responses import RedirectResponse
from pulse.connectors.google_auth import GoogleOAuth, build_authorization_url
from pulse.store.oauth import OAuthTokenRepository
import httpx
```

Add inside `create_app`, after the telegram_webhook endpoint:

```python
    # In-memory state store for CSRF protection
    _pending_oauth_states: set[str] = set()

    @app.get("/auth/google")
    async def auth_google(
        settings: Annotated[Settings, Depends(settings_dependency)],
    ):
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=503, detail="Google OAuth not configured.")

        url, state = build_authorization_url(
            client_id=settings.google_client_id,
            redirect_uri=settings.google_redirect_uri,
        )
        _pending_oauth_states.add(state)
        return RedirectResponse(url=url, status_code=307)

    @app.get("/auth/google/callback")
    async def auth_google_callback(
        code: str,
        state: str,
        settings: Annotated[Settings, Depends(settings_dependency)],
    ):
        if state not in _pending_oauth_states:
            raise HTTPException(status_code=400, detail="Invalid OAuth state.")
        _pending_oauth_states.discard(state)

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            token_repo = OAuthTokenRepository(db)
            async with httpx.AsyncClient() as http_client:
                oauth = GoogleOAuth(
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    redirect_uri=settings.google_redirect_uri,
                    token_repo=token_repo,
                    http_client=http_client,
                )
                await oauth.exchange_code(code)

        return {"status": "authorized"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/integration/test_google_auth_endpoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/main.py src/pulse/app/config.py tests/integration/test_google_auth_endpoints.py
git commit -m "feat: add google oauth2 endpoints with csrf protection"
```

---

### Task 4: Real Google Calendar Client

**Files:**
- Modify: `src/pulse/connectors/calendar.py`
- Create: `tests/unit/test_google_calendar_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_calendar_client.py
from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest

from pulse.connectors.calendar import GoogleCalendarClient


@pytest.mark.asyncio
async def test_calendar_client_lists_events():
    mock_http = AsyncMock()
    mock_http.get.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Standup",
                    "start": {"dateTime": "2026-03-22T09:00:00Z"},
                }
            ],
        },
        raise_for_status=lambda: None,
    )

    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = "access-tok"

    client = GoogleCalendarClient(oauth=mock_oauth, http_client=mock_http)
    events = await client.list_events(since=datetime(2026, 3, 22, tzinfo=UTC))

    assert len(events) == 1
    assert events[0]["id"] == "evt-1"
    mock_http.get.assert_called_once()


@pytest.mark.asyncio
async def test_calendar_client_returns_empty_when_no_token():
    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = None

    client = GoogleCalendarClient(oauth=mock_oauth, http_client=AsyncMock())
    events = await client.list_events()
    assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_calendar_client.py -v`
Expected: FAIL with `ImportError` for `GoogleCalendarClient`

- [ ] **Step 3: Write minimal implementation**

Add `GoogleCalendarClient` to `src/pulse/connectors/calendar.py`:

```python
import logging

CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    def __init__(self, oauth, http_client) -> None:
        self._oauth = oauth
        self._http = http_client

    async def list_events(self, since: datetime | None = None) -> list[dict]:
        token = await self._oauth.get_access_token()
        if token is None:
            logger.warning("No Google OAuth token available; skipping calendar pull.")
            return []

        params: dict[str, str] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        if since is not None:
            params["timeMin"] = since.isoformat()

        all_items: list[dict] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            response = await self._http.get(
                CALENDAR_EVENTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            data = response.json()
            all_items.extend(data.get("items", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_items
```

Add an optional `sync_state_repo` to the connector constructor and update cursor after pull:

```python
class GoogleCalendarConnector(Connector):
    def __init__(self, client: Any, sync_state_repo=None) -> None:
        self._client = client
        self._sync_state_repo = sync_state_repo

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_events(since=since)
        events = [self._to_event(row) for row in rows]
        if events and self._sync_state_repo is not None:
            latest = max(e.timestamp for e in events)
            await self._sync_state_repo.save("calendar", latest.isoformat())
        return events
```

Also add a `from_settings` classmethod to `GoogleCalendarConnector`. The caller owns the `httpx.AsyncClient` lifetime and passes it in to avoid resource leaks:

```python
    @classmethod
    async def from_settings(
        cls, settings, db: aiosqlite.Connection, http_client=None
    ) -> "GoogleCalendarConnector":
        from pulse.connectors.google_auth import GoogleOAuth
        from pulse.store.oauth import OAuthTokenRepository

        import httpx

        token_repo = OAuthTokenRepository(db)
        if http_client is None:
            http_client = httpx.AsyncClient()
        oauth = GoogleOAuth(
            client_id=settings.google_client_id or "",
            client_secret=settings.google_client_secret or "",
            redirect_uri=settings.google_redirect_uri,
            token_repo=token_repo,
            http_client=http_client,
        )
        client = GoogleCalendarClient(oauth=oauth, http_client=http_client)
        sync_repo = SyncStateRepository(db)
        return cls(client=client, sync_state_repo=sync_repo)
```

Add `import aiosqlite` and `import logging` to the top, and add `from pulse.store.sync_state import SyncStateRepository` inside `from_settings`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_calendar_client.py tests/unit/test_calendar_connector.py -v`
Expected: PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/pulse/connectors/calendar.py tests/unit/test_google_calendar_client.py
git commit -m "feat: add real google calendar api client"
```

---

### Task 5: Real Gmail Client

**Files:**
- Modify: `src/pulse/connectors/gmail.py`
- Create: `tests/unit/test_google_gmail_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_google_gmail_client.py
from unittest.mock import AsyncMock

import pytest

from pulse.connectors.gmail import GoogleGmailClient


@pytest.mark.asyncio
async def test_gmail_client_lists_messages():
    mock_list_resp = AsyncMock(
        status_code=200,
        json=lambda: {"messages": [{"id": "msg-1"}]},
        raise_for_status=lambda: None,
    )
    mock_detail_resp = AsyncMock(
        status_code=200,
        json=lambda: {
            "id": "msg-1",
            "internalDate": "1774173600000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Hello"},
                    {"name": "From", "value": "test@example.com"},
                ]
            },
        },
        raise_for_status=lambda: None,
    )

    mock_http = AsyncMock()
    mock_http.get.side_effect = [mock_list_resp, mock_detail_resp]

    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = "access-tok"

    client = GoogleGmailClient(oauth=mock_oauth, http_client=mock_http)
    messages = await client.list_messages()

    assert len(messages) == 1
    assert messages[0]["id"] == "msg-1"


@pytest.mark.asyncio
async def test_gmail_client_returns_empty_when_no_token():
    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = None

    client = GoogleGmailClient(oauth=mock_oauth, http_client=AsyncMock())
    messages = await client.list_messages()
    assert messages == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_gmail_client.py -v`
Expected: FAIL with `ImportError` for `GoogleGmailClient`

- [ ] **Step 3: Write minimal implementation**

Add `GoogleGmailClient` to `src/pulse/connectors/gmail.py`:

```python
import logging

GMAIL_LIST_URL = "https://www.googleapis.com/gmail/v1/users/me/messages"
GMAIL_MESSAGE_URL = "https://www.googleapis.com/gmail/v1/users/me/messages/{msg_id}"

logger = logging.getLogger(__name__)


class GoogleGmailClient:
    def __init__(self, oauth, http_client) -> None:
        self._oauth = oauth
        self._http = http_client

    async def list_messages(self, since: datetime | None = None) -> list[dict]:
        token = await self._oauth.get_access_token()
        if token is None:
            logger.warning("No Google OAuth token available; skipping gmail pull.")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, str] = {"maxResults": "100"}
        if since is not None:
            epoch = int(since.timestamp())
            params["q"] = f"after:{epoch}"

        response = await self._http.get(GMAIL_LIST_URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        message_stubs = data.get("messages", [])
        if not message_stubs:
            return []

        results = []
        for stub in message_stubs:
            detail_resp = await self._http.get(
                GMAIL_MESSAGE_URL.format(msg_id=stub["id"]),
                params={"format": "metadata", "metadataHeaders": "Subject,From"},
                headers=headers,
            )
            detail_resp.raise_for_status()
            results.append(detail_resp.json())

        return results
```

Add the same optional `sync_state_repo` pattern to `GmailConnector`:

```python
class GmailConnector(Connector):
    def __init__(self, client: Any, sync_state_repo=None) -> None:
        self._client = client
        self._sync_state_repo = sync_state_repo

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_messages(since=since)
        events = [self._to_event(row) for row in rows]
        if events and self._sync_state_repo is not None:
            latest = max(e.timestamp for e in events)
            await self._sync_state_repo.save("gmail", latest.isoformat())
        return events
```

Also add a `from_settings` classmethod to `GmailConnector`. Same pattern — caller owns the `httpx.AsyncClient`:

```python
    @classmethod
    async def from_settings(
        cls, settings, db: aiosqlite.Connection, http_client=None
    ) -> "GmailConnector":
        from pulse.connectors.google_auth import GoogleOAuth
        from pulse.store.oauth import OAuthTokenRepository

        import httpx

        token_repo = OAuthTokenRepository(db)
        if http_client is None:
            http_client = httpx.AsyncClient()
        oauth = GoogleOAuth(
            client_id=settings.google_client_id or "",
            client_secret=settings.google_client_secret or "",
            redirect_uri=settings.google_redirect_uri,
            token_repo=token_repo,
            http_client=http_client,
        )
        client = GoogleGmailClient(oauth=oauth, http_client=http_client)
        sync_repo = SyncStateRepository(db)
        return cls(client=client, sync_state_repo=sync_repo)
```

Add `import aiosqlite` and `import logging` to the top, and add `from pulse.store.sync_state import SyncStateRepository` inside `from_settings`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_google_gmail_client.py tests/unit/test_gmail_connector.py -v`
Expected: PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/pulse/connectors/gmail.py tests/unit/test_google_gmail_client.py
git commit -m "feat: add real gmail api client"
```

---

### Task 6: LLM Provider Protocol And Claude Adapter

**Files:**
- Create: `src/pulse/llm/__init__.py`
- Create: `src/pulse/llm/base.py`
- Create: `src/pulse/llm/claude.py`
- Delete: `src/pulse/domain/llm.py`
- Create: `tests/unit/test_llm_claude.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_claude.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from pulse.llm.base import LLMProvider
from pulse.llm.claude import ClaudeProvider


@pytest.mark.asyncio
async def test_claude_provider_sends_message_and_returns_text():
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Here is your summary.")]
    mock_client.messages.create.return_value = mock_response

    provider = ClaudeProvider(client=mock_client, model="claude-sonnet-4-20250514")
    result = await provider.complete(
        system_prompt="You are a helpful assistant.",
        user_prompt="Summarize my day.",
    )

    assert result == "Here is your summary."
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Summarize my day."}],
    )


def test_claude_provider_satisfies_llm_provider_protocol():
    # Structural typing check — ClaudeProvider should be assignable to LLMProvider
    provider: LLMProvider = ClaudeProvider(client=AsyncMock(), model="test")
    assert provider is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_llm_claude.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pulse.llm'`

- [ ] **Step 3: Write minimal implementation**

Create `src/pulse/llm/__init__.py`:

```python
"""LLM provider abstraction."""
```

Create `src/pulse/llm/base.py`:

```python
from typing import Protocol


class LLMProvider(Protocol):
    async def complete(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> str: ...
```

Create `src/pulse/llm/claude.py`:

```python
class ClaudeProvider:
    def __init__(self, client, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=kwargs.get("max_tokens", 4096),
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
```

Delete `src/pulse/domain/llm.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_llm_claude.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for breakage**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest -v`
Expected: PASS — `domain/llm.py` is not imported by any existing code (the summarizer doesn't use it yet)

- [ ] **Step 6: Commit**

```bash
git rm src/pulse/domain/llm.py
git add src/pulse/llm/__init__.py src/pulse/llm/base.py src/pulse/llm/claude.py tests/unit/test_llm_claude.py
git commit -m "feat: add llm provider protocol and claude adapter"
```

---

### Task 7: LLM-Powered Summarizer

**Files:**
- Modify: `src/pulse/analysis/summarizer.py`
- Modify: `src/pulse/vault/renderer.py`
- Modify: `tests/unit/test_summarizer.py`
- Create: `tests/unit/test_summarizer_with_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_summarizer_with_llm.py
from datetime import date, datetime, UTC

import pytest

from pulse.analysis.summarizer import DailySummarizer, DailySummary
from pulse.domain.events import Event


class FakeLLM:
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return (
            "## Timeline\n"
            "- 09:00 Standup with team\n"
            "\n"
            "## Email Highlights\n"
            "- Advisor sent portfolio update\n"
            "\n"
            "## Spending\n"
            "- No spending recorded.\n"
            "\n"
            "## Health\n"
            "- No health updates.\n"
            "\n"
            "## Media\n"
            "- No media activity.\n"
            "\n"
            "## Insights\n"
            "- Light day with only 1 meeting\n"
            "- Email from advisor may need follow-up\n"
        )


@pytest.mark.asyncio
async def test_summarizer_with_llm_produces_insights():
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Standup"},
        ),
    ]
    summarizer = DailySummarizer(llm=FakeLLM())
    summary = await summarizer.summarize(date(2026, 3, 22), events)

    assert isinstance(summary, DailySummary)
    assert "## Insights" in summary.markdown
    assert "Light day" in summary.markdown
    assert "## Timeline" in summary.markdown


@pytest.mark.asyncio
async def test_summarizer_without_llm_falls_back_to_raw():
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Standup"},
        ),
    ]
    summarizer = DailySummarizer()
    summary = await summarizer.summarize(date(2026, 3, 22), events)

    assert "## Timeline" in summary.markdown
    assert "Standup" in summary.markdown
    assert "## Insights" not in summary.markdown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_summarizer_with_llm.py -v`
Expected: FAIL — `DailySummarizer` doesn't accept `llm` param and `summarize` is not async

- [ ] **Step 3: Write minimal implementation**

Update `src/pulse/vault/renderer.py` — add `insights_items` parameter:

```python
def render_daily_digest(
    *,
    date_label: str,
    timeline_items: list[str],
    email_highlights: list[str],
    spending_items: list[str],
    health_items: list[str],
    media_items: list[str],
    tags: list[str],
    insights_items: list[str] | None = None,
) -> str:
    sections = [
        ("Timeline", timeline_items, "No timeline entries."),
        ("Email Highlights", email_highlights, "No email highlights."),
        ("Spending", spending_items, "No spending recorded."),
        ("Health", health_items, "No health updates."),
        ("Media", media_items, "No media activity."),
    ]
    if insights_items is not None:
        sections.append(("Insights", insights_items, "No insights."))

    sections.append(("Tags", tags, "No tags."))

    lines = [f"# {date_label}", ""]

    for index, (title, items, fallback) in enumerate(sections):
        lines.append(f"## {title}")
        lines.extend(_render_items(items, fallback))
        if index < len(sections) - 1:
            lines.append("")

    return "\n".join(lines)
```

Update `src/pulse/analysis/summarizer.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = (
    "You are a personal assistant summarizing one day's activity for a single user. "
    "Return markdown with these exact section headers: "
    "## Timeline, ## Email Highlights, ## Spending, ## Health, ## Media, ## Insights. "
    "Use bullet points, not paragraphs. Be concise. "
    "In the Insights section, identify patterns, anomalies, or notable observations "
    "(e.g., 'Unusually busy morning — 4 meetings before noon', 'No emails after 6pm')."
)


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def __init__(self, llm=None) -> None:
        self._llm = llm

    async def summarize(self, day: date, events: list[Event]) -> DailySummary:
        if self._llm is not None:
            return await self._summarize_with_llm(day, events)
        return self._summarize_raw(day, events)

    async def _summarize_with_llm(self, day: date, events: list[Event]) -> DailySummary:
        event_lines = "\n".join(
            f"- [{e.timestamp:%H:%M}] {e.source}/{e.event_type}: {_event_text(e)}"
            for e in sorted(events, key=lambda item: item.timestamp)
        )
        user_prompt = f"Date: {day.isoformat()}\n\nEvents:\n{event_lines}"

        try:
            llm_response = await self._llm.complete(
                system_prompt=SUMMARIZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return self._parse_llm_response(day, llm_response)
        except Exception:
            logger.warning("LLM call failed; falling back to raw summarization.", exc_info=True)
            return self._summarize_raw(day, events)

    def _parse_llm_response(self, day: date, response: str) -> DailySummary:
        sections: dict[str, list[str]] = {}
        current_section: str | None = None

        for line in response.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped.removeprefix("## ").strip()
                sections.setdefault(current_section, [])
            elif current_section and stripped.startswith("- "):
                sections[current_section].append(stripped.removeprefix("- ").strip())

        insights = sections.get("Insights")

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=sections.get("Timeline", []),
            email_highlights=sections.get("Email Highlights", []),
            spending_items=sections.get("Spending", []),
            health_items=sections.get("Health", []),
            media_items=sections.get("Media", []),
            tags=[],
            insights_items=insights,
        )
        return DailySummary(day=day, markdown=markdown)

    def _summarize_raw(self, day: date, events: list[Event]) -> DailySummary:
        timeline_items: list[str] = []
        email_highlights: list[str] = []

        for event in sorted(events, key=lambda item: item.timestamp):
            if event.event_type == "calendar.event":
                timeline_items.append(_event_text(event, "title"))
                continue
            if event.event_type == "email.received":
                email_highlights.append(_event_text(event, "subject"))
                continue
            timeline_items.append(_event_text(event))

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=timeline_items,
            email_highlights=email_highlights,
            spending_items=[],
            health_items=[],
            media_items=[],
            tags=[],
        )
        return DailySummary(day=day, markdown=markdown)


def _event_text(event: Event, preferred_key: str | None = None) -> str:
    if preferred_key is not None:
        value = event.data.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return event.event_type
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/unit/test_summarizer_with_llm.py -v`
Expected: PASS

- [ ] **Step 5: Update existing summarizer tests for async**

In `tests/unit/test_summarizer.py`:

1. **Delete** `test_daily_summarizer_does_not_accept_an_llm_dependency_yet` entirely — this test asserts `DailySummarizer(llm=object())` raises `TypeError`, which is now intentionally valid behavior.
2. Convert `test_daily_summarizer_renders_markdown_digest_from_events` to async:
   - Add `@pytest.mark.asyncio` decorator
   - Change `def` to `async def`
   - Change `DailySummarizer().summarize(day, events)` to `await DailySummarizer().summarize(day, events)`

- [ ] **Step 6: Run full test suite**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/analysis/summarizer.py src/pulse/vault/renderer.py tests/unit/test_summarizer_with_llm.py tests/unit/test_summarizer.py
git commit -m "feat: add llm-powered summarization with insights"
```

---

### Task 8: Update Runners And Briefing For Async Summarizer + LLM

**Files:**
- Modify: `src/pulse/jobs/runners.py`
- Modify: `src/pulse/analysis/briefing.py`
- Modify: `tests/integration/test_daily_digest_job.py`
- Modify: `tests/integration/test_morning_briefing_job.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/integration/test_morning_briefing_job.py or create tests/integration/test_briefing_with_llm.py
from datetime import date

import pytest

from pulse.analysis.briefing import build_morning_briefing


class FakeLLM:
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "Light day ahead. 1 meeting at 9am. Check advisor email."


@pytest.mark.asyncio
async def test_build_morning_briefing_with_llm():
    notification = await build_morning_briefing(
        day=date(2026, 3, 22),
        digest_markdown="## Timeline\n- 09:00 Standup\n",
        llm=FakeLLM(),
    )
    assert "Light day ahead" in notification.body


@pytest.mark.asyncio
async def test_build_morning_briefing_without_llm_falls_back():
    notification = await build_morning_briefing(
        day=date(2026, 3, 22),
        digest_markdown="## Timeline\n- 09:00 Standup\n",
    )
    assert "09:00 Standup" in notification.body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/integration/test_briefing_with_llm.py -v`
Expected: FAIL — `build_morning_briefing` is sync and doesn't accept `llm` param

- [ ] **Step 3: Write minimal implementation**

Update `src/pulse/analysis/briefing.py`:

```python
import logging
from datetime import date

from pulse.domain.notifications import Notification

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM_PROMPT = (
    "You are a personal assistant. Summarize this daily digest into a concise "
    "3-5 line morning briefing message. Use plain text, no markdown. "
    "Focus on what matters most for the day ahead."
)


async def build_morning_briefing(
    day: date, digest_markdown: str, llm=None
) -> Notification:
    if llm is not None:
        try:
            body = await llm.complete(
                system_prompt=BRIEFING_SYSTEM_PROMPT,
                user_prompt=digest_markdown,
            )
            return Notification(
                title=f"Morning briefing for {day.isoformat()}",
                body=body,
                category="morning_briefing",
                context_id=day.isoformat(),
            )
        except Exception:
            logger.warning("LLM call failed for briefing; using fallback.", exc_info=True)

    bullet_lines = [
        line.strip() for line in digest_markdown.splitlines() if line.startswith("- ")
    ]
    key_lines = bullet_lines[:3]

    body_lines = ["Here are the key points for your day."]
    if key_lines:
        body_lines.extend(["", *key_lines])
    else:
        body_lines.extend(["", "- No digest highlights available."])

    return Notification(
        title=f"Morning briefing for {day.isoformat()}",
        body="\n".join(body_lines),
        category="morning_briefing",
        context_id=day.isoformat(),
    )
```

Update `src/pulse/jobs/runners.py` — make `_build_daily_summary` use async summarizer and wire LLM:

```python
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulse.analysis.briefing import build_morning_briefing
from pulse.domain.notifications import Notification
from pulse.domain.notifications import append_reply_context
from pulse.domain.notifications import NotificationChannel
from pulse.analysis.summarizer import DailySummarizer
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.vault.writer import write_daily_digest


@dataclass(slots=True)
class JobResult:
    status: str
    detail: str


async def run_daily_digest_job(
    day: date, database_path: str | Path, vault_path: str | Path, llm=None
) -> JobResult:
    summary = await _build_daily_summary(day=day, database_path=database_path, llm=llm)
    output_path = write_daily_digest(
        vault_root=Path(vault_path),
        date_slug=day.isoformat(),
        content=summary.markdown,
    )
    return JobResult(status="success", detail=str(output_path))


async def run_morning_briefing_job(
    day: date,
    database_path: str | Path,
    vault_path: str | Path,
    channel: NotificationChannel,
    llm=None,
) -> JobResult:
    summary = await _build_daily_summary(day=day, database_path=database_path, llm=llm)
    notification = await build_morning_briefing(
        day=day, digest_markdown=summary.markdown, llm=llm
    )
    notification = _attach_reply_context(notification)
    delivered = channel.send(notification)
    if not delivered:
        return JobResult(
            status="failed",
            detail=f"Failed to send morning briefing for {day.isoformat()}",
        )
    return JobResult(
        status="success", detail=f"Sent morning briefing for {day.isoformat()}"
    )


async def _build_daily_summary(
    day: date,
    database_path: str | Path,
    llm=None,
):
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        events = await repository.list_events_for_day(day.isoformat())

    return await DailySummarizer(llm=llm).summarize(day, events)


def _attach_reply_context(notification: Notification) -> Notification:
    if notification.context_id is None:
        return notification

    return Notification(
        title=notification.title,
        body=append_reply_context(notification.body, notification.context_id),
        category=notification.category,
        context_id=notification.context_id,
        priority=notification.priority,
    )
```

- [ ] **Step 4: Update existing runner/briefing tests for async signatures**

Update `tests/integration/test_daily_digest_job.py` and `tests/integration/test_morning_briefing_job.py` — the `run_daily_digest_job` and `run_morning_briefing_job` signatures now accept an optional `llm` param. Existing tests should pass without changes since `llm` defaults to `None`.

The `build_morning_briefing` call in existing tests needs to become `await build_morning_briefing(...)` since it's now async.

- [ ] **Step 5: Run full test suite**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/jobs/runners.py src/pulse/analysis/briefing.py tests/integration/test_briefing_with_llm.py tests/integration/test_daily_digest_job.py tests/integration/test_morning_briefing_job.py
git commit -m "feat: wire llm into runners and briefing"
```

---

### Task 9: Update Config And Dependencies

**Files:**
- Modify: `src/pulse/app/config.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add LLM config fields to Settings**

Add to `src/pulse/app/config.py`:

```python
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-4-20250514"
```

These are read from `PULSE_ANTHROPIC_API_KEY` and `PULSE_LLM_MODEL` env vars via the existing `get_settings()` mapper in `dependencies.py`.

- [ ] **Step 2: Update pyproject.toml**

Add `anthropic` to the dependencies list:

```toml
dependencies = [
    "fastapi",
    "pydantic",
    "aiosqlite",
    "apscheduler",
    "httpx",
    "anthropic",
]
```

- [ ] **Step 3: Update .env.example**

Add new env vars:

```dotenv
PULSE_GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
PULSE_ANTHROPIC_API_KEY=
PULSE_LLM_MODEL=claude-sonnet-4-20250514
```

- [ ] **Step 4: Reinstall package**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/pip install -e .`

- [ ] **Step 5: Run full test suite**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/pulse/app/config.py .env.example
git commit -m "feat: add anthropic dependency and llm config fields"
```

---

### Task 10: End-To-End Verification

**Files:**
- Modify: `tests/e2e/test_backend_first_mvp.py`

- [ ] **Step 1: Run the full test suite**

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest -v`
Expected: All tests pass. If any fail, fix them.

- [ ] **Step 2: Verify the e2e test still passes**

The existing e2e test should still work since all changes are backward-compatible (LLM defaults to None, OAuth is additive).

Run: `cd /home/rupan/projects/pulse/.worktrees/backend-first-mvp && .venv/bin/python -m pytest tests/e2e/test_backend_first_mvp.py -v`
Expected: PASS

- [ ] **Step 3: Fix any remaining issues and commit**

```bash
git add -A
git commit -m "test: verify google oauth and llm summarization end to end"
```

## Multi-Agent Execution Recommendation

If multiple agents implement this plan, split ownership:

- **Agent 1:** Tasks 1-3 (OAuth storage, auth module, endpoints)
- **Agent 2:** Tasks 4-5 (Google API clients)
- **Agent 3:** Tasks 6-7 (LLM provider, summarizer)
- **Agent 4:** Tasks 8-10 (wiring, config, verification)

Tasks 1-5 and 6-7 can run in parallel. Task 8 depends on both groups. Task 9-10 are final integration.

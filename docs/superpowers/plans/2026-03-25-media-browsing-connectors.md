# Phase 2: Media & Browsing Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Spotify and browser history connectors to Pulse, with a generalized OAuth base class.

**Architecture:** Extract `OAuthManager` base class from existing `GoogleAuthManager`, add `SpotifyAuthManager` subclass using httpx for token exchange, add `SpotifyConnector` with dual-pull strategy (frequent recently-played + infrequent supplementary), add `BrowserHistoryConnector` with copy-then-read SQLite approach and Chrome/Firefox presets, extend scheduler for supplementary jobs, update summarizer/renderer for new event types.

**Tech Stack:** httpx (already a dependency), sqlite3 (stdlib), Python 3.12+

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pulse/connectors/oauth.py` | Create | `OAuthManager` ABC with shared token I/O |
| `src/pulse/connectors/google_auth.py` | Modify | Subclass `OAuthManager`, preserve `get_credentials()` |
| `src/pulse/connectors/spotify_auth.py` | Create | `SpotifyAuthManager` — Spotify OAuth2 flow |
| `src/pulse/connectors/spotify.py` | Create | `SpotifyConnector` + `SupplementaryPullMixin` |
| `src/pulse/connectors/browser.py` | Create | `BrowserHistoryConnector` with presets |
| `src/pulse/connectors/__init__.py` | Modify | Register spotify + browser connectors |
| `src/pulse/app/config.py` | Modify | Add `spotify_client_id`, `spotify_client_secret` |
| `src/pulse/app/cli.py` | Modify | Add `pulse auth spotify` command |
| `src/pulse/jobs/scheduler.py` | Modify | Add `_make_supplementary_job`, supplementary job scheduling |
| `src/pulse/analysis/summarizer.py` | Modify | Route new event types to media/browsing sections |
| `src/pulse/vault/renderer.py` | Modify | Add `browsing_items` parameter |
| `pulse.toml` | Modify | Add spotify + browser connector config |
| `tests/unit/test_oauth_manager.py` | Create | Base class token I/O tests |
| `tests/unit/test_spotify_auth.py` | Create | SpotifyAuthManager tests |
| `tests/unit/test_spotify_connector.py` | Create | SpotifyConnector parsing tests |
| `tests/unit/test_browser_connector.py` | Create | BrowserHistoryConnector tests |
| `tests/unit/test_scheduler.py` | Modify | Supplementary job tests |
| `tests/unit/test_summarizer.py` | Modify | New event type routing tests |
| `tests/integration/test_spotify_pull_cycle.py` | Create | Full Spotify pull cycle with mocked HTTP |
| `tests/integration/test_browser_pull_cycle.py` | Create | Full browser pull with fixture DB |

---

## Task 1: OAuthManager Base Class

**Files:**
- Create: `src/pulse/connectors/oauth.py`
- Create: `tests/unit/test_oauth_manager.py`

- [ ] **Step 1: Write failing tests for OAuthManager**

Create `tests/unit/test_oauth_manager.py`:

```python
import json
from pathlib import Path

from pulse.connectors.oauth import OAuthManager


class FakeOAuthManager(OAuthManager):
    def _get_auth_url(self, scopes, state):
        return f"https://fake.com/auth?state={state}"

    def _exchange_code(self, code):
        return {"access_token": "new_token", "refresh_token": "new_refresh"}

    def _refresh_access_token(self, token_data):
        return {**token_data, "access_token": "refreshed_token"}

    def _is_token_expired(self, token_data):
        return token_data.get("expired", False)


def test_is_authorized_returns_false_when_no_file(tmp_path):
    mgr = FakeOAuthManager(token_path=tmp_path / "missing.json")
    assert mgr.is_authorized() is False


def test_save_and_load_tokens(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok", "refresh_token": "ref"})

    loaded = mgr.load_tokens()
    assert loaded["access_token"] == "tok"
    assert loaded["refresh_token"] == "ref"


def test_is_authorized_returns_true_after_save(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok"})
    assert mgr.is_authorized() is True


def test_load_tokens_returns_none_for_invalid_json(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text("not json")
    mgr = FakeOAuthManager(token_path=token_path)
    assert mgr.load_tokens() is None


def test_get_valid_token_returns_access_token(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "my_token", "expired": False})
    assert mgr.get_valid_token() == "my_token"


def test_get_valid_token_refreshes_when_expired(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "old", "refresh_token": "ref", "expired": True})
    assert mgr.get_valid_token() == "refreshed_token"
    # Verify refreshed token was persisted
    loaded = mgr.load_tokens()
    assert loaded["access_token"] == "refreshed_token"


def test_get_valid_token_raises_when_not_authorized(tmp_path):
    import pytest
    mgr = FakeOAuthManager(token_path=tmp_path / "missing.json")
    with pytest.raises(RuntimeError):
        mgr.get_valid_token()


def test_save_tokens_creates_parent_dirs(tmp_path):
    token_path = tmp_path / "nested" / "dir" / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok"})
    assert token_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_oauth_manager.py -v`
Expected: FAIL — `pulse.connectors.oauth` does not exist

- [ ] **Step 3: Implement OAuthManager**

Create `src/pulse/connectors/oauth.py`:

```python
import json
from abc import ABC, abstractmethod
from pathlib import Path


class OAuthManager(ABC):
    def __init__(self, token_path: Path) -> None:
        self._token_path = token_path

    @abstractmethod
    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        """Build the authorization URL for the provider."""

    @abstractmethod
    def _exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens. Returns token dict."""

    @abstractmethod
    def _refresh_access_token(self, token_data: dict) -> dict:
        """Refresh an expired access token. Returns updated token dict."""

    @abstractmethod
    def _is_token_expired(self, token_data: dict) -> bool:
        """Check if the stored access token has expired."""

    def is_authorized(self) -> bool:
        if not self._token_path.exists():
            return False
        return self.load_tokens() is not None

    def load_tokens(self) -> dict | None:
        try:
            return json.loads(self._token_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save_tokens(self, token_data: dict) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(token_data))

    def get_valid_token(self) -> str:
        token_data = self.load_tokens()
        if token_data is None:
            raise RuntimeError("Not authorized.")
        if self._is_token_expired(token_data):
            token_data = self._refresh_access_token(token_data)
            self.save_tokens(token_data)
        return token_data["access_token"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_oauth_manager.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/oauth.py tests/unit/test_oauth_manager.py
git commit -m "feat: add OAuthManager base class with shared token I/O"
```

---

## Task 2: Migrate GoogleAuthManager to Subclass OAuthManager

**Files:**
- Modify: `src/pulse/connectors/google_auth.py`
- Modify: `tests/unit/test_google_auth_manager.py`

- [ ] **Step 1: Add a test confirming GoogleAuthManager is an OAuthManager**

Add to `tests/unit/test_google_auth_manager.py`:

```python
def test_google_auth_manager_is_oauth_manager_subclass():
    from pulse.connectors.google_auth import GoogleAuthManager
    from pulse.connectors.oauth import OAuthManager
    assert issubclass(GoogleAuthManager, OAuthManager)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_google_auth_manager.py::test_google_auth_manager_is_oauth_manager_subclass -v`
Expected: FAIL — GoogleAuthManager doesn't inherit from OAuthManager

- [ ] **Step 3: Refactor GoogleAuthManager to subclass OAuthManager**

Replace `src/pulse/connectors/google_auth.py`:

```python
import json
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from pulse.connectors.oauth import OAuthManager

logger = logging.getLogger(__name__)

SCOPES_BY_CONNECTOR: dict[str, list[str]] = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "youtube": ["https://www.googleapis.com/auth/youtube.readonly"],
}


class GoogleAuthManager(OAuthManager):
    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def get_required_scopes(self, active_connectors: list[str]) -> list[str]:
        scopes: list[str] = []
        for name in active_connectors:
            scopes.extend(SCOPES_BY_CONNECTOR.get(name, []))
        return scopes

    # --- OAuthManager abstract methods (used by base class, but Google
    #     overrides get_valid_token so these are only called if someone
    #     uses the base class path directly) ---

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        # Not used — Google auth uses InstalledAppFlow.run_local_server
        raise NotImplementedError("Use authorize() for Google OAuth")

    def _exchange_code(self, code: str) -> dict:
        raise NotImplementedError("Use authorize() for Google OAuth")

    def _refresh_access_token(self, token_data: dict) -> dict:
        raise NotImplementedError("Google refresh is handled in get_credentials()")

    def _is_token_expired(self, token_data: dict) -> bool:
        # Not used — Google credential expiry is checked via Credentials object
        return False

    # --- Google-specific API (preserved for backward compatibility) ---

    def is_authorized(self) -> bool:
        if not self._token_path.exists():
            return False
        try:
            creds = self._load_credentials()
            return creds is not None
        except Exception:
            return False

    def get_credentials(self) -> Credentials:
        creds = self._load_credentials()
        if creds is None:
            raise RuntimeError(
                "Not authorized. Run 'pulse auth google' first."
            )
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            self._save_credentials(creds)
        return creds

    def authorize(self, scopes: list[str]) -> None:
        client_config = {
            "installed": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        creds = flow.run_local_server(port=0)
        self._save_credentials(creds)
        logger.info("Google authorization complete. Tokens saved to %s", self._token_path)

    def _load_credentials(self) -> Credentials | None:
        try:
            data = json.loads(self._token_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", self._client_id),
            client_secret=data.get("client_secret", self._client_secret),
        )

    def _save_credentials(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
        self._token_path.write_text(json.dumps(data))
```

- [ ] **Step 4: Run all auth manager tests**

Run: `pytest tests/unit/test_google_auth_manager.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/google_auth.py tests/unit/test_google_auth_manager.py
git commit -m "refactor: migrate GoogleAuthManager to subclass OAuthManager"
```

---

## Task 3: SpotifyAuthManager

**Files:**
- Create: `src/pulse/connectors/spotify_auth.py`
- Create: `tests/unit/test_spotify_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_spotify_auth.py`:

```python
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pulse.connectors.oauth import OAuthManager
from pulse.connectors.spotify_auth import SpotifyAuthManager


def test_spotify_auth_is_oauth_manager_subclass():
    assert issubclass(SpotifyAuthManager, OAuthManager)


def test_get_auth_url_contains_required_params():
    mgr = SpotifyAuthManager(
        client_id="test_id", client_secret="test_secret",
        token_path=Path("/tmp/sp.json"),
    )
    url = mgr._get_auth_url(
        scopes=["user-read-recently-played", "user-library-read"],
        state="abc123",
    )
    assert "https://accounts.spotify.com/authorize" in url
    assert "client_id=test_id" in url
    assert "state=abc123" in url
    assert "user-read-recently-played" in url
    assert "redirect_uri=" in url


def test_is_token_expired_returns_false_for_fresh_token():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok", "expires_at": time.time() + 3600}
    assert mgr._is_token_expired(token_data) is False


def test_is_token_expired_returns_true_for_expired_token():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok", "expires_at": time.time() - 100}
    assert mgr._is_token_expired(token_data) is True


def test_is_token_expired_returns_true_when_no_expires_at():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok"}
    assert mgr._is_token_expired(token_data) is True


def test_exchange_code_calls_token_endpoint(tmp_path):
    import httpx

    mgr = SpotifyAuthManager(
        client_id="cid", client_secret="csec",
        token_path=tmp_path / "tokens.json",
    )

    mock_response = httpx.Response(
        200,
        json={
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
        request=httpx.Request("POST", "https://accounts.spotify.com/api/token"),
    )

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = mgr._exchange_code("auth_code_123")

    assert result["access_token"] == "new_access"
    assert result["refresh_token"] == "new_refresh"
    assert "expires_at" in result
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["data"]["code"] == "auth_code_123"
    assert call_kwargs.kwargs["data"]["grant_type"] == "authorization_code"


def test_refresh_access_token_calls_token_endpoint(tmp_path):
    import httpx

    mgr = SpotifyAuthManager(
        client_id="cid", client_secret="csec",
        token_path=tmp_path / "tokens.json",
    )

    mock_response = httpx.Response(
        200,
        json={
            "access_token": "refreshed_access",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
        request=httpx.Request("POST", "https://accounts.spotify.com/api/token"),
    )

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = mgr._refresh_access_token({
            "access_token": "old",
            "refresh_token": "my_refresh",
        })

    assert result["access_token"] == "refreshed_access"
    assert result["refresh_token"] == "my_refresh"  # preserved from original
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["data"]["grant_type"] == "refresh_token"
    assert call_kwargs.kwargs["data"]["refresh_token"] == "my_refresh"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_spotify_auth.py -v`
Expected: FAIL — `pulse.connectors.spotify_auth` does not exist

- [ ] **Step 3: Implement SpotifyAuthManager**

Create `src/pulse/connectors/spotify_auth.py`:

```python
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

SPOTIFY_SCOPES = [
    "user-read-recently-played",
    "user-library-read",
    "user-top-read",
]

REDIRECT_URI = "http://localhost:8888/callback"


class SpotifyAuthManager(OAuthManager):
    AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        data = response.json()
        data["expires_at"] = time.time() + data.get("expires_in", 3600)
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        response = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
            },
            auth=(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        refreshed = response.json()
        refreshed["expires_at"] = time.time() + refreshed.get("expires_in", 3600)
        # Spotify may not return a new refresh_token — preserve the old one
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = token_data["refresh_token"]
        return refreshed

    def _is_token_expired(self, token_data: dict) -> bool:
        expires_at = token_data.get("expires_at")
        if expires_at is None:
            return True
        # Refresh 2 minutes early to avoid edge cases
        return time.time() > (expires_at - 120)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_spotify_auth.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/spotify_auth.py tests/unit/test_spotify_auth.py
git commit -m "feat: add SpotifyAuthManager with OAuth2 token exchange and refresh"
```

---

## Task 4: SpotifyConnector

**Files:**
- Create: `src/pulse/connectors/spotify.py`
- Create: `tests/unit/test_spotify_connector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_spotify_connector.py`:

```python
import asyncio
from datetime import UTC, datetime, timedelta

from pulse.connectors.spotify import SpotifyConnector


def test_spotify_connector_source_name():
    connector = SpotifyConnector()
    assert connector.get_source_name() == "spotify"


def test_spotify_connector_default_interval():
    connector = SpotifyConnector()
    assert connector.get_default_interval() == timedelta(minutes=30)


def test_spotify_connector_validate_config_false_without_auth():
    connector = SpotifyConnector()
    assert asyncio.run(connector.validate_config()) is False


def test_spotify_connector_parses_recently_played():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        async def get(self, url, **kwargs):
            class Resp:
                def raise_for_status(self): pass
                def json(self):
                    return {
                        "items": [{
                            "track": {
                                "id": "track-1",
                                "name": "Cool Song",
                                "artists": [{"name": "Artist A"}],
                                "album": {"name": "Album X"},
                                "duration_ms": 240000,
                            },
                            "played_at": "2026-03-25T10:30:00Z",
                        }],
                        "cursors": {"after": "1711360200000"},
                    }
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector.pull())

    assert len(events) == 1
    e = events[0]
    assert e.id == "spotify:play:track-1:2026-03-25T10:30:00Z"
    assert e.source == "spotify"
    assert e.event_type == "media.spotify.play"
    assert e.data["track_name"] == "Cool Song"
    assert e.data["artist"] == "Artist A"
    assert e.data["album"] == "Album X"
    assert e.data["duration_ms"] == 240000
    assert e.data["played_at"] == "2026-03-25T10:30:00Z"


def test_spotify_connector_parses_saved_tracks():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        async def get(self, url, **kwargs):
            class Resp:
                def raise_for_status(self): pass
                def json(self):
                    return {
                        "items": [{
                            "added_at": "2026-03-20T08:00:00Z",
                            "track": {
                                "id": "saved-1",
                                "name": "Saved Song",
                                "artists": [{"name": "Artist B"}],
                                "album": {"name": "Album Y"},
                            },
                        }],
                        "next": None,
                    }
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector._pull_supplementary())

    saved = [e for e in events if e.event_type == "media.spotify.save"]
    assert len(saved) == 1
    assert saved[0].data["track_name"] == "Saved Song"
    assert saved[0].id == "spotify:save:saved-1"


def test_spotify_connector_parses_top_tracks():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        call_count = 0
        async def get(self, url, **kwargs):
            self.call_count += 1
            class Resp:
                def raise_for_status(self): pass
                def json(resp_self):
                    if "top/tracks" in url:
                        return {
                            "items": [{
                                "id": "top-1",
                                "name": "Top Song",
                                "artists": [{"name": "Artist C"}],
                            }],
                        }
                    elif "top/artists" in url:
                        return {
                            "items": [{
                                "id": "topart-1",
                                "name": "Top Artist",
                                "genres": ["pop", "rock"],
                            }],
                        }
                    # saved tracks returns empty
                    return {"items": [], "next": None}
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector._pull_supplementary())

    top_tracks = [e for e in events if e.event_type == "media.spotify.top_track"]
    top_artists = [e for e in events if e.event_type == "media.spotify.top_artist"]
    assert len(top_tracks) >= 1
    assert top_tracks[0].data["track_name"] == "Top Song"
    assert top_tracks[0].data["rank"] == 1
    assert len(top_artists) >= 1
    assert top_artists[0].data["artist_name"] == "Top Artist"
    assert top_artists[0].data["genres"] == ["pop", "rock"]


def test_spotify_connector_has_supplementary_jobs():
    from pulse.app.config import ConnectorConfig
    connector = SpotifyConnector()
    jobs = connector.get_supplementary_jobs(ConnectorConfig(supplementary_interval="6h"))
    assert len(jobs) == 1
    suffix, interval, _ = jobs[0]
    assert suffix == "supplementary"
    assert interval == timedelta(hours=6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_spotify_connector.py -v`
Expected: FAIL — `pulse.connectors.spotify` does not exist

- [ ] **Step 3: Implement SpotifyConnector**

Create `src/pulse/connectors/spotify.py`:

```python
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from pulse.app.config import ConnectorConfig
from pulse.domain.connectors import Connector
from pulse.domain.events import Event
from pulse.connectors.spotify_auth import SpotifyAuthManager

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SupplementaryPullMixin:
    def get_supplementary_jobs(
        self, config: ConnectorConfig
    ) -> list[tuple[str, timedelta, Callable]]:
        return []


class SpotifyConnector(Connector, SupplementaryPullMixin):
    def __init__(
        self,
        auth_manager: SpotifyAuthManager | None = None,
        http_client: object | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._http = http_client

    def get_source_name(self) -> str:
        return "spotify"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        """Pull recently played tracks."""
        client = self._get_http_client()
        owns_client = self._http is None
        try:
            params: dict = {"limit": 50}
            if since is not None:
                # Spotify expects Unix timestamp in milliseconds
                params["after"] = str(int(since.timestamp() * 1000))

            resp = await client.get(
                f"{SPOTIFY_API_BASE}/me/player/recently-played",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            events = []
            for item in data.get("items", []):
                track = item["track"]
                played_at = item["played_at"]
                events.append(Event(
                    id=f"spotify:play:{track['id']}:{played_at}",
                    timestamp=datetime.fromisoformat(played_at.replace("Z", "+00:00")),
                    source="spotify",
                    event_type="media.spotify.play",
                    data={
                        "track_name": track["name"],
                        "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                        "album": track.get("album", {}).get("name", ""),
                        "played_at": played_at,
                        "duration_ms": track.get("duration_ms", 0),
                    },
                ))
            return events
        finally:
            if owns_client:
                await client.aclose()

    async def _pull_supplementary(self) -> list[Event]:
        """Pull saved tracks, top tracks, top artists. Stateless."""
        events: list[Event] = []
        client = self._get_http_client()
        owns_client = self._http is None
        headers = self._auth_headers()
        now = datetime.now(UTC)
        try:
            # Saved tracks (first page only — new additions)
            resp = await client.get(
                f"{SPOTIFY_API_BASE}/me/tracks",
                params={"limit": 50},
                headers=headers,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                track = item["track"]
                events.append(Event(
                    id=f"spotify:save:{track['id']}",
                    timestamp=datetime.fromisoformat(
                        item["added_at"].replace("Z", "+00:00")
                    ),
                    source="spotify",
                    event_type="media.spotify.save",
                    data={
                        "track_name": track["name"],
                        "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                        "album": track.get("album", {}).get("name", ""),
                        "saved_at": item["added_at"],
                    },
                ))

            # Top tracks (all three time ranges per spec)
            for time_range in ("short_term", "medium_term", "long_term"):
                resp = await client.get(
                    f"{SPOTIFY_API_BASE}/me/top/tracks",
                    params={"limit": 20, "time_range": time_range},
                    headers=headers,
                )
                resp.raise_for_status()
                for rank, item in enumerate(resp.json().get("items", []), 1):
                    events.append(Event(
                        id=f"spotify:top_track:{item['id']}:{time_range}",
                        timestamp=now,
                        source="spotify",
                        event_type="media.spotify.top_track",
                        data={
                            "track_name": item["name"],
                            "artist": item["artists"][0]["name"] if item["artists"] else "Unknown",
                            "rank": rank,
                            "time_range": time_range,
                            "pulled_at": now.isoformat(),
                        },
                    ))

            # Top artists (all three time ranges per spec)
            for time_range in ("short_term", "medium_term", "long_term"):
                resp = await client.get(
                    f"{SPOTIFY_API_BASE}/me/top/artists",
                    params={"limit": 20, "time_range": time_range},
                    headers=headers,
                )
                resp.raise_for_status()
                for rank, item in enumerate(resp.json().get("items", []), 1):
                    events.append(Event(
                        id=f"spotify:top_artist:{item['id']}:{time_range}",
                        timestamp=now,
                        source="spotify",
                        event_type="media.spotify.top_artist",
                        data={
                            "artist_name": item["name"],
                            "genres": item.get("genres", []),
                            "rank": rank,
                            "time_range": time_range,
                            "pulled_at": now.isoformat(),
                        },
                    ))

            return events
        finally:
            if owns_client:
                await client.aclose()

    def get_supplementary_jobs(
        self, config: ConnectorConfig
    ) -> list[tuple[str, timedelta, Callable]]:
        from pulse.jobs.scheduler import parse_interval
        interval_str = getattr(config, "supplementary_interval", "6h")
        interval = parse_interval(interval_str)
        return [("supplementary", interval, self._pull_supplementary)]

    def _auth_headers(self) -> dict[str, str]:
        token = self._auth_manager.get_valid_token()
        return {"Authorization": f"Bearer {token}"}

    def _get_http_client(self):
        if self._http is not None:
            return self._http
        return httpx.AsyncClient()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_spotify_connector.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/spotify.py tests/unit/test_spotify_connector.py
git commit -m "feat: add SpotifyConnector with recently-played and supplementary pulls"
```

---

## Task 5: BrowserHistoryConnector

**Files:**
- Create: `src/pulse/connectors/browser.py`
- Create: `tests/unit/test_browser_connector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_browser_connector.py`:

```python
import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulse.connectors.browser import (
    BrowserHistoryConnector,
    BROWSER_PRESETS,
    normalize_timestamp,
)


def test_browser_connector_source_name():
    connector = BrowserHistoryConnector()
    assert connector.get_source_name() == "browser"


def test_browser_connector_default_interval():
    connector = BrowserHistoryConnector()
    assert connector.get_default_interval() == timedelta(minutes=15)


def test_browser_connector_validate_config_false_when_db_missing(tmp_path):
    connector = BrowserHistoryConnector(db_path=str(tmp_path / "nonexistent.db"))
    assert asyncio.run(connector.validate_config()) is False


def test_browser_connector_validate_config_true_when_db_exists(tmp_path):
    db_path = tmp_path / "History"
    db_path.write_text("")  # empty file is enough for validate_config
    connector = BrowserHistoryConnector(db_path=str(db_path))
    assert asyncio.run(connector.validate_config()) is True


def test_normalize_timestamp_chrome():
    preset = BROWSER_PRESETS["chrome"]
    # Chrome timestamp for 2026-03-25 12:00:00 UTC
    # Unix timestamp = 1774699200
    # Chrome raw = (1774699200 + 11644473600) * 1000000 = 13419172800000000
    raw = 13419172800000000
    result = normalize_timestamp(raw, preset["epoch_offset"], preset["timestamp_divisor"])
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 25
    assert result.hour == 12


def test_normalize_timestamp_firefox():
    preset = BROWSER_PRESETS["firefox"]
    # Firefox timestamp for 2026-03-25 12:00:00 UTC
    # Unix timestamp = 1774699200
    # Firefox raw = 1774699200 * 1000000 = 1774699200000000
    raw = 1774699200000000
    result = normalize_timestamp(raw, preset["epoch_offset"], preset["timestamp_divisor"])
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 25
    assert result.hour == 12


def _create_chrome_fixture(db_path: Path) -> None:
    """Create a minimal Chrome-style History SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    conn.execute(
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)"
    )
    # 2026-03-25 10:00:00 UTC as Chrome timestamp
    chrome_ts = (1774692000 + 11644473600) * 1000000
    conn.execute("INSERT INTO urls VALUES (1, 'https://example.com', 'Example')")
    conn.execute(f"INSERT INTO visits VALUES (1, 1, {chrome_ts})")
    # Older visit
    chrome_ts_old = (1774600000 + 11644473600) * 1000000
    conn.execute("INSERT INTO urls VALUES (2, 'https://old.com', 'Old Page')")
    conn.execute(f"INSERT INTO visits VALUES (2, 2, {chrome_ts_old})")
    conn.commit()
    conn.close()


def test_browser_connector_pulls_from_chrome_fixture(tmp_path):
    db_path = tmp_path / "History"
    _create_chrome_fixture(db_path)

    connector = BrowserHistoryConnector(browser="chrome", db_path=str(db_path))
    events = asyncio.run(connector.pull())

    assert len(events) == 2
    urls = {e.data["url"] for e in events}
    assert "https://example.com" in urls
    assert "https://old.com" in urls
    assert all(e.event_type == "browsing.visit" for e in events)
    assert all(e.source == "browser" for e in events)


def test_browser_connector_pulls_since_cursor(tmp_path):
    db_path = tmp_path / "History"
    _create_chrome_fixture(db_path)

    connector = BrowserHistoryConnector(browser="chrome", db_path=str(db_path))
    # Set since to 2026-03-25 09:00:00 — should only get the 10:00 visit
    since = datetime(2026, 3, 25, 9, 0, 0, tzinfo=UTC)
    events = asyncio.run(connector.pull(since=since))

    assert len(events) == 1
    assert events[0].data["url"] == "https://example.com"


def test_browser_presets_have_required_keys():
    for name, preset in BROWSER_PRESETS.items():
        assert "url_table" in preset, f"{name} missing url_table"
        assert "visit_table" in preset, f"{name} missing visit_table"
        assert "epoch_offset" in preset, f"{name} missing epoch_offset"
        assert "timestamp_divisor" in preset, f"{name} missing timestamp_divisor"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_browser_connector.py -v`
Expected: FAIL — `pulse.connectors.browser` does not exist

- [ ] **Step 3: Implement BrowserHistoryConnector**

Create `src/pulse/connectors/browser.py`:

```python
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

BROWSER_PRESETS: dict[str, dict] = {
    "chrome": {
        "linux": "~/.config/google-chrome/Default/History",
        "darwin": "~/Library/Application Support/Google/Chrome/Default/History",
        "win32": "~/AppData/Local/Google/Chrome/User Data/Default/History",
        "url_table": "urls",
        "visit_table": "visits",
        "url_column": "url",
        "title_column": "title",
        "visit_time_column": "visit_time",
        "url_id_column": "id",
        "visit_url_column": "url",
        "epoch_offset": 11_644_473_600,
        "timestamp_divisor": 1_000_000,
    },
    "firefox": {
        "linux": "~/.mozilla/firefox/*.default*/places.sqlite",
        "darwin": "~/Library/Application Support/Firefox/Profiles/*.default*/places.sqlite",
        "win32": "~/AppData/Roaming/Mozilla/Firefox/Profiles/*.default*/places.sqlite",
        "url_table": "moz_places",
        "visit_table": "moz_historyvisits",
        "url_column": "url",
        "title_column": "title",
        "visit_time_column": "visit_date",
        "url_id_column": "id",
        "visit_url_column": "place_id",
        "epoch_offset": 0,
        "timestamp_divisor": 1_000_000,
    },
}


def normalize_timestamp(
    raw_value: int, epoch_offset: int, timestamp_divisor: int
) -> datetime:
    """Convert browser-specific timestamp to UTC datetime.

    Formula: unix_ts = (raw_value / timestamp_divisor) - epoch_offset
    """
    unix_ts = (raw_value / timestamp_divisor) - epoch_offset
    return datetime.fromtimestamp(unix_ts, tz=UTC)


class BrowserHistoryConnector(Connector):
    def __init__(
        self, browser: str = "chrome", db_path: str | None = None
    ) -> None:
        self._browser = browser
        self._db_path = db_path

    def get_source_name(self) -> str:
        return "browser"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        path = self._resolve_db_path()
        return path is not None and path.exists()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        db_path = self._resolve_db_path()
        if db_path is None or not db_path.exists():
            return []

        preset = BROWSER_PRESETS.get(self._browser, BROWSER_PRESETS["chrome"])
        fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            shutil.copy2(db_path, tmp_path)
            return self._query_visits(tmp_path, preset, since)
        finally:
            os.unlink(tmp_path)

    def _query_visits(
        self, db_path: str, preset: dict, since: datetime | None
    ) -> list[Event]:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            url_table = preset["url_table"]
            visit_table = preset["visit_table"]
            time_col = preset["visit_time_column"]
            url_id_col = preset["url_id_column"]
            visit_url_col = preset["visit_url_column"]
            url_col = preset["url_column"]
            title_col = preset["title_column"]

            query = (
                f"SELECT u.{url_col}, u.{title_col}, v.{time_col} "
                f"FROM {visit_table} v "
                f"JOIN {url_table} u ON u.{url_id_col} = v.{visit_url_col} "
            )
            params: list = []

            if since is not None:
                # Convert since datetime back to browser-specific timestamp
                raw_since = int(
                    (since.timestamp() + preset["epoch_offset"])
                    * preset["timestamp_divisor"]
                )
                query += f"WHERE v.{time_col} > ? "
                params.append(raw_since)

            query += f"ORDER BY v.{time_col}"

            rows = conn.execute(query, params).fetchall()

            events = []
            for url, title, raw_time in rows:
                visit_time = normalize_timestamp(
                    raw_time, preset["epoch_offset"], preset["timestamp_divisor"]
                )
                events.append(Event(
                    id=f"browser:{self._browser}:{raw_time}:{hashlib.md5(url.encode()).hexdigest()[:8]}",
                    timestamp=visit_time,
                    source="browser",
                    event_type="browsing.visit",
                    data={
                        "url": url,
                        "title": title or "",
                        "visit_time": visit_time.isoformat(),
                        "browser": self._browser,
                    },
                ))
            return events
        finally:
            conn.close()

    def _resolve_db_path(self) -> Path | None:
        if self._db_path:
            return Path(self._db_path).expanduser()
        preset = BROWSER_PRESETS.get(self._browser)
        if not preset:
            return None
        platform_path = preset.get(sys.platform)
        if not platform_path:
            return None
        expanded = Path(platform_path).expanduser()
        if "*" in platform_path:
            matches = list(Path("/").glob(str(expanded).lstrip("/")))
            if not matches:
                return None
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]
        return expanded
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_browser_connector.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/browser.py tests/unit/test_browser_connector.py
git commit -m "feat: add BrowserHistoryConnector with Chrome/Firefox presets"
```

---

## Task 6: Config, Registration, and CLI Updates

**Files:**
- Modify: `src/pulse/app/config.py`
- Modify: `src/pulse/connectors/__init__.py`
- Modify: `src/pulse/app/cli.py`
- Modify: `pulse.toml`

- [ ] **Step 1: Update PulseConfig with Spotify fields**

Add to `src/pulse/app/config.py` after `google_client_secret`:

```python
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
```

- [ ] **Step 2: Update register_all to include Spotify and browser connectors**

Replace `src/pulse/connectors/__init__.py`:

```python
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector
    from pulse.connectors.youtube import YouTubeConnector
    from pulse.connectors.spotify import SpotifyConnector
    from pulse.connectors.spotify_auth import SpotifyAuthManager
    from pulse.connectors.browser import BrowserHistoryConnector

    # Build shared Google auth manager if credentials are configured
    auth_manager: GoogleAuthManager | None = None
    if config.google_client_id and config.google_client_secret:
        token_path = Path(config.database_path).parent / "google_tokens.json"
        auth_manager = GoogleAuthManager(
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            token_path=token_path,
        )

    registry.register_pull("gmail", lambda: GmailConnector(auth_manager=auth_manager))
    registry.register_pull("calendar", lambda: GoogleCalendarConnector(auth_manager=auth_manager))
    registry.register_pull("youtube", lambda: YouTubeConnector(auth_manager=auth_manager))

    # Spotify
    spotify_auth: SpotifyAuthManager | None = None
    if config.spotify_client_id and config.spotify_client_secret:
        token_path = Path(config.database_path).parent / "spotify_tokens.json"
        spotify_auth = SpotifyAuthManager(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            token_path=token_path,
        )
    registry.register_pull("spotify", lambda: SpotifyConnector(auth_manager=spotify_auth))

    # Browser history
    browser_config = config.connectors.get("browser")
    browser_type = getattr(browser_config, "browser", "chrome") if browser_config else "chrome"
    db_path = getattr(browser_config, "db_path", None) if browser_config else None
    registry.register_pull("browser", lambda: BrowserHistoryConnector(
        browser=browser_type, db_path=db_path,
    ))
```

- [ ] **Step 3: Add `pulse auth spotify` to CLI**

Replace `src/pulse/app/cli.py`:

```python
import argparse
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import GoogleAuthManager, SCOPES_BY_CONNECTOR
from pulse.connectors.spotify_auth import SpotifyAuthManager, SPOTIFY_SCOPES, REDIRECT_URI


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse CLI")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="provider")
    auth_subparsers.add_parser("google", help="Authorize Google services")
    auth_subparsers.add_parser("spotify", help="Authorize Spotify")

    args = parser.parse_args()

    if args.command == "auth" and args.provider == "google":
        _auth_google()
    elif args.command == "auth" and args.provider == "spotify":
        _auth_spotify()
    else:
        parser.print_help()
        sys.exit(1)


def _auth_google() -> None:
    config = load_config()

    if not config.google_client_id or not config.google_client_secret:
        print("Error: PULSE_GOOGLE_CLIENT_ID and PULSE_GOOGLE_CLIENT_SECRET must be set.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "google_tokens.json"
    auth_manager = GoogleAuthManager(
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        token_path=token_path,
    )

    google_connectors = [
        name for name in config.connectors
        if name in SCOPES_BY_CONNECTOR and config.connectors[name].enabled
    ]

    if not google_connectors:
        print("No Google connectors enabled in pulse.toml. Enable gmail, calendar, or youtube.")
        sys.exit(1)

    scopes = auth_manager.get_required_scopes(google_connectors)
    print(f"Authorizing for: {', '.join(google_connectors)}")
    print(f"Scopes: {', '.join(scopes)}")

    auth_manager.authorize(scopes)
    print("Authorization complete!")


def _auth_spotify() -> None:
    config = load_config()

    if not config.spotify_client_id or not config.spotify_client_secret:
        print("Error: PULSE_SPOTIFY_CLIENT_ID and PULSE_SPOTIFY_CLIENT_SECRET must be set.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "spotify_tokens.json"
    auth_manager = SpotifyAuthManager(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        token_path=token_path,
    )

    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(SPOTIFY_SCOPES, state)

    print(f"Opening browser for Spotify authorization...")
    print(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    # Start temporary HTTP server to receive callback
    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            returned_state = query.get("state", [None])[0]
            code = query.get("code", [None])[0]

            if returned_state != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch — possible CSRF attack.")
                return

            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorization successful! You can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No authorization code received.")

        def log_message(self, format, *args):
            pass  # Suppress request logging

    server = HTTPServer(("localhost", 8888), CallbackHandler)
    server.handle_request()  # Handle single callback request

    if not received_code:
        print("Error: No authorization code received.")
        sys.exit(1)

    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    print("Spotify authorization complete!")
```

- [ ] **Step 4: Update pulse.toml**

Add to `pulse.toml`:

```toml

[connectors.spotify]
enabled = true
poll_interval = "30m"
supplementary_interval = "6h"

[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"
```

- [ ] **Step 5: Verify imports**

Run: `python -c "from pulse.connectors import register_all; from pulse.connectors.registry import ConnectorRegistry; from pulse.app.config import PulseConfig; r = ConnectorRegistry(); register_all(r, PulseConfig()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/app/config.py src/pulse/connectors/__init__.py src/pulse/app/cli.py pulse.toml
git commit -m "feat: wire Spotify and browser connectors into config, registration, and CLI"
```

---

## Task 7: Scheduler Supplementary Job Support

**Files:**
- Modify: `src/pulse/jobs/scheduler.py`
- Modify: `tests/unit/test_scheduler.py`

- [ ] **Step 1: Write failing tests for supplementary jobs**

Add to `tests/unit/test_scheduler.py`:

```python
from pulse.connectors.spotify import SupplementaryPullMixin


class FakeSupplementaryConnector(Connector, SupplementaryPullMixin):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "supplementary_fake"
    def get_default_interval(self):
        return timedelta(minutes=30)
    def get_supplementary_jobs(self, config):
        return [("extra", timedelta(hours=2), self._extra_pull)]
    async def _extra_pull(self):
        return []


def test_build_scheduler_creates_supplementary_jobs():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    registry.register_pull("supplementary_fake", lambda: FakeSupplementaryConnector())
    config = PulseConfig(connectors={
        "supplementary_fake": ConnectorConfig(enabled=True, poll_interval="30m"),
    })
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "pull_supplementary_fake" in jobs
    assert "pull_supplementary_fake_extra" in jobs
    supp_job = jobs["pull_supplementary_fake_extra"]
    assert isinstance(supp_job.trigger, IntervalTrigger)
    assert supp_job.trigger.interval.total_seconds() == 7200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scheduler.py::test_build_scheduler_creates_supplementary_jobs -v`
Expected: FAIL — no supplementary job created

- [ ] **Step 3: Add supplementary job support to scheduler**

In `src/pulse/jobs/scheduler.py`, add after the pull connector job creation loop (after line 46):

```python
            # Supplementary jobs (if connector supports them)
            if hasattr(connector, "get_supplementary_jobs"):
                for suffix, supp_interval, job_fn in connector.get_supplementary_jobs(cc):
                    scheduler.add_job(
                        _make_supplementary_job(job_fn, config),
                        trigger=IntervalTrigger(seconds=int(supp_interval.total_seconds())),
                        id=f"pull_{connector.get_source_name()}_{suffix}",
                    )
```

And add the `_make_supplementary_job` function after `_make_pull_job`:

```python
def _make_supplementary_job(job_fn, config):
    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        events = await job_fn()
        if events:
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                await event_repo.upsert_events(events)

    return job
```

- [ ] **Step 4: Run scheduler tests**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/jobs/scheduler.py tests/unit/test_scheduler.py
git commit -m "feat: add supplementary job support to scheduler for dual-interval connectors"
```

---

## Task 8: Summarizer and Renderer Updates

**Files:**
- Modify: `src/pulse/vault/renderer.py`
- Modify: `src/pulse/analysis/summarizer.py`
- Modify: `tests/unit/test_summarizer.py`

- [ ] **Step 1: Add browsing_items parameter to renderer**

In `src/pulse/vault/renderer.py`, add `browsing_items: list[str] = []` parameter and a "Browsing" section:

Replace `src/pulse/vault/renderer.py`:

```python
def render_daily_digest(
    *,
    date_label: str,
    timeline_items: list[str],
    email_highlights: list[str],
    spending_items: list[str],
    health_items: list[str],
    media_items: list[str],
    browsing_items: list[str] | None = None,
    tags: list[str],
) -> str:
    if browsing_items is None:
        browsing_items = []
    sections = [
        ("Timeline", timeline_items, "No timeline entries."),
        ("Email Highlights", email_highlights, "No email highlights."),
        ("Spending", spending_items, "No spending recorded."),
        ("Health", health_items, "No health updates."),
        ("Media", media_items, "No media activity."),
        ("Browsing", browsing_items, "No browsing activity."),
        ("Tags", tags, "No tags."),
    ]
    lines = [f"# {date_label}", ""]

    for index, (title, items, fallback) in enumerate(sections):
        lines.append(f"## {title}")
        lines.extend(_render_items(items, fallback))
        if index < len(sections) - 1:
            lines.append("")

    return "\n".join(lines)


def _render_items(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [f"- {fallback}"]

    return [f"- {item}" for item in items]
```

- [ ] **Step 2: Update summarizer to route new event types**

Replace `src/pulse/analysis/summarizer.py`:

```python
from dataclasses import dataclass
from datetime import date

from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def summarize(self, day: date, events: list[Event]) -> DailySummary:
        timeline_items: list[str] = []
        email_highlights: list[str] = []
        media_items: list[str] = []
        browsing_items: list[str] = []

        for event in sorted(events, key=lambda item: item.timestamp):
            if event.event_type == "calendar.event":
                timeline_items.append(_event_text(event, "title"))
            elif event.event_type == "email.received":
                email_highlights.append(_event_text(event, "subject"))
            elif event.event_type == "media.spotify.play":
                track = event.data.get("track_name", "Unknown")
                artist = event.data.get("artist", "Unknown")
                media_items.append(f"Listened to {track} by {artist}")
            elif event.event_type in (
                "media.youtube.activity",
                "media.youtube.like",
            ):
                media_items.append(_event_text(event, "title"))
            elif event.event_type == "browsing.visit":
                title = event.data.get("title") or event.data.get("url", "")
                browsing_items.append(title)
            else:
                timeline_items.append(_event_text(event))

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=timeline_items,
            email_highlights=email_highlights,
            spending_items=[],
            health_items=[],
            media_items=media_items,
            browsing_items=browsing_items,
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

- [ ] **Step 3: Update existing summarizer test for new Browsing section**

The existing `test_daily_summarizer_renders_markdown_digest_from_events` asserts exact markdown output. Adding the Browsing section to the renderer changes that output. Update the expected string in `tests/unit/test_summarizer.py`:

```python
    expected = "\n".join(
        [
            "# 2026-03-22",
            "",
            "## Timeline",
            "- Team sync",
            "- message.created",
            "",
            "## Email Highlights",
            "- Project update",
            "",
            "## Spending",
            "- No spending recorded.",
            "",
            "## Health",
            "- No health updates.",
            "",
            "## Media",
            "- No media activity.",
            "",
            "## Browsing",
            "- No browsing activity.",
            "",
            "## Tags",
            "- No tags.",
        ]
    )
```

- [ ] **Step 4: Add tests for new event type routing**

Add to `tests/unit/test_summarizer.py`:

```python
def test_summarizer_routes_spotify_play_to_media_section():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event
    from datetime import UTC, date, datetime

    events = [Event(
        id="sp:1", timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        source="spotify", event_type="media.spotify.play",
        data={"track_name": "Cool Song", "artist": "Artist A"},
    )]
    result = DailySummarizer().summarize(date(2026, 3, 25), events)
    assert "Listened to Cool Song by Artist A" in result.markdown


def test_summarizer_routes_browsing_visit_to_browsing_section():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event
    from datetime import UTC, date, datetime

    events = [Event(
        id="br:1", timestamp=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        source="browser", event_type="browsing.visit",
        data={"url": "https://example.com", "title": "Example Site"},
    )]
    result = DailySummarizer().summarize(date(2026, 3, 25), events)
    assert "Example Site" in result.markdown
    assert "## Browsing" in result.markdown
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_summarizer.py tests/unit/test_vault_renderer.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/vault/renderer.py src/pulse/analysis/summarizer.py tests/unit/test_summarizer.py
git commit -m "feat: route Spotify and browsing events to digest media/browsing sections"
```

---

## Task 9: Integration Test — Spotify Pull Cycle

**Files:**
- Create: `tests/integration/test_spotify_pull_cycle.py`

- [ ] **Step 1: Write Spotify integration test**

Create `tests/integration/test_spotify_pull_cycle.py`:

```python
import asyncio
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.spotify import SpotifyConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


class FakeAuth:
    def is_authorized(self):
        return True
    def get_valid_token(self):
        return "fake_token"


class FakeHTTPClient:
    async def get(self, url, **kwargs):
        class Resp:
            def raise_for_status(self): pass
            def json(resp_self):
                if "recently-played" in url:
                    return {
                        "items": [{
                            "track": {
                                "id": "track-1",
                                "name": "Test Song",
                                "artists": [{"name": "Test Artist"}],
                                "album": {"name": "Test Album"},
                                "duration_ms": 200000,
                            },
                            "played_at": "2026-03-25T10:30:00Z",
                        }],
                        "cursors": {"after": "1711360200000"},
                    }
                return {"items": [], "next": None}
        return Resp()

    async def aclose(self):
        pass


def test_spotify_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"

        connector = SpotifyConnector(
            auth_manager=FakeAuth(),
            http_client=FakeHTTPClient(),
        )
        registry = ConnectorRegistry()
        registry.register_pull("spotify", lambda: connector)

        config = PulseConfig(
            database_path=str(db_path),
            connectors={"spotify": ConnectorConfig(enabled=True, poll_interval="30m")},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]
        assert connector.get_source_name() == "spotify"

        events = await connector.pull()
        assert len(events) == 1
        assert events[0].event_type == "media.spotify.play"
        assert events[0].data["track_name"] == "Test Song"

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(events)

            sync_repo = SyncStateRepository(db)
            await sync_repo.save("spotify", events[-1].timestamp.isoformat())
            state = await sync_repo.load("spotify")
            assert state is not None

            stored = await event_repo.list_events_for_day("2026-03-25")
            assert len(stored) == 1
            assert stored[0].id == "spotify:play:track-1:2026-03-25T10:30:00Z"

    asyncio.run(exercise())
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/integration/test_spotify_pull_cycle.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_spotify_pull_cycle.py
git commit -m "test: add Spotify pull cycle integration test"
```

---

## Task 10: Integration Test — Browser Pull Cycle

**Files:**
- Create: `tests/integration/test_browser_pull_cycle.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_browser_pull_cycle.py`:

```python
import asyncio
import sqlite3
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.browser import BrowserHistoryConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def _create_chrome_fixture(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    conn.execute(
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)"
    )
    chrome_ts = (1774692000 + 11644473600) * 1000000
    conn.execute("INSERT INTO urls VALUES (1, 'https://example.com', 'Example')")
    conn.execute(f"INSERT INTO visits VALUES (1, 1, {chrome_ts})")
    conn.commit()
    conn.close()


def test_browser_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        # Create fixture
        browser_db = tmp_path / "History"
        _create_chrome_fixture(browser_db)

        db_path = tmp_path / "pulse.db"
        registry = ConnectorRegistry()
        registry.register_pull("browser", lambda: BrowserHistoryConnector(
            browser="chrome", db_path=str(browser_db),
        ))
        config = PulseConfig(
            database_path=str(db_path),
            connectors={"browser": ConnectorConfig(enabled=True)},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            events = await connector.pull()
            assert len(events) == 1
            await event_repo.upsert_events(events)
            latest = max(e.timestamp for e in events)
            await sync_state.save("browser", latest.isoformat())

            stored = await event_repo.list_events_for_day("2026-03-25")
            assert len(stored) == 1
            assert stored[0].data["url"] == "https://example.com"

            cursor = await sync_state.load("browser")
            assert cursor is not None

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_browser_pull_cycle.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_browser_pull_cycle.py
git commit -m "test: add integration test for browser history pull cycle"
```

---

## Task 11: Final Verification

- [ ] **Step 1: Run complete test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from pulse.connectors import register_all; from pulse.connectors.registry import ConnectorRegistry; from pulse.app.config import PulseConfig; r = ConnectorRegistry(); register_all(r, PulseConfig()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify CLI entry points**

Run: `python -m pulse.app.cli auth --help`
Expected: Shows help with `google` and `spotify` subcommands

- [ ] **Step 4: Verify Spotify auth manager end-to-end (unit)**

Run: `python -c "from pulse.connectors.spotify_auth import SpotifyAuthManager; from pathlib import Path; m = SpotifyAuthManager('id', 'sec', Path('/tmp/test_sp.json')); print(m._get_auth_url(['user-read-recently-played'], 'state123'))"`
Expected: Prints a valid Spotify authorization URL

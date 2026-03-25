# Phase 2: Media & Browsing Connectors

**Date:** 2026-03-25
**Status:** Approved
**Scope:** OAuthManager base class, Spotify connector, browser history connector, summarizer updates

---

## Context

Phase 1 established the connector infrastructure (registry, config, scheduler, interfaces) and added Google ecosystem connectors (Gmail, Calendar, YouTube). Phase 2 adds two new data sources — Spotify and browser history — to broaden cross-source pattern detection. It also refactors the OAuth layer to support multiple providers.

### Decisions Made

- **OAuth approach:** Generalized `OAuthManager` base class, refactor `GoogleAuthManager` to subclass it
- **Spotify data:** Frequent polling of recently played (30m) + supplementary pulls of saved/top data (6h)
- **Browser history:** Copy-then-read approach for safe SQLite access while browser is running
- **Browser support:** Single configurable `BrowserHistoryConnector` with presets for Chrome and Firefox
- **HTTP client:** `httpx` for Spotify API calls (async, no Spotify SDK)

---

## 1. OAuthManager Base Class

### Interface

```python
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

    # Concrete shared methods
    def is_authorized(self) -> bool:
        """Check if valid tokens exist on disk."""
        if not self._token_path.exists():
            return False
        return self.load_tokens() is not None

    def load_tokens(self) -> dict | None:
        """Load tokens from disk. Returns None if invalid."""
        try:
            return json.loads(self._token_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save_tokens(self, token_data: dict) -> None:
        """Persist tokens to disk."""
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(token_data))

    def get_valid_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        token_data = self.load_tokens()
        if token_data is None:
            raise RuntimeError("Not authorized.")
        if self._is_token_expired(token_data):
            token_data = self._refresh_access_token(token_data)
            self.save_tokens(token_data)
        return token_data["access_token"]
```

### GoogleAuthManager Migration

`GoogleAuthManager` becomes a subclass of `OAuthManager`, inheriting `is_authorized()`, `load_tokens()`, and `save_tokens()`. However, `GoogleAuthManager` **overrides `get_valid_token()` entirely** — it does not use the base class refresh path. This is because Google's token refresh requires `google.auth.transport.requests.Request` and constructs a full `google.oauth2.credentials.Credentials` object, which is incompatible with the base class's simple dict-based refresh.

`GoogleAuthManager.get_credentials()` remains the primary API for Google connectors. It loads tokens, constructs a `Credentials` object, refreshes via Google's transport if expired, and saves. The `authorize()` method continues to use `google_auth_oauthlib.flow.InstalledAppFlow` internally.

Existing Google connectors continue to call `auth_manager.get_credentials()` unchanged. The base class `get_valid_token()` is used only by non-Google subclasses like `SpotifyAuthManager`.

### SpotifyAuthManager

```python
class SpotifyAuthManager(OAuthManager):
    AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self, client_id: str, client_secret: str, token_path: Path) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret
```

Implements the four abstract methods using direct HTTP calls to Spotify's OAuth endpoints. No Spotify SDK needed.

**Scopes:** `user-read-recently-played`, `user-library-read`, `user-top-read`

**Redirect URI:** `http://localhost:8888/callback` — must be registered in the Spotify Developer Dashboard under the app's redirect URIs.

### CLI Extension

`pulse auth spotify` added alongside `pulse auth google`. The flow:

1. CLI generates a random `state` parameter for CSRF protection
2. Opens browser to Spotify's authorize URL with `client_id`, `redirect_uri=http://localhost:8888/callback`, `scope`, `state`, and `response_type=code`
3. Starts a temporary HTTP server on `localhost:8888`
4. User approves in browser → Spotify redirects to `localhost:8888/callback?code=...&state=...`
5. CLI validates `state` matches, extracts `code`
6. Calls `SpotifyAuthManager._exchange_code(code)` which POSTs to `https://accounts.spotify.com/api/token` with `grant_type=authorization_code`, `code`, `redirect_uri`, and HTTP Basic auth (`client_id:client_secret`)
7. Saves tokens to `data/spotify_tokens.json`

This uses the Authorization Code flow (not PKCE) since we have a `client_secret`. The temporary HTTP server is shut down after receiving the callback.

### Design Rationale

- Base class captures the common pattern: token file I/O, refresh logic, expiry check.
- Provider-specific logic (URL construction, token exchange, credential format) stays in subclasses.
- Google retains its `get_credentials()` for backward compatibility with google-api-python-client.
- Token files remain at `data/<provider>_tokens.json`.

---

## 2. Spotify Connector

### API Approach

Spotify Web API v1 provides:
- **Recently played** (`GET /me/player/recently-played`) — last 50 tracks, cursor-based
- **Saved tracks** (`GET /me/tracks`) — full library, paginated
- **Top tracks** (`GET /me/top/tracks`) — personalized, three time ranges
- **Top artists** (`GET /me/top/artists`) — personalized, three time ranges

Note: Spotify Development Mode (Feb 2026) requires Premium and limits to 5 authorized users per Client ID. This is fine for self-hosted.

### Dual Pull Strategy

The connector runs two pull strategies at different intervals:

**Frequent pull (default 30m):** Recently played tracks. Uses the `after` timestamp cursor from sync state to avoid duplicates. The 50-track limit means polling must be frequent enough to not miss plays.

**Supplementary pull (default 6h):** Saved tracks (new additions), top tracks, top artists. These change slowly and don't need frequent polling.

### SupplementaryPullMixin

To support the dual-interval pattern without changing the base `Connector` ABC:

```python
class SupplementaryPullMixin:
    def get_supplementary_jobs(self, config: ConnectorConfig) -> list[tuple[str, timedelta, Callable]]:
        """Return (job_id_suffix, interval, async_callable) tuples for extra scheduled jobs."""
        return []
```

The scheduler checks if a connector has this mixin and registers additional jobs. `SpotifyConnector` implements it; other connectors don't need to. The `config` parameter allows reading connector-specific settings like `supplementary_interval` from the TOML config.

### Event Types

| Event Type | Source | Data Fields |
|-----------|--------|-------------|
| `media.spotify.play` | Recently played | track_name, artist, album, played_at, duration_ms |
| `media.spotify.save` | Saved tracks | track_name, artist, album, saved_at |
| `media.spotify.top_track` | Top tracks | track_name, artist, rank, time_range, pulled_at |
| `media.spotify.top_artist` | Top artists | artist_name, genres, rank, time_range, pulled_at |

Note: `top_track` and `top_artist` events have no inherent timestamp from the API. The `Event.timestamp` is set to `datetime.now(UTC)` at pull time, and `pulled_at` is included in the data dict for clarity. These events represent a snapshot of the user's current top items, not a point-in-time occurrence.

### Implementation

```python
class SpotifyConnector(Connector, SupplementaryPullMixin):
    def __init__(self, auth_manager: SpotifyAuthManager | None = None) -> None:
        self._auth_manager = auth_manager

    def get_source_name(self) -> str:
        return "spotify"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        """Pull recently played tracks."""
        token = self._auth_manager.get_valid_token()
        # GET /me/player/recently-played?after=<cursor>&limit=50
        # Convert to Event objects with type media.spotify.play
        ...

    def get_supplementary_jobs(self, config: ConnectorConfig) -> list[tuple[str, timedelta, Callable]]:
        interval_str = getattr(config, "supplementary_interval", "6h")
        from pulse.jobs.scheduler import parse_interval
        interval = parse_interval(interval_str)
        return [("supplementary", interval, self._pull_supplementary)]

    async def _pull_supplementary(self) -> list[Event]:
        """Pull saved tracks, top tracks, top artists. Stateless — no sync cursor."""
        ...
```

### Config

```toml
[connectors.spotify]
enabled = true
poll_interval = "30m"
supplementary_interval = "6h"
```

### Dependencies

- `httpx` — async HTTP client for Spotify API calls

---

## 3. Browser History Connector

### Approach

Copy-then-read: copy the browser's SQLite history file to a temp location, query the copy, clean up. This avoids file locking issues when the browser is running.

### Browser Presets

```python
BROWSER_PRESETS = {
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
        "epoch_offset": 11_644_473_600,  # 1601 → 1970
        "timestamp_divisor": 1_000_000,  # microseconds → seconds
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
```

### Event Type

| Event Type | Data Fields |
|-----------|-------------|
| `browsing.visit` | url, title, visit_time, browser |

### Implementation

```python
class BrowserHistoryConnector(Connector):
    def __init__(self, browser: str = "chrome", db_path: str | None = None) -> None:
        self._browser = browser
        self._db_path = db_path  # override for custom path

    def get_source_name(self) -> str:
        return "browser"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        path = self._resolve_db_path()
        return path is not None and path.exists()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        db_path = self._resolve_db_path()
        # Use mkstemp + manual cleanup to avoid Windows file locking issues
        fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            shutil.copy2(db_path, tmp_path)
            # Query visits since cursor, normalize timestamps
            # Formula: unix_ts = (raw_value / timestamp_divisor) - epoch_offset
            ...
        finally:
            os.unlink(tmp_path)

    def _resolve_db_path(self) -> Path | None:
        if self._db_path:
            return Path(self._db_path).expanduser()
        preset = BROWSER_PRESETS.get(self._browser)
        if not preset:
            return None
        platform_path = preset.get(sys.platform)
        if not platform_path:
            return None
        # Handle glob patterns (Firefox profile dirs)
        expanded = Path(platform_path).expanduser()
        if "*" in platform_path:
            matches = list(Path("/").glob(str(expanded).lstrip("/")))
            if not matches:
                return None
            # Sort by modification time descending — most recently used profile first
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]
        return expanded
```

### Config

```toml
[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"
# db_path = "/custom/path/to/History"  # optional override
```

### No New Dependencies

Uses `sqlite3` (stdlib), `shutil.copy2`, `tempfile`.

---

## 4. Scheduler Extension

The scheduler gains awareness of `SupplementaryPullMixin`:

```python
# In build_scheduler(), after creating the standard pull job:
if hasattr(connector, "get_supplementary_jobs"):
    for suffix, interval, job_fn in connector.get_supplementary_jobs(cc):
        scheduler.add_job(
            _make_supplementary_job(job_fn, config),
            trigger=IntervalTrigger(seconds=int(interval.total_seconds())),
            id=f"pull_{connector.get_source_name()}_{suffix}",
        )
```

### `_make_supplementary_job` wrapper

Supplementary jobs are **stateless** — they do not read or write sync state. This avoids cursor collisions with the main `pull()` which uses its own sync state cursor. The wrapper is simpler than `_make_pull_job`:

```python
def _make_supplementary_job(job_fn, config):
    async def job():
        events = await job_fn()
        if events:
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                await event_repo.upsert_events(events)
    return job
```

Events are upserted with stable IDs (e.g., `spotify:top_track:{track_id}:{time_range}`) so repeated pulls overwrite rather than duplicate.

---

## 5. Summarizer Updates

The `DailySummarizer` is extended to route new event types:

- `media.spotify.play` → `media_items` (format: "Listened to {track} by {artist}")
- `browsing.visit` → `browsing_items` (new section)

The `render_daily_digest` function gains a `browsing_items: list[str] = []` parameter (keyword-only, with default, backward-compatible) and a new "Browsing" section in the digest. The `DailySummarizer.summarize()` call site is updated to pass `browsing_items` and `media_items` from the new event types.

---

## 6. Registration and Config

### Connector Registration

```python
def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    # ... existing Google connectors ...

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

### PulseConfig Additions

```python
class PulseConfig(BaseModel):
    # ... existing fields ...
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
```

Secrets follow the Phase 1 convention: sourced from `PULSE_SPOTIFY_CLIENT_ID` and `PULSE_SPOTIFY_CLIENT_SECRET` env vars (handled by `config_loader.py`'s existing `PULSE_` prefix env var override). Never stored in `pulse.toml`.

### pulse.toml Additions

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

---

## 7. Testing Strategy

### Unit Tests

- `OAuthManager` — token load/save, expiry check, refresh delegation
- `SpotifyAuthManager` — auth URL construction, token exchange (mock HTTP)
- `SpotifyConnector` — recently played parsing, saved tracks parsing, top tracks/artists parsing (mock HTTP responses)
- `BrowserHistoryConnector` — Chrome timestamp normalization, Firefox timestamp normalization, path resolution per platform, copy-then-read with fixture SQLite DB
- Summarizer — new event type routing to correct digest sections

### Integration Tests

- Spotify full pull cycle with mocked HTTP → event store → sync state
- Browser history pull from a test-fixture SQLite DB → event store
- Registry startup with Spotify + browser connectors (validate_config behavior)

### E2E Tests

- `tests/e2e/test_spotify_live.py` — manual run with real Spotify credentials (skipped by default)
- `tests/e2e/test_browser_live.py` — reads actual browser history (skipped by default)

---

## 8. New Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | Async HTTP client for Spotify API |

---

## 9. Future Phases

| Phase | Scope | Connectors |
|-------|-------|------------|
| 3 | Financial | Plaid (bank transactions) |
| 4 | Health & Location | HealthKit, fitness trackers, location webhooks |

Each phase follows its own spec → plan → implementation cycle.

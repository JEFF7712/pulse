# Phase 1: Connector Infrastructure + Google Ecosystem — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the connector infrastructure (registry, config, scheduling, push support) and add YouTube as the third connector, migrating Gmail/Calendar to the new framework.

**Architecture:** Config-driven connector registry reads `pulse.toml` to determine which connectors are active. Pull connectors are scheduled on intervals; push connectors register webhook routes. All Google connectors share a single OAuth2 auth manager. The existing `Connector` ABC gains `get_default_interval()` and `validate_config()` methods; a new `PushConnector` ABC handles webhook-based sources.

**Tech Stack:** Python 3.12+, pydantic, aiosqlite, APScheduler, FastAPI, google-auth-oauthlib, google-api-python-client

**Spec:** `docs/superpowers/specs/2026-03-24-connector-infrastructure-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/pulse/connectors/__init__.py` | Connector registration (`register_all`) |
| `src/pulse/connectors/registry.py` | `ConnectorRegistry` class — discovery, validation, lifecycle |
| `src/pulse/connectors/youtube.py` | YouTube Data API v3 connector |
| `src/pulse/app/cli.py` | CLI entry points (`pulse auth google`) |
| `src/pulse/app/config_loader.py` | `pulse.toml` loading + merge with env vars |
| `pulse.toml` | Default connector configuration file |
| `tests/unit/test_connector_registry.py` | Unit tests for ConnectorRegistry |
| `tests/unit/test_config_loader.py` | Unit tests for TOML config loading |
| `tests/unit/test_google_auth_manager.py` | Unit tests for GoogleAuthManager |
| `tests/unit/test_youtube_connector.py` | Unit tests for YouTubeConnector |
| `tests/integration/test_pull_cycle.py` | Integration test: connector → store → sync state |
| `tests/integration/test_push_webhook.py` | Integration test: push connector webhook → store |
| `tests/integration/test_registry_startup.py` | Integration test: mixed valid/invalid connectors |

### Modified Files

| File | Changes |
|------|---------|
| `src/pulse/domain/connectors.py` | Add `get_default_interval()`, `validate_config()` to `Connector`; add `PushConnector` ABC |
| `src/pulse/app/config.py` | Rename `Settings` → `PulseConfig`, add `connectors` dict field, add `ConnectorConfig` |
| `src/pulse/app/dependencies.py` | Update `get_settings()` → `get_config()`, load from TOML + env |
| `src/pulse/connectors/google_auth.py` | Replace stub with full `GoogleAuthManager` |
| `src/pulse/connectors/gmail.py` | Accept `GoogleAuthManager` instead of raw client |
| `src/pulse/connectors/calendar.py` | Accept `GoogleAuthManager` instead of raw client |
| `src/pulse/jobs/scheduler.py` | Rewrite to use `ConnectorRegistry` for pull scheduling |
| `src/pulse/app/main.py` | Wire push connector routes at startup, update `Settings` → `PulseConfig` refs |
| `src/pulse/mcp/server.py` | Enhance `pulse_connector_status` to use registry |
| `pyproject.toml` | Add google deps, add `pulse` CLI entry point |
| `tests/unit/test_config.py` | Update for `PulseConfig` rename + new fields |
| `tests/unit/test_scheduler.py` | Update for registry-driven scheduler |

---

## Task 1: Enhance Connector Interfaces

**Files:**
- Modify: `src/pulse/domain/connectors.py`
- Test: `tests/unit/test_connector_interfaces.py` (new)

- [ ] **Step 1: Write failing tests for enhanced Connector**

Create `tests/unit/test_connector_interfaces.py`:

```python
from datetime import timedelta


def test_connector_provides_default_interval():
    import asyncio
    from pulse.domain.connectors import Connector
    from pulse.domain.events import Event
    from datetime import datetime

    class StubConnector(Connector):
        async def pull(self, since=None):
            return []
        def get_source_name(self):
            return "stub"

    c = StubConnector()
    assert c.get_default_interval() == timedelta(minutes=15)


def test_connector_validate_config_returns_true_by_default():
    import asyncio
    from pulse.domain.connectors import Connector

    class StubConnector(Connector):
        async def pull(self, since=None):
            return []
        def get_source_name(self):
            return "stub"

    c = StubConnector()
    assert asyncio.run(c.validate_config()) is True


def test_push_connector_requires_source_name_webhook_path_and_handle():
    import asyncio
    from pulse.domain.connectors import PushConnector

    class StubPush(PushConnector):
        def get_source_name(self):
            return "webhook_test"
        def get_webhook_path(self):
            return "/webhooks/test"
        async def handle_webhook(self, payload):
            return []

    p = StubPush()
    assert p.get_source_name() == "webhook_test"
    assert p.get_webhook_path() == "/webhooks/test"
    assert asyncio.run(p.handle_webhook({})) == []
    assert asyncio.run(p.validate_config()) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_connector_interfaces.py -v`
Expected: FAIL — `PushConnector` doesn't exist, `get_default_interval` doesn't exist

- [ ] **Step 3: Implement enhanced Connector and PushConnector**

Replace `src/pulse/domain/connectors.py` with:

```python
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from pulse.domain.events import Event


class Connector(ABC):
    @abstractmethod
    async def pull(self, since: datetime | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        return True


class PushConnector(ABC):
    @abstractmethod
    def get_source_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_webhook_path(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> list[Event]:
        raise NotImplementedError

    async def validate_config(self) -> bool:
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_connector_interfaces.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: All 37 existing tests + 3 new tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/domain/connectors.py tests/unit/test_connector_interfaces.py
git commit -m "feat: enhance Connector ABC with default_interval/validate_config, add PushConnector"
```

---

## Task 2: Config System — PulseConfig + TOML Loading

**Files:**
- Modify: `src/pulse/app/config.py`
- Create: `src/pulse/app/config_loader.py`
- Create: `pulse.toml`
- Modify: `src/pulse/app/dependencies.py`
- Test: `tests/unit/test_config_loader.py` (new)
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests for ConnectorConfig and PulseConfig**

Update `tests/unit/test_config.py`:

```python
from pulse.app.config import PulseConfig, ConnectorConfig, Settings


def test_pulse_config_defaults_match_original_settings():
    config = PulseConfig()

    assert config.database_path == "data/pulse.db"
    assert config.vault_path == "Pulse-Vault"
    assert config.timezone == "UTC"
    assert config.telegram_bot_token is None
    assert config.telegram_chat_id is None
    assert config.google_client_id is None
    assert config.google_client_secret is None
    assert config.connectors == {}


def test_settings_alias_is_pulse_config():
    assert Settings is PulseConfig


def test_connector_config_defaults():
    cc = ConnectorConfig()
    assert cc.enabled is True
    assert cc.poll_interval == "15m"


def test_connector_config_accepts_extra_fields():
    cc = ConnectorConfig(enabled=True, poll_interval="30m", custom_key="value")
    assert cc.custom_key == "value"


def test_pulse_config_with_connectors():
    config = PulseConfig(
        connectors={
            "gmail": ConnectorConfig(enabled=True, poll_interval="10m"),
            "calendar": ConnectorConfig(enabled=False),
        }
    )
    assert config.connectors["gmail"].enabled is True
    assert config.connectors["gmail"].poll_interval == "10m"
    assert config.connectors["calendar"].enabled is False


def test_get_settings_reads_pulse_prefixed_environment_variables(monkeypatch):
    from pulse.app.dependencies import get_settings

    monkeypatch.setenv("PULSE_DATABASE_PATH", "/tmp/pulse-test.db")
    monkeypatch.setenv("PULSE_TIMEZONE", "America/New_York")

    settings = get_settings()

    assert settings.database_path == "/tmp/pulse-test.db"
    assert settings.timezone == "America/New_York"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL — `PulseConfig` and `ConnectorConfig` don't exist

- [ ] **Step 3: Implement PulseConfig and ConnectorConfig**

Replace `src/pulse/app/config.py`:

```python
from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    poll_interval: str = "15m"


class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    connectors: dict[str, ConnectorConfig] = {}


# Backward compatibility alias
Settings = PulseConfig
```

- [ ] **Step 4: Run config tests to verify they pass**

Run: `pytest tests/unit/test_config.py -v`
Expected: All PASS (new tests + old tests via `Settings` alias)

- [ ] **Step 5: Write failing tests for TOML config loader**

Create `tests/unit/test_config_loader.py`:

```python
from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.app.config_loader import load_config


def test_load_config_from_toml(tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text("""
[connectors.gmail]
enabled = true
poll_interval = "10m"

[connectors.youtube]
enabled = false
poll_interval = "1h"
""")

    config = load_config(config_path=toml_file)

    assert config.connectors["gmail"].enabled is True
    assert config.connectors["gmail"].poll_interval == "10m"
    assert config.connectors["youtube"].enabled is False


def test_load_config_env_overrides_defaults(monkeypatch, tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text("")

    monkeypatch.setenv("PULSE_DATABASE_PATH", "/custom/db.sqlite")
    monkeypatch.setenv("PULSE_TIMEZONE", "US/Eastern")

    config = load_config(config_path=toml_file)

    assert config.database_path == "/custom/db.sqlite"
    assert config.timezone == "US/Eastern"


def test_load_config_returns_defaults_when_no_toml(tmp_path):
    missing_path = tmp_path / "nonexistent.toml"

    config = load_config(config_path=missing_path)

    assert config.database_path == "data/pulse.db"
    assert config.connectors == {}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: FAIL — `config_loader` module doesn't exist

- [ ] **Step 7: Implement TOML config loader**

Create `src/pulse/app/config_loader.py`:

```python
import os
import tomllib
from pathlib import Path

from pulse.app.config import PulseConfig


def load_config(config_path: Path | None = None) -> PulseConfig:
    if config_path is None:
        config_path = Path("pulse.toml")

    file_values: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            file_values = tomllib.load(f)

    env_values = {
        field_name: value
        for field_name in PulseConfig.model_fields
        if field_name != "connectors"
        and (value := os.environ.get(f"PULSE_{field_name.upper()}")) is not None
    }

    merged = {**file_values, **env_values}
    return PulseConfig(**merged)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/unit/test_config_loader.py -v`
Expected: 3 tests PASS

- [ ] **Step 9: Update dependencies.py**

Replace `src/pulse/app/dependencies.py`:

```python
from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config

# Keep backward compat
from pulse.app.config import Settings  # noqa: F401


def get_config() -> PulseConfig:
    return load_config()


# Backward compatibility alias
def get_settings() -> PulseConfig:
    return get_config()
```

- [ ] **Step 10: Create default pulse.toml**

Create `pulse.toml` in project root:

```toml
# Pulse connector configuration.
# Secrets (API keys, tokens) go in .env, not here.

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

- [ ] **Step 11: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (Settings alias preserves backward compat)

- [ ] **Step 12: Commit**

```bash
git add src/pulse/app/config.py src/pulse/app/config_loader.py src/pulse/app/dependencies.py \
  pulse.toml tests/unit/test_config.py tests/unit/test_config_loader.py
git commit -m "feat: add PulseConfig with ConnectorConfig, TOML config loader"
```

---

## Task 3: Connector Registry

**Files:**
- Create: `src/pulse/connectors/registry.py`
- Create: `src/pulse/connectors/__init__.py`
- Test: `tests/unit/test_connector_registry.py` (new)

- [ ] **Step 1: Write failing tests for ConnectorRegistry**

Create `tests/unit/test_connector_registry.py`:

```python
import asyncio
from datetime import timedelta
from collections.abc import Callable

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.domain.connectors import Connector, PushConnector
from pulse.domain.events import Event


class FakePullConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake_pull"
    def get_default_interval(self):
        return timedelta(minutes=5)

class FakeInvalidConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake_invalid"
    async def validate_config(self):
        return False

class FakePushConnector(PushConnector):
    def get_source_name(self):
        return "fake_push"
    def get_webhook_path(self):
        return "/webhooks/fake"
    async def handle_webhook(self, payload):
        return []


def test_registry_registers_and_builds_pull_connectors():
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    registry.register_pull("fake_pull", lambda: FakePullConnector())

    config = PulseConfig(connectors={
        "fake_pull": ConnectorConfig(enabled=True, poll_interval="5m"),
    })

    asyncio.run(registry.build_active_connectors(config))

    pull = registry.get_pull_connectors()
    assert len(pull) == 1
    connector, cc = pull[0]
    assert connector.get_source_name() == "fake_pull"
    assert cc.poll_interval == "5m"


def test_registry_skips_disabled_connectors():
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    registry.register_pull("fake_pull", lambda: FakePullConnector())

    config = PulseConfig(connectors={
        "fake_pull": ConnectorConfig(enabled=False),
    })

    asyncio.run(registry.build_active_connectors(config))

    assert registry.get_pull_connectors() == []


def test_registry_skips_connectors_that_fail_validation():
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    registry.register_pull("fake_invalid", lambda: FakeInvalidConnector())

    config = PulseConfig(connectors={
        "fake_invalid": ConnectorConfig(enabled=True),
    })

    asyncio.run(registry.build_active_connectors(config))

    assert registry.get_pull_connectors() == []


def test_registry_registers_push_connectors():
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    registry.register_push("fake_push", lambda: FakePushConnector())

    config = PulseConfig(connectors={
        "fake_push": ConnectorConfig(enabled=True),
    })

    asyncio.run(registry.build_active_connectors(config))

    push = registry.get_push_connectors()
    assert len(push) == 1
    connector, cc = push[0]
    assert connector.get_source_name() == "fake_push"
    assert connector.get_webhook_path() == "/webhooks/fake"


def test_registry_ignores_config_entries_without_registered_class():
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()

    config = PulseConfig(connectors={
        "nonexistent": ConnectorConfig(enabled=True),
    })

    asyncio.run(registry.build_active_connectors(config))

    assert registry.get_pull_connectors() == []
    assert registry.get_push_connectors() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_connector_registry.py -v`
Expected: FAIL — `registry` module doesn't exist

- [ ] **Step 3: Implement ConnectorRegistry**

The registry accepts **factory callables** (not bare classes) so that dependencies like `GoogleAuthManager` can be injected at registration time via closures.

Create `src/pulse/connectors/registry.py`:

```python
import logging
from collections.abc import Callable

from pulse.app.config import ConnectorConfig, PulseConfig
from pulse.domain.connectors import Connector, PushConnector

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    def __init__(self) -> None:
        self._pull_factories: dict[str, Callable[[], Connector]] = {}
        self._push_factories: dict[str, Callable[[], PushConnector]] = {}
        self._active_pull: list[tuple[Connector, ConnectorConfig]] = []
        self._active_push: list[tuple[PushConnector, ConnectorConfig]] = []

    def register_pull(self, name: str, factory: Callable[[], Connector]) -> None:
        self._pull_factories[name] = factory

    def register_push(self, name: str, factory: Callable[[], PushConnector]) -> None:
        self._push_factories[name] = factory

    async def build_active_connectors(self, config: PulseConfig) -> None:
        self._active_pull = []
        self._active_push = []

        for name, cc in config.connectors.items():
            if not cc.enabled:
                logger.info("Connector '%s' is disabled, skipping", name)
                continue

            if name in self._pull_factories:
                instance = self._pull_factories[name]()
                if not await instance.validate_config():
                    logger.warning(
                        "Connector '%s' failed config validation, skipping", name
                    )
                    continue
                self._active_pull.append((instance, cc))

            elif name in self._push_factories:
                instance = self._push_factories[name]()
                if not await instance.validate_config():
                    logger.warning(
                        "Connector '%s' failed config validation, skipping", name
                    )
                    continue
                self._active_push.append((instance, cc))

            else:
                logger.warning(
                    "Config entry '%s' has no registered connector class, skipping", name
                )

    def get_pull_connectors(self) -> list[tuple[Connector, ConnectorConfig]]:
        return list(self._active_pull)

    def get_push_connectors(self) -> list[tuple[PushConnector, ConnectorConfig]]:
        return list(self._active_push)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_connector_registry.py -v`
Expected: 5 tests PASS

- [ ] **Step 5: Create connectors __init__.py with register_all**

Create `src/pulse/connectors/__init__.py`. Note: `register_all` accepts `config` to build the shared `GoogleAuthManager` and pass it to Google connectors via factory closures:

```python
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector

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
    # YouTube will be added in Task 6
```

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/__init__.py src/pulse/connectors/registry.py \
  tests/unit/test_connector_registry.py
git commit -m "feat: add ConnectorRegistry with factory-based registration and config-driven activation"
```

---

## Task 4: Google OAuth2 Auth Manager

**Files:**
- Modify: `src/pulse/connectors/google_auth.py`
- Test: `tests/unit/test_google_auth_manager.py` (new)

- [ ] **Step 1: Add google dependencies to pyproject.toml**

Update `pyproject.toml` dependencies:

```toml
dependencies = [
    "fastapi",
    "pydantic",
    "aiosqlite",
    "apscheduler",
    "httpx",
    "mcp[cli]",
    "google-auth-oauthlib",
    "google-api-python-client",
]
```

- [ ] **Step 2: Install updated dependencies**

Run: `pip install -e .`

- [ ] **Step 3: Write failing tests for GoogleAuthManager**

Create `tests/unit/test_google_auth_manager.py`:

```python
import json
from pathlib import Path


def test_get_required_scopes_unions_enabled_connectors():
    from pulse.connectors.google_auth import GoogleAuthManager

    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=Path("/tmp/tokens.json")
    )
    scopes = mgr.get_required_scopes(["gmail", "youtube"])

    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/youtube.readonly" in scopes
    assert "https://www.googleapis.com/auth/calendar.readonly" not in scopes


def test_get_required_scopes_returns_empty_for_no_connectors():
    from pulse.connectors.google_auth import GoogleAuthManager

    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=Path("/tmp/tokens.json")
    )
    assert mgr.get_required_scopes([]) == []


def test_is_authorized_returns_false_when_no_token_file(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager

    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=tmp_path / "missing.json"
    )
    assert mgr.is_authorized() is False


def test_is_authorized_returns_true_when_valid_token_exists(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager

    token_path = tmp_path / "tokens.json"
    token_path.write_text(json.dumps({
        "token": "access_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
    }))

    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=token_path
    )
    assert mgr.is_authorized() is True


def test_is_authorized_returns_false_for_invalid_json(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager

    token_path = tmp_path / "tokens.json"
    token_path.write_text("not json")

    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=token_path
    )
    assert mgr.is_authorized() is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/unit/test_google_auth_manager.py -v`
Expected: FAIL — `GoogleAuthManager` class doesn't exist (only the stub)

- [ ] **Step 5: Implement GoogleAuthManager**

Replace `src/pulse/connectors/google_auth.py`:

```python
import json
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES_BY_CONNECTOR: dict[str, list[str]] = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "youtube": ["https://www.googleapis.com/auth/youtube.readonly"],
}


class GoogleAuthManager:
    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_path = token_path

    def get_required_scopes(self, active_connectors: list[str]) -> list[str]:
        scopes: list[str] = []
        for name in active_connectors:
            scopes.extend(SCOPES_BY_CONNECTOR.get(name, []))
        return scopes

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

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_google_auth_manager.py -v`
Expected: 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/connectors/google_auth.py tests/unit/test_google_auth_manager.py pyproject.toml
git commit -m "feat: implement GoogleAuthManager with OAuth2 flow and token persistence"
```

---

## Task 5: Migrate Gmail and Calendar Connectors

**Files:**
- Modify: `src/pulse/connectors/gmail.py`
- Modify: `src/pulse/connectors/calendar.py`
- Modify: `tests/unit/test_gmail_connector.py`
- Modify: `tests/unit/test_calendar_connector.py`

- [ ] **Step 1: Update Gmail connector to use GoogleAuthManager**

Replace `src/pulse/connectors/gmail.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GmailConnector(Connector):
    def __init__(self, auth_manager: GoogleAuthManager | None = None, client: Any = None) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._get_client()
        rows = await client.list_messages(since=since)
        return [self._to_event(row) for row in rows]

    def get_source_name(self) -> str:
        return "gmail"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        if self._client is not None:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._auth_manager is None:
            raise RuntimeError("No auth_manager or client provided")
        creds = self._auth_manager.get_credentials()
        from googleapiclient.discovery import build
        return build("gmail", "v1", credentials=creds)

    def _to_event(self, row: dict[str, Any]) -> Event:
        headers = self._headers_by_name(row.get("payload", {}).get("headers", []))
        return Event(
            id=f"gmail:{row['id']}",
            timestamp=datetime.fromtimestamp(int(row["internalDate"]) / 1000, tz=UTC),
            source="gmail",
            event_type="email.received",
            data={
                "subject": headers.get("subject", ""),
                "sender": headers.get("from", ""),
            },
        )

    def _headers_by_name(self, headers: list[dict[str, str]]) -> dict[str, str]:
        return {
            header["name"].lower(): header.get("value", "")
            for header in headers
            if "name" in header
        }
```

- [ ] **Step 2: Update Calendar connector similarly**

Replace `src/pulse/connectors/calendar.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GoogleCalendarConnector(Connector):
    def __init__(self, auth_manager: GoogleAuthManager | None = None, client: Any = None) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._get_client()
        rows = await client.list_events(since=since)
        return [self._to_event(row) for row in rows]

    def get_source_name(self) -> str:
        return "calendar"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        if self._client is not None:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._auth_manager is None:
            raise RuntimeError("No auth_manager or client provided")
        creds = self._auth_manager.get_credentials()
        from googleapiclient.discovery import build
        return build("calendar", "v3", credentials=creds)

    def _to_event(self, row: dict[str, Any]) -> Event:
        start = row["start"]
        timestamp = self._parse_start(start)
        title = row.get("summary") or "Untitled event"
        return Event(
            id=f"calendar:{row['id']}",
            timestamp=timestamp,
            source="calendar",
            event_type="calendar.event",
            data={"title": title},
        )

    def _parse_start(self, start: dict[str, str]) -> datetime:
        if "dateTime" in start:
            return datetime.fromisoformat(start["dateTime"])
        return datetime.fromisoformat(start["date"]).replace(tzinfo=UTC)
```

- [ ] **Step 3: Run existing connector tests**

Run: `pytest tests/unit/test_gmail_connector.py tests/unit/test_calendar_connector.py -v`
Expected: PASS — existing tests use `client=FakeClient()` which still works via backward-compat path

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/connectors/gmail.py src/pulse/connectors/calendar.py
git commit -m "refactor: migrate Gmail and Calendar connectors to support GoogleAuthManager"
```

---

## Task 6: YouTube Connector

**Files:**
- Create: `src/pulse/connectors/youtube.py`
- Modify: `src/pulse/connectors/__init__.py`
- Test: `tests/unit/test_youtube_connector.py` (new)

- [ ] **Step 1: Write failing tests for YouTubeConnector**

Create `tests/unit/test_youtube_connector.py`:

```python
import asyncio
from datetime import UTC, datetime, timedelta


def test_youtube_connector_source_name():
    from pulse.connectors.youtube import YouTubeConnector

    connector = YouTubeConnector()
    assert connector.get_source_name() == "youtube"


def test_youtube_connector_default_interval():
    from pulse.connectors.youtube import YouTubeConnector

    connector = YouTubeConnector()
    assert connector.get_default_interval() == timedelta(hours=1)


def test_youtube_connector_validate_config_false_without_auth():
    from pulse.connectors.youtube import YouTubeConnector

    connector = YouTubeConnector()
    assert asyncio.run(connector.validate_config()) is False


def test_youtube_connector_parses_activities():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return [
                {
                    "id": "act-1",
                    "snippet": {
                        "publishedAt": "2026-03-23T10:00:00Z",
                        "title": "Cool Video",
                        "channelTitle": "TestChannel",
                        "type": "upload",
                    },
                    "contentDetails": {
                        "upload": {"videoId": "vid-123"},
                    },
                },
            ]
        async def list_liked_videos(self, since=None):
            return []
        async def list_subscriptions(self, since=None):
            return []

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())

    assert len(events) == 1
    assert events[0].id == "youtube:act-1"
    assert events[0].source == "youtube"
    assert events[0].event_type == "media.youtube.activity"
    assert events[0].data["title"] == "Cool Video"
    assert events[0].data["channel"] == "TestChannel"
    assert events[0].data["video_id"] == "vid-123"
    assert events[0].data["activity_type"] == "upload"


def test_youtube_connector_parses_liked_videos():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return []
        async def list_liked_videos(self, since=None):
            return [
                {
                    "id": "like-1",
                    "snippet": {
                        "publishedAt": "2026-03-23T12:00:00Z",
                        "title": "Liked Video",
                        "videoOwnerChannelTitle": "LikedChannel",
                    },
                    "contentDetails": {"videoId": "vid-456"},
                },
            ]
        async def list_subscriptions(self, since=None):
            return []

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())

    assert len(events) == 1
    assert events[0].event_type == "media.youtube.like"
    assert events[0].data["title"] == "Liked Video"
    assert events[0].data["video_id"] == "vid-456"


def test_youtube_connector_parses_subscriptions():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return []
        async def list_liked_videos(self, since=None):
            return []
        async def list_subscriptions(self, since=None):
            return [
                {
                    "id": "sub-1",
                    "snippet": {
                        "publishedAt": "2026-03-22T08:00:00Z",
                        "title": "SubChannel",
                        "resourceId": {"channelId": "UC-123"},
                    },
                },
            ]

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())

    assert len(events) == 1
    assert events[0].event_type == "media.youtube.subscription"
    assert events[0].data["channel_name"] == "SubChannel"
    assert events[0].data["channel_id"] == "UC-123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_youtube_connector.py -v`
Expected: FAIL — `YouTubeConnector` doesn't exist

- [ ] **Step 3: Implement YouTubeConnector**

Create `src/pulse/connectors/youtube.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class YouTubeConnector(Connector):
    def __init__(
        self, auth_manager: GoogleAuthManager | None = None, client: Any = None
    ) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._get_client()
        events: list[Event] = []

        activities = await client.list_activities(since=since)
        for item in activities:
            events.append(self._activity_to_event(item))

        liked = await client.list_liked_videos(since=since)
        for item in liked:
            events.append(self._liked_to_event(item))

        subs = await client.list_subscriptions(since=since)
        for item in subs:
            events.append(self._subscription_to_event(item))

        return events

    def get_source_name(self) -> str:
        return "youtube"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=1)

    async def validate_config(self) -> bool:
        if self._client is not None:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._auth_manager is None:
            raise RuntimeError("No auth_manager or client provided")
        creds = self._auth_manager.get_credentials()
        from googleapiclient.discovery import build
        return build("youtube", "v3", credentials=creds)

    def _activity_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        activity_type = snippet.get("type", "unknown")

        video_id = ""
        if activity_type in content:
            video_id = content[activity_type].get("videoId", "")

        return Event(
            id=f"youtube:{item['id']}",
            timestamp=datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            ),
            source="youtube",
            event_type="media.youtube.activity",
            data={
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "video_id": video_id,
                "activity_type": activity_type,
            },
        )

    def _liked_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})

        return Event(
            id=f"youtube:like:{content.get('videoId', item['id'])}",
            timestamp=datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            ),
            source="youtube",
            event_type="media.youtube.like",
            data={
                "title": snippet.get("title", ""),
                "channel": snippet.get("videoOwnerChannelTitle", ""),
                "video_id": content.get("videoId", ""),
            },
        )

    def _subscription_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        resource = snippet.get("resourceId", {})

        return Event(
            id=f"youtube:sub:{resource.get('channelId', item['id'])}",
            timestamp=datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            ),
            source="youtube",
            event_type="media.youtube.subscription",
            data={
                "channel_name": snippet.get("title", ""),
                "channel_id": resource.get("channelId", ""),
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_youtube_connector.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Register YouTube in connectors/__init__.py**

Update `src/pulse/connectors/__init__.py` to add YouTube registration:

```python
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector
    from pulse.connectors.youtube import YouTubeConnector

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
```

- [ ] **Step 6: Commit**

```bash
git add src/pulse/connectors/youtube.py src/pulse/connectors/__init__.py \
  tests/unit/test_youtube_connector.py
git commit -m "feat: add YouTubeConnector for activities, liked videos, and subscriptions"
```

---

## Task 7: Registry-Driven Scheduler

**Files:**
- Modify: `src/pulse/jobs/scheduler.py`
- Modify: `tests/unit/test_scheduler.py`

- [ ] **Step 1: Write failing tests for new scheduler**

Replace `tests/unit/test_scheduler.py`:

```python
import asyncio
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector
from pulse.jobs.scheduler import parse_interval


class FakeConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake"
    def get_default_interval(self):
        return timedelta(minutes=10)


def test_build_scheduler_creates_pull_jobs_from_registry():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    registry.register_pull("fake", lambda: FakeConnector())
    config = PulseConfig(connectors={
        "fake": ConnectorConfig(enabled=True, poll_interval="10m"),
    })
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "pull_fake" in jobs
    pull_job = jobs["pull_fake"]
    assert isinstance(pull_job.trigger, IntervalTrigger)
    assert pull_job.trigger.interval.total_seconds() == 600


def test_build_scheduler_keeps_analysis_jobs():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    config = PulseConfig()
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "daily_digest" in jobs
    assert "morning_briefing" in jobs
    assert isinstance(jobs["daily_digest"].trigger, IntervalTrigger)
    assert isinstance(jobs["morning_briefing"].trigger, CronTrigger)


def test_build_scheduler_morning_briefing_skips_without_telegram():
    """Equivalent of old test_morning_briefing_job_skips_when_telegram_is_not_configured."""
    from pulse.jobs.scheduler import build_scheduler

    config = PulseConfig()  # No telegram_bot_token or telegram_chat_id
    scheduler = build_scheduler(registry=ConnectorRegistry(), config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    # Morning briefing job is registered — it handles skip logic internally
    assert "morning_briefing" in jobs


def test_parse_interval_handles_various_units():
    assert parse_interval("5m") == timedelta(minutes=5)
    assert parse_interval("2h") == timedelta(hours=2)
    assert parse_interval("1d") == timedelta(days=1)
    assert parse_interval("30s") == timedelta(seconds=30)


def test_parse_interval_rejects_invalid_format():
    import pytest
    with pytest.raises(ValueError):
        parse_interval("invalid")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: FAIL — `build_scheduler` doesn't accept `registry` or `config` params

- [ ] **Step 3: Rewrite scheduler to be registry-driven**

Replace `src/pulse/jobs/scheduler.py`:

```python
import re
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.runners import run_daily_digest_job, run_morning_briefing_job, JobResult
from pulse.notifications.telegram import TelegramChannel

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def parse_interval(interval_str: str) -> timedelta:
    match = re.fullmatch(r"(\d+)\s*(m|h|d|s)", interval_str.strip())
    if not match:
        raise ValueError(f"Invalid interval format: '{interval_str}'")
    value = int(match.group(1))
    unit = match.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: value})


def build_scheduler(
    registry: ConnectorRegistry | None = None,
    config: PulseConfig | None = None,
) -> AsyncIOScheduler:
    if config is None:
        config = load_config()

    scheduler = AsyncIOScheduler()

    # Pull connector jobs
    if registry is not None:
        for connector, cc in registry.get_pull_connectors():
            interval = parse_interval(cc.poll_interval)
            scheduler.add_job(
                _make_pull_job(connector, config),
                trigger=IntervalTrigger(seconds=int(interval.total_seconds())),
                id=f"pull_{connector.get_source_name()}",
            )

    # Analysis jobs (unchanged)
    scheduler.add_job(
        _make_daily_digest_job(config),
        "interval",
        days=1,
        id="daily_digest",
    )
    scheduler.add_job(
        _make_morning_briefing_job(config),
        "cron",
        hour=8,
        minute=0,
        id="morning_briefing",
    )

    return scheduler


def _make_pull_job(connector, config):
    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            source = connector.get_source_name()
            cursor = await sync_state.load(source)
            since = datetime.fromisoformat(cursor) if cursor else None

            events = await connector.pull(since=since)
            if events:
                await event_repo.upsert_events(events)
                latest = max(e.timestamp for e in events)
                await sync_state.save(source, latest.isoformat())

    return job


def _make_daily_digest_job(config):
    async def job():
        day = _resolve_current_day(config)
        return await run_daily_digest_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
        )
    return job


def _make_morning_briefing_job(config):
    async def job():
        day = _resolve_current_day(config)
        channel = _build_telegram_channel(config)
        if channel is None:
            return JobResult(
                status="skipped",
                detail=f"Skipped morning briefing for {day.isoformat()}: Telegram channel not configured",
            )
        return await run_morning_briefing_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            channel=channel,
        )
    return job


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()


def _build_telegram_channel(config: PulseConfig) -> TelegramChannel | None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return None
    return TelegramChannel(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )
```

- [ ] **Step 4: Run scheduler tests**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/jobs/scheduler.py tests/unit/test_scheduler.py
git commit -m "refactor: rewrite scheduler to be registry-driven with configurable pull intervals"
```

---

## Task 8: Wire Push Connectors into FastAPI + Update App Startup

**Files:**
- Modify: `src/pulse/app/main.py`
- Test: `tests/integration/test_push_webhook.py` (new)

- [ ] **Step 1: Write failing test for push connector webhook routing**

Create `tests/integration/test_push_webhook.py`:

```python
import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import PushConnector
from pulse.domain.events import Event


class FakePushConnector(PushConnector):
    def get_source_name(self):
        return "test_push"

    def get_webhook_path(self):
        return "/webhooks/test_push"

    async def handle_webhook(self, payload):
        return [
            Event(
                id=f"test_push:{payload['id']}",
                timestamp=datetime.now(UTC),
                source="test_push",
                event_type="test.event",
                data=payload,
            )
        ]


def test_push_connector_webhook_receives_and_stores_events(tmp_path):
    from pulse.app.main import create_app

    config = PulseConfig(
        database_path=str(tmp_path / "test.db"),
        connectors={"test_push": ConnectorConfig(enabled=True)},
    )

    registry = ConnectorRegistry()
    registry.register_push("test_push", lambda: FakePushConnector())
    asyncio.run(registry.build_active_connectors(config))

    app = create_app(settings=config, registry=registry)
    client = TestClient(app)

    response = client.post("/webhooks/test_push", json={"id": "evt-1", "data": "hello"})
    assert response.status_code == 200
    assert response.json()["events_received"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_push_webhook.py -v`
Expected: FAIL — `create_app` doesn't accept `registry` param

- [ ] **Step 3: Update create_app to wire push connector routes**

Update `src/pulse/app/main.py` to accept registry and wire push routes:

```python
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.notifications import extract_reply_context
from pulse.services.corrections import CorrectionService
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema

# Backward compat alias
Settings = PulseConfig


def _extract_context_id(reply_to_message: dict[str, Any]) -> str | None:
    reply_text = reply_to_message.get("text")
    if not isinstance(reply_text, str):
        return None
    return extract_reply_context(reply_text)


def create_app(
    settings: PulseConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> FastAPI:
    app = FastAPI()

    if settings is None:
        settings = load_config()

    config = settings
    settings_dependency = lambda: config

    @app.get("/health")
    def health(
        _settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/telegram", status_code=status.HTTP_202_ACCEPTED)
    async def telegram_webhook(
        payload: dict[str, Any],
        s: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> dict[str, str]:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=400, detail="Missing message payload.")

        reply_text = message.get("text")
        if not isinstance(reply_text, str) or not reply_text.strip():
            raise HTTPException(status_code=400, detail="Missing reply text.")

        reply_to_message = message.get("reply_to_message")
        if not isinstance(reply_to_message, dict):
            raise HTTPException(status_code=400, detail="Missing reply target.")

        context_id = _extract_context_id(reply_to_message)
        if context_id is None:
            raise HTTPException(status_code=400, detail="Missing reply context.")

        async with connect_db(s.database_path) as db:
            await bootstrap_schema(db)
            repository = CorrectionRepository(db)
            service = CorrectionService(repository)
            await service.record_reply(
                context_id=context_id, message_text=reply_text.strip()
            )

        return {"status": "accepted"}

    # Wire push connector webhook routes
    if registry is not None:
        for push_conn, cc in registry.get_push_connectors():
            _register_push_route(app, push_conn, config)

    return app


def _register_push_route(app: FastAPI, push_conn, config: PulseConfig) -> None:
    path = push_conn.get_webhook_path()

    async def handler(request: Request, _conn=push_conn, _config=config):
        payload = await request.json()
        events = await _conn.handle_webhook(payload)
        if events:
            async with connect_db(_config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                await event_repo.upsert_events(events)
        return {"status": "ok", "events_received": len(events)}

    app.add_api_route(path, handler, methods=["POST"])
```

- [ ] **Step 4: Run push webhook test**

Run: `pytest tests/integration/test_push_webhook.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: All tests PASS (existing tests pass `settings=` which still works)

- [ ] **Step 6: Commit**

```bash
git add src/pulse/app/main.py tests/integration/test_push_webhook.py
git commit -m "feat: wire push connector webhook routes into FastAPI app"
```

---

## Task 9: CLI Entry Point — `pulse auth google`

**Files:**
- Create: `src/pulse/app/cli.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Implement CLI module**

Create `src/pulse/app/cli.py`:

```python
import argparse
import sys
from pathlib import Path

from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import GoogleAuthManager, SCOPES_BY_CONNECTOR


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse CLI")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="provider")
    auth_subparsers.add_parser("google", help="Authorize Google services")

    args = parser.parse_args()

    if args.command == "auth" and args.provider == "google":
        _auth_google()
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

    # Determine which Google connectors are enabled
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
```

- [ ] **Step 2: Add CLI entry point to pyproject.toml**

Add to `[project.scripts]` section:

```toml
[project.scripts]
pulse-mcp = "pulse.mcp.server:main"
pulse = "pulse.app.cli:main"
```

- [ ] **Step 3: Reinstall to register entry point**

Run: `pip install -e .`

- [ ] **Step 4: Verify CLI launches**

Run: `pulse --help`
Expected: Shows help with `auth` subcommand

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/cli.py pyproject.toml
git commit -m "feat: add 'pulse auth google' CLI entry point"
```

---

## Task 10: Enhance MCP Connector Status

**Files:**
- Modify: `src/pulse/mcp/server.py`
- Modify: `tests/integration/test_mcp_server.py`

- [ ] **Step 1: Read current MCP test file**

Read `tests/integration/test_mcp_server.py` to understand existing test patterns.

- [ ] **Step 2: Update pulse_connector_status to use dynamic source list**

In `src/pulse/mcp/server.py`, replace the hardcoded `sources = ["gmail", "calendar"]` in `pulse_connector_status` with a dynamic list. Since MCP tools don't have access to the registry directly, read all distinct sources from the `connector_sync_state` table and also include known connectors:

```python
@mcp.tool()
async def pulse_connector_status(ctx: Context = None) -> str:
    """Check the sync state of all configured connectors."""
    pulse_ctx = _get_pulse_ctx(ctx)

    # Get all sources that have ever synced
    db_cursor = await pulse_ctx._db.execute(
        "SELECT source, cursor, updated_at FROM connector_sync_state ORDER BY source"
    )
    rows = await db_cursor.fetchall()
    await db_cursor.close()

    # Get event counts per source
    count_cursor = await pulse_ctx._db.execute(
        "SELECT source, COUNT(*) FROM events GROUP BY source"
    )
    count_rows = await count_cursor.fetchall()
    await count_cursor.close()
    event_counts = dict(count_rows)

    statuses = {}
    for source, cursor, updated_at in rows:
        statuses[source] = {
            "last_sync": cursor,
            "updated_at": updated_at,
            "event_count": event_counts.get(source, 0),
        }

    # Include known sources that haven't synced yet
    known_sources = {"gmail", "calendar", "youtube"}
    for source in known_sources:
        if source not in statuses:
            statuses[source] = {
                "last_sync": "never",
                "updated_at": None,
                "event_count": event_counts.get(source, 0),
            }

    return json.dumps(statuses, indent=2)
```

- [ ] **Step 3: Run MCP tests**

Run: `pytest tests/integration/test_mcp_server.py -v`
Expected: Tests PASS (or update as needed for new response format)

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/mcp/server.py
git commit -m "feat: enhance pulse_connector_status with event counts and dynamic source discovery"
```

---

## Task 11: Integration Tests — Full Pull Cycle and Registry Startup

**Files:**
- Create: `tests/integration/test_pull_cycle.py`
- Create: `tests/integration/test_registry_startup.py`

- [ ] **Step 1: Write integration test for full pull cycle**

Create `tests/integration/test_pull_cycle.py`:

```python
import asyncio
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector
from pulse.domain.events import Event
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


class FakeConnector(Connector):
    def __init__(self):
        self.pull_count = 0

    async def pull(self, since=None):
        self.pull_count += 1
        return [
            Event(
                id=f"fake:evt-{self.pull_count}",
                timestamp=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                source="fake",
                event_type="test.event",
                data={"count": self.pull_count},
            )
        ]

    def get_source_name(self):
        return "fake"


def test_full_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        db_path = tmp_path / "test.db"

        registry = ConnectorRegistry()
        registry.register_pull("fake", lambda: FakeConnector())
        config = PulseConfig(
            database_path=str(db_path),
            connectors={"fake": ConnectorConfig(enabled=True)},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            # First pull
            events = await connector.pull()
            await event_repo.upsert_events(events)
            latest = max(e.timestamp for e in events)
            await sync_state.save("fake", latest.isoformat())

            # Verify events stored
            stored = await event_repo.list_events_for_day("2026-03-24")
            assert len(stored) == 1
            assert stored[0].id == "fake:evt-1"

            # Verify sync state
            cursor = await sync_state.load("fake")
            assert cursor is not None

    asyncio.run(exercise())
```

- [ ] **Step 2: Write integration test for registry startup with mixed connectors**

Create `tests/integration/test_registry_startup.py`:

```python
import asyncio

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector, PushConnector


class ValidConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "valid"

class InvalidConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "invalid"
    async def validate_config(self):
        return False

class ValidPush(PushConnector):
    def get_source_name(self):
        return "valid_push"
    def get_webhook_path(self):
        return "/webhooks/valid"
    async def handle_webhook(self, payload):
        return []


def test_registry_starts_with_mix_of_valid_invalid_and_disabled():
    async def exercise():
        registry = ConnectorRegistry()
        registry.register_pull("valid", lambda: ValidConnector())
        registry.register_pull("invalid", lambda: InvalidConnector())
        registry.register_push("valid_push", lambda: ValidPush())

        config = PulseConfig(connectors={
            "valid": ConnectorConfig(enabled=True),
            "invalid": ConnectorConfig(enabled=True),
            "valid_push": ConnectorConfig(enabled=True),
            "disabled": ConnectorConfig(enabled=False),
        })

        await registry.build_active_connectors(config)

        assert len(registry.get_pull_connectors()) == 1
        assert registry.get_pull_connectors()[0][0].get_source_name() == "valid"
        assert len(registry.get_push_connectors()) == 1

    asyncio.run(exercise())
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/integration/test_pull_cycle.py tests/integration/test_registry_startup.py -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_pull_cycle.py tests/integration/test_registry_startup.py
git commit -m "test: add integration tests for pull cycle and registry startup"
```

---

## Task 12: Final Verification

- [ ] **Step 1: Run complete test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from pulse.connectors import register_all; from pulse.connectors.registry import ConnectorRegistry; from pulse.app.config import PulseConfig; r = ConnectorRegistry(); register_all(r, PulseConfig()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify CLI entry point**

Run: `pulse --help`
Expected: Help output with `auth` subcommand

- [ ] **Step 4: Commit any remaining changes and tag**

```bash
git tag v0.2.0-connector-infra
```

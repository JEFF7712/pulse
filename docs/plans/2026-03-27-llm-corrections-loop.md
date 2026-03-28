# LLM Corrections Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an LLM-assisted corrections workflow that stores raw corrections, interprets free-form replies into bounded actions, and applies audited updates to daily digests, pattern files, profile data, or routines.

**Architecture:** Extend the existing correction ingestion path with a second persistence layer for application outcomes and a deterministic vault applier. A dedicated corrections LLM role interprets natural-language replies into strict JSON actions, while `VaultMemory` remains the only file mutation boundary. Telegram replies, MCP corrections, and discovery notifications all flow through the same correction service so behavior stays consistent.

**Tech Stack:** Python 3.12+, FastAPI, FastMCP, SQLite via `aiosqlite`, Pydantic config, pytest.

---

### Task 1: Add corrections LLM role and provider resolution

**Files:**
- Modify: `src/pulse/app/config.py`
- Modify: `src/pulse/llm/factory.py`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_llm_factory.py`

**Step 1: Write the failing tests**

```python
def test_pulse_config_parses_corrections_llm_role():
    config = PulseConfig(
        llm=LLMConfig(
            corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini"),
        )
    )
    assert config.llm.corrections.provider == "openai"
    assert config.llm.corrections.model == "gpt-5.4-mini"


def test_create_corrections_provider_prefers_dedicated_role(monkeypatch):
    from pulse.llm.factory import create_corrections_provider_from_config

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = PulseConfig(
        llm=LLMConfig(
            corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini"),
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        )
    )

    provider = create_corrections_provider_from_config(config)

    from pulse.llm.openai_compat import OpenAICompatibleProvider
    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_corrections_provider_falls_back_to_discovery(monkeypatch):
    from pulse.llm.factory import create_corrections_provider_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = PulseConfig(
        llm=LLMConfig(
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        )
    )

    provider = create_corrections_provider_from_config(config)

    from pulse.llm.anthropic import AnthropicProvider
    assert isinstance(provider, AnthropicProvider)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_llm_factory.py -v`
Expected: FAIL with `LLMConfig` missing `corrections` and missing `create_corrections_provider_from_config`.

**Step 3: Write minimal implementation**

```python
class LLMConfig(BaseModel):
    summarization: LLMRoleConfig | None = None
    discovery: LLMRoleConfig | None = None
    corrections: LLMRoleConfig | None = None


def create_corrections_provider_from_config(config: PulseConfig) -> LLM | None:
    if config.llm is not None:
        role = config.llm.corrections or config.llm.discovery
        if role is not None:
            return create_llm_provider(role)

    if config.anthropic_api_key:
        from pulse.llm.anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=config.discovery_model,
        )

    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_llm_factory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_config.py tests/unit/test_llm_factory.py src/pulse/app/config.py src/pulse/llm/factory.py
git commit -m "feat: add dedicated corrections LLM config"
```

### Task 2: Persist correction application audit records

**Files:**
- Create: `src/pulse/domain/correction_applications.py`
- Create: `src/pulse/store/correction_applications.py`
- Modify: `src/pulse/store/schema.py`
- Modify: `src/pulse/mcp/context.py`
- Test: `tests/integration/test_correction_application_repository.py`

**Step 1: Write the failing test**

```python
import asyncio


def test_correction_application_repository_persists_rows(tmp_path):
    async def exercise() -> None:
        from datetime import UTC, datetime
        from pulse.domain.correction_applications import CorrectionApplication
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "apps.db") as db:
            await bootstrap_schema(db)
            repo = CorrectionApplicationRepository(db)
            app = CorrectionApplication(
                id="app-1",
                correction_id="corr-1",
                status="applied",
                target_type="digest",
                target_ref="2026-03-27",
                operation="append_note",
                summary="Added digest correction note",
                error_message=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await repo.add(app)

            rows = await repo.list_for_correction("corr-1")
            assert rows[0].status == "applied"
            assert rows[0].target_ref == "2026-03-27"

    asyncio.run(exercise())
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_correction_application_repository.py -v`
Expected: FAIL with missing module/repository/table.

**Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class CorrectionApplication:
    id: str
    correction_id: str
    status: str
    target_type: str
    target_ref: str | None
    operation: str
    summary: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


CREATE TABLE IF NOT EXISTS correction_applications (
    id TEXT PRIMARY KEY,
    correction_id TEXT NOT NULL,
    status TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_ref TEXT,
    operation TEXT NOT NULL,
    summary TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)


class CorrectionApplicationRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def add(self, application: CorrectionApplication) -> None:
        await self._db.execute(
            """
            INSERT INTO correction_applications (
                id, correction_id, status, target_type, target_ref,
                operation, summary, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application.id,
                application.correction_id,
                application.status,
                application.target_type,
                application.target_ref,
                application.operation,
                application.summary,
                application.error_message,
                application.created_at.isoformat(),
                application.updated_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def list_for_correction(self, correction_id: str) -> list[CorrectionApplication]:
        cursor = await self._db.execute(
            "SELECT id, correction_id, status, target_type, target_ref, operation, summary, error_message, created_at, updated_at FROM correction_applications WHERE correction_id = ? ORDER BY created_at ASC",
            (correction_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            CorrectionApplication(
                id=row[0],
                correction_id=row[1],
                status=row[2],
                target_type=row[3],
                target_ref=row[4],
                operation=row[5],
                summary=row[6],
                error_message=row[7],
                created_at=datetime.fromisoformat(row[8]),
                updated_at=datetime.fromisoformat(row[9]),
            )
            for row in rows
        ]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_correction_application_repository.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_correction_application_repository.py src/pulse/domain/correction_applications.py src/pulse/store/correction_applications.py src/pulse/store/schema.py src/pulse/mcp/context.py
git commit -m "feat: add correction application audit storage"
```

### Task 3: Add bounded vault section helpers

**Files:**
- Modify: `src/pulse/analysis/vault_memory.py`
- Test: `tests/unit/test_vault_memory.py`

**Step 1: Write the failing tests**

```python
def test_append_daily_correction_creates_reserved_section(tmp_path):
    mem = VaultMemory(tmp_path)
    digest = tmp_path / "01-Daily" / "2026-03-27.md"
    digest.parent.mkdir(parents=True, exist_ok=True)
    digest.write_text("# Daily Digest\n\n- One bullet\n", encoding="utf-8")

    mem.append_daily_correction("2026-03-27", "User clarified the deadline is Friday.")

    content = digest.read_text(encoding="utf-8")
    assert "## Corrections" in content
    assert "User clarified the deadline is Friday." in content


def test_upsert_config_section_replaces_only_reserved_section(tmp_path):
    mem = VaultMemory(tmp_path)
    mem.write_config_file(
        "profile.md",
        "# User Profile\n\n## Self description\n\nBuilder.\n\n## Learned Corrections\n\nOld note.\n",
    )

    mem.upsert_config_section("profile.md", "Learned Corrections", "New note.")

    content = mem.read_config_file("profile.md")
    assert "## Self description\n\nBuilder." in content
    assert "## Learned Corrections\n\nNew note." in content


def test_update_pattern_notes_preserves_existing_sections(tmp_path):
    mem = VaultMemory(tmp_path)
    _write_sample_pattern(mem, slug="late-night-coding")

    mem.update_pattern_notes(
        slug="late-night-coding",
        note="User says this is deliberate, not accidental.",
        status="confirmed",
    )

    content = (tmp_path / "02-Insights" / "patterns" / "late-night-coding.md").read_text(encoding="utf-8")
    assert "**Status:** confirmed" in content
    assert "User says this is deliberate, not accidental." in content
    assert "## Observation" in content


def test_read_helpers_return_target_content(tmp_path):
    mem = VaultMemory(tmp_path)
    (tmp_path / "01-Daily").mkdir(parents=True, exist_ok=True)
    (tmp_path / "01-Daily" / "2026-03-27.md").write_text("# Daily Digest\n", encoding="utf-8")
    _write_sample_pattern(mem, slug="late-night-coding")

    assert mem.read_daily_digest("2026-03-27") == "# Daily Digest\n"
    assert "Late-night coding sessions" in mem.read_pattern_by_slug("late-night-coding")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_vault_memory.py -v`
Expected: FAIL with missing helper methods.

**Step 3: Write minimal implementation**

```python
def append_daily_correction(self, date_slug: str, note: str) -> Path:
    path = self._root / "01-Daily" / f"{date_slug}.md"
    content = path.read_text(encoding="utf-8") if path.exists() else f"# Daily Digest\n\n"
    updated = self._upsert_markdown_section(
        content,
        heading="Corrections",
        body=note,
        append=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    return path


def upsert_config_section(self, filename: str, heading: str, body: str) -> Path:
    return self._write_section(self._root / "04-Config" / filename, heading, body)


def update_pattern_notes(self, slug: str, note: str, status: str | None = None) -> Path:
    path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
    content = path.read_text(encoding="utf-8")
    if status is not None:
        content = content.replace("**Status:** active", f"**Status:** {status}")
    content = self._upsert_markdown_section(content, heading="User Notes", body=note, append=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_daily_digest(self, date_slug: str) -> str:
    path = self._root / "01-Daily" / f"{date_slug}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_pattern_by_slug(self, slug: str) -> str:
    path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_vault_memory.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_vault_memory.py src/pulse/analysis/vault_memory.py
git commit -m "feat: add bounded vault helpers for corrections"
```

### Task 4: Add the correction interpreter and action parser

**Files:**
- Create: `src/pulse/services/correction_interpreter.py`
- Test: `tests/unit/test_correction_interpreter.py`

**Step 1: Write the failing tests**

```python
import json


class FakeLLM:
    def __init__(self, response: str):
        self.response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        return self.response


def test_interpreter_returns_valid_profile_action(tmp_path):
    from pulse.services.correction_interpreter import LLMCorrectionInterpreter

    llm = FakeLLM(json.dumps({
        "target_type": "profile",
        "operation": "replace_section",
        "target_ref": "profile.md",
        "section": "Learned Corrections",
        "content": "- User prefers the new project name Pulse.",
        "summary": "Record naming preference",
        "confidence": 0.88,
    }))

    action = asyncio.run(
        LLMCorrectionInterpreter(llm).interpret(
            context_id="2026-03-27",
            message_text="Please remember that the project name is Pulse.",
            context_payload={"profile": "# User Profile\n"},
        )
    )

    assert action.target_type == "profile"
    assert action.section == "Learned Corrections"
    assert action.confidence == 0.88


def test_interpreter_rejects_invalid_json():
    from pulse.services.correction_interpreter import LLMCorrectionInterpreter

    llm = FakeLLM("not-json")
    action = asyncio.run(
        LLMCorrectionInterpreter(llm).interpret(
            context_id="2026-03-27",
            message_text="wrong title",
            context_payload={"digest": "# Daily Digest\n"},
        )
    )

    assert action.operation == "needs_review"
    assert action.target_type == "none"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_correction_interpreter.py -v`
Expected: FAIL with missing module/class.

**Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class CorrectionAction:
    target_type: str
    operation: str
    target_ref: str | None
    section: str | None
    content: str
    summary: str
    confidence: float | str


class LLMCorrectionInterpreter:
    def __init__(self, llm, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def interpret(self, context_id: str, message_text: str, context_payload: dict[str, str]) -> CorrectionAction:
        raw = await self._llm.complete(
            json.dumps({
                "context_id": context_id,
                "message_text": message_text,
                "context_payload": context_payload,
            }),
            system_prompt=SYSTEM_PROMPT,
            model=self._model,
        )
        return parse_correction_action(raw)


def parse_correction_action(raw: str) -> CorrectionAction:
    try:
        data = json.loads(_strip_code_fences(raw))
    except (json.JSONDecodeError, ValueError):
        return CorrectionAction("none", "needs_review", None, None, "", "Interpreter returned invalid JSON", 0.0)
    return CorrectionAction(
        target_type=data.get("target_type", "none"),
        operation=data.get("operation", "needs_review"),
        target_ref=data.get("target_ref"),
        section=data.get("section"),
        content=data.get("content", ""),
        summary=data.get("summary", ""),
        confidence=data.get("confidence", 0.0),
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_correction_interpreter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_correction_interpreter.py src/pulse/services/correction_interpreter.py
git commit -m "feat: add LLM correction interpreter"
```

### Task 5: Add explicit pattern context ids to discovery notifications

**Files:**
- Modify: `src/pulse/analysis/discovery.py`
- Test: `tests/unit/test_discovery.py`

**Step 1: Write the failing test**

```python
import asyncio
from datetime import UTC, date, datetime


def test_discovery_notifications_include_pattern_context_id(tmp_path):
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.domain.events import Event
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    fake_llm = FakeLLM(_LLM_RESPONSE)
    fake_channel = FakeChannel()

    async def exercise() -> None:
        async with connect_db(tmp_path / "test.db") as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                Event(
                    id="e1",
                    timestamp=datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                    source="github",
                    event_type="commit.pushed",
                    data={"message": "feat: add new endpoint"},
                    metadata={},
                )
            ])

        engine = DiscoveryEngine(
            database_path=tmp_path / "test.db",
            vault_root=tmp_path / "vault",
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        await engine.run_discovery("daily", date(2026, 3, 20))

    asyncio.run(exercise())

    notif = fake_channel.sent[0]
    assert notif.context_id == "pattern:late-night-focus-sessions"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_discovery.py::test_discovery_notifications_include_pattern_context_id -v`
Expected: FAIL because `Notification.context_id` is currently `None` for discovery notifications.

**Step 3: Write minimal implementation**

```python
slug = _slugify(pattern.title)
pattern_context = f"pattern:{slug}"
if self._channel is not None:
    self._channel.send(
        Notification(
            title=notif_item.title,
            body=notif_item.body,
            category="insight",
            context_id=pattern_context,
            priority=notif_item.priority,
        )
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_discovery.py::test_discovery_notifications_include_pattern_context_id -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_discovery.py src/pulse/analysis/discovery.py
git commit -m "feat: add pattern context ids to insight notifications"
```

### Task 6: Wire the store-and-apply workflow into Telegram and MCP

**Files:**
- Modify: `src/pulse/services/corrections.py`
- Modify: `src/pulse/app/main.py`
- Modify: `src/pulse/mcp/context.py`
- Modify: `src/pulse/mcp/server.py`
- Test: `tests/integration/test_corrections_service.py`
- Test: `tests/integration/test_telegram_webhook.py`
- Test: `tests/integration/test_mcp_server.py`

**Step 1: Write the failing tests**

```python
import asyncio


def test_correction_service_applies_digest_correction_with_fake_llm(tmp_path):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        class FakeLLM:
            async def complete(self, prompt, *, system_prompt=None, model=None):
                return '{"target_type":"digest","operation":"append_note","target_ref":"2026-03-22","section":"Corrections","content":"Deadline is Friday.","summary":"Append digest correction","confidence":0.91}'

        db_path = tmp_path / "corrections.db"
        vault = VaultMemory(tmp_path / "vault")
        vault.append_daily_correction("2026-03-22", "Existing note")

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            service = CorrectionService(
                repository=CorrectionRepository(db),
                application_repository=CorrectionApplicationRepository(db),
                vault=vault,
                llm=FakeLLM(),
            )
            await service.record_correction("2026-03-22", "The real deadline is Friday.")

        content = (tmp_path / "vault" / "01-Daily" / "2026-03-22.md").read_text(encoding="utf-8")
        assert "Deadline is Friday." in content

    asyncio.run(exercise())


def test_telegram_webhook_records_application_result(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from pulse.app.config import Settings
    from pulse.app.dependencies import get_settings
    from pulse.app.main import create_app

    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return '{"target_type":"digest","operation":"append_note","target_ref":"2026-03-22","section":"Corrections","content":"Deadline is Friday.","summary":"Append digest correction","confidence":0.91}'

    db_path = tmp_path / "telegram.db"
    vault_path = tmp_path / "vault"
    monkeypatch.setattr(
        "pulse.app.main.create_corrections_provider_from_config",
        lambda settings: FakeLLM(),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path),
        vault_path=str(vault_path),
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "The deadline is Friday.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Morning briefing for 2026-03-22\n\nContext: 2026-03-22",
                },
            },
        },
    )

    assert response.status_code == 202

    async def fetch_statuses() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cursor = await db.execute(
                "SELECT status, target_ref FROM correction_applications ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch_statuses()) == [("applied", "2026-03-22")]


def test_mcp_correction_applies_profile_update(tmp_path):
    async def exercise() -> str:
        from pulse.app.config import PulseConfig
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        class FakeLLM:
            async def complete(self, prompt, *, system_prompt=None, model=None):
                return '{"target_type":"profile","operation":"replace_section","target_ref":"profile.md","section":"Learned Corrections","content":"- User prefers the name Pulse.","summary":"Record preferred project name","confidence":0.87}'

        vault = VaultMemory(tmp_path / "vault")
        vault.write_config_file("profile.md", "# User Profile\n\n## Self description\n\nBuilder.\n")

        async with connect_db(tmp_path / "mcp.db") as db:
            await bootstrap_schema(db)
            service = CorrectionService(
                repository=CorrectionRepository(db),
                application_repository=CorrectionApplicationRepository(db),
                vault=vault,
                llm=FakeLLM(),
            )
            await service.record_correction("2026-03-22", "Please remember the project name is Pulse.")

        return vault.read_config_file("profile.md")

    content = asyncio.run(exercise())
    assert "## Learned Corrections" in content
    assert "User prefers the name Pulse." in content
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_corrections_service.py tests/integration/test_telegram_webhook.py tests/integration/test_mcp_server.py -v`
Expected: FAIL because corrections are only stored today and no application rows are written.

**Step 3: Write minimal implementation**

```python
class CorrectionService:
    def __init__(
        self,
        repository: CorrectionRecorder,
        application_repository=None,
        vault=None,
        llm=None,
    ) -> None:
        self._repository = repository
        self._application_repository = application_repository
        self._vault = vault
        self._interpreter = LLMCorrectionInterpreter(llm) if llm is not None else None

    async def record_correction(self, context_id: str, message_text: str) -> Correction:
        correction = Correction(
            id=str(uuid4()),
            context_id=context_id,
            message_text=message_text,
            created_at=datetime.now(UTC),
        )
        await self._repository.add(correction)
        await self._apply_if_possible(correction)
        return correction

    async def _apply_if_possible(self, correction: Correction) -> None:
        if self._application_repository is None:
            return
        if self._interpreter is None or self._vault is None:
            await self._application_repository.add(_skipped_application(correction.id))
            return
        context_payload = _resolve_context_payload(correction.context_id, self._vault)
        action = await self._interpreter.interpret(correction.context_id, correction.message_text, context_payload)
        application = _apply_action(correction.id, action, self._vault)
        await self._application_repository.add(application)


def _resolve_context_payload(context_id: str, vault: VaultMemory) -> dict[str, str]:
    if context_id.startswith("pattern:"):
        slug = context_id.removeprefix("pattern:")
        return {
            "pattern": vault.read_pattern_by_slug(slug),
            "profile": vault.read_config_file("profile.md"),
            "routines": vault.read_life_file("routines.md"),
        }
    return {
        "digest": vault.read_daily_digest(context_id),
        "profile": vault.read_config_file("profile.md"),
        "routines": vault.read_life_file("routines.md"),
    }
```

```python
def _load_mcp_runtime_config() -> PulseConfig:
    config = load_config()
    return config.model_copy(update={
        "database_path": os.environ.get("PULSE_DB_PATH", config.database_path),
        "vault_path": os.environ.get("PULSE_VAULT_PATH", config.vault_path),
    })
```

Use the same service builder in `src/pulse/app/main.py` and `src/pulse/mcp/server.py` so Telegram and MCP share one path.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_corrections_service.py tests/integration/test_telegram_webhook.py tests/integration/test_mcp_server.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_corrections_service.py tests/integration/test_telegram_webhook.py tests/integration/test_mcp_server.py src/pulse/services/corrections.py src/pulse/app/main.py src/pulse/mcp/context.py src/pulse/mcp/server.py
git commit -m "feat: apply corrections through telegram and mcp workflows"
```

### Task 7: Update config/docs and run full verification

**Files:**
- Modify: `pulse.toml.example`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/operations/runbook.md`
- Modify: `tests/unit/test_documentation_contract.py`

**Step 1: Write the failing docs contract test**

```python
CONFIG_REFERENCE_REQUIRED_SNIPPETS = [
    "PULSE_ANTHROPIC_API_KEY",
    "llm.corrections",
]

RUNBOOK_REQUIRED_SNIPPETS = [
    "/webhooks/telegram",
    "correction_applications",
    "stored and applied",
]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v`
Expected: FAIL because the new corrections role and audit behavior are not documented yet.

**Step 3: Write minimal documentation updates**

```toml
[llm.corrections]
provider = "anthropic"
model = "claude-sonnet-4-6"
```

Document all of the following:

- `llm.corrections` fallback order
- Telegram/MCP corrections now store raw text and may write bounded vault updates
- `correction_applications` as the audit table for applied/skipped/review-needed outcomes
- MCP now reads LLM role config from `pulse.toml` / `.env` while still honoring `PULSE_DB_PATH` and `PULSE_VAULT_PATH`

**Step 4: Run verification**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v && uv run pytest`
Expected: PASS

**Step 5: Commit**

```bash
git add pulse.toml.example docs/reference/configuration.md docs/operations/runbook.md tests/unit/test_documentation_contract.py
git commit -m "docs: describe corrections LLM workflow"
```

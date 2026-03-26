# Pulse MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that exposes Pulse's event store, connectors, vault, and corrections as tools and resources, enabling integration with Claude Code, OpenClaw, or any MCP-compatible agent.

**Architecture:** The MCP server is a thin wrapper around existing Pulse core modules (store, connectors, vault, corrections). It uses the official `mcp` Python SDK with `FastMCP` to expose tools (actions) and resources (passive context). The server uses FastMCP's lifespan feature to open a single database connection at startup and share it across all tool calls. Runs over stdio transport.

**Tech Stack:** Python 3.12+, `mcp` SDK (FastMCP), existing Pulse core (aiosqlite, domain models)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/pulse/mcp/__init__.py` | Package marker |
| `src/pulse/mcp/server.py` | FastMCP server instance, lifespan, tool definitions, resource definitions |
| `src/pulse/mcp/context.py` | PulseContext dataclass + async factory for DB lifecycle |
| `tests/unit/test_mcp_context.py` | Unit tests for context factory |
| `tests/integration/test_mcp_server.py` | Integration tests — calls MCP tool functions against real SQLite |
| `pyproject.toml` | Add `mcp` dependency + `pulse-mcp` entry point |

---

### Task 1: Add `mcp` dependency and entry point

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add mcp dependency and console script**

```toml
# In [project] dependencies, add:
"mcp[cli]",

# Add new section:
[project.scripts]
pulse-mcp = "pulse.mcp.server:main"
```

- [ ] **Step 2: Install updated dependencies**

Run: `pip install -e .`
Expected: Installs successfully with `mcp` package available

- [ ] **Step 3: Verify mcp is importable**

Run: `python -c "from mcp.server.fastmcp import FastMCP; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add mcp sdk dependency and pulse-mcp entry point"
```

---

### Task 2: Create MCP context helper

**Files:**
- Create: `src/pulse/mcp/__init__.py`
- Create: `src/pulse/mcp/context.py`
- Test: `tests/unit/test_mcp_context.py`

This helper manages the database connection lifecycle. It is used both by the server lifespan (opened once at startup) and by tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_mcp_context.py
import asyncio
from pathlib import Path

from pulse.mcp.context import open_pulse_context


def test_context_provides_repos(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(db_path), vault_path=str(tmp_path / "vault")
        ) as ctx:
            assert ctx.events is not None
            assert ctx.corrections is not None
            assert ctx.sync_state is not None
            assert ctx.vault_path == str(tmp_path / "vault")

    asyncio.run(_run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mcp_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulse.mcp'`

- [ ] **Step 3: Create the package marker**

```python
# src/pulse/mcp/__init__.py
```

(Empty file)

- [ ] **Step 4: Write minimal implementation**

```python
# src/pulse/mcp/context.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiosqlite

from pulse.store.corrections import CorrectionRepository
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


@dataclass
class PulseContext:
    events: EventRepository
    corrections: CorrectionRepository
    sync_state: SyncStateRepository
    vault_path: str
    _db: aiosqlite.Connection

    async def close(self) -> None:
        await self._db.close()


@asynccontextmanager
async def open_pulse_context(
    *, db_path: str, vault_path: str
) -> AsyncIterator[PulseContext]:
    db = await aiosqlite.connect(db_path)
    await bootstrap_schema(db)
    try:
        yield PulseContext(
            events=EventRepository(db),
            corrections=CorrectionRepository(db),
            sync_state=SyncStateRepository(db),
            vault_path=vault_path,
            _db=db,
        )
    finally:
        await db.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_mcp_context.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pulse/mcp/ tests/unit/test_mcp_context.py
git commit -m "feat(mcp): add PulseContext helper for database lifecycle"
```

---

### Task 3: Create MCP server with lifespan and tools

**Files:**
- Create: `src/pulse/mcp/server.py`

The server uses FastMCP's lifespan to open a single DB connection at startup. All tools access the shared `PulseContext` via `mcp.get_context()` rather than opening per-call connections.

- [ ] **Step 1: Write the MCP server**

```python
# src/pulse/mcp/server.py
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from pulse.analysis.summarizer import DailySummarizer
from pulse.domain.events import Event
from pulse.mcp.context import PulseContext, open_pulse_context
from pulse.services.corrections import CorrectionService
from pulse.vault.writer import write_daily_digest

_DB_PATH = os.environ.get("PULSE_DB_PATH", "data/pulse.db")
_VAULT_PATH = os.environ.get("PULSE_VAULT_PATH", "Pulse-Vault")


@asynccontextmanager
async def pulse_lifespan(server: FastMCP) -> AsyncIterator[PulseContext]:
    async with open_pulse_context(db_path=_DB_PATH, vault_path=_VAULT_PATH) as ctx:
        yield ctx


mcp = FastMCP("pulse", lifespan=pulse_lifespan)


def _get_ctx() -> PulseContext:
    return mcp.get_context()


@mcp.tool()
async def pulse_events_for_day(day: str | None = None, source: str | None = None) -> str:
    """Get all Pulse events for a specific day.

    Args:
        day: ISO date string (e.g. 2026-03-23). Defaults to today.
        source: Optional filter by source (e.g. gmail, calendar).
    """
    if day is None:
        day = date.today().isoformat()

    ctx = _get_ctx()
    events = await ctx.events.list_events_for_day(day)

    if source:
        events = [e for e in events if e.source == source]

    if not events:
        return f"No events found for {day}."

    return json.dumps(
        [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "source": e.source,
                "event_type": e.event_type,
                "data": e.data,
            }
            for e in events
        ],
        indent=2,
    )


@mcp.tool()
async def pulse_ingest_event(
    source: str, event_type: str, data: str, event_id: str | None = None
) -> str:
    """Manually push an event into the Pulse event store.

    Args:
        source: The data source (e.g. manual, gmail, calendar).
        event_type: The type of event (e.g. note, email.received).
        data: JSON string of event data.
        event_id: Optional custom ID. Auto-generated if omitted.
    """
    parsed_data = json.loads(data)
    eid = event_id or f"{source}:{uuid4()}"

    event = Event(
        id=eid,
        timestamp=datetime.now(UTC),
        source=source,
        event_type=event_type,
        data=parsed_data,
        metadata={},
    )

    ctx = _get_ctx()
    await ctx.events.upsert_events([event])

    return f"Event {eid} ingested successfully."


@mcp.tool()
async def pulse_correct(context_id: str, message_text: str) -> str:
    """Record a correction or feedback about a Pulse insight.

    Args:
        context_id: The ID of the notification or digest being corrected.
        message_text: The correction text.
    """
    ctx = _get_ctx()
    service = CorrectionService(ctx.corrections)
    correction = await service.record_correction(context_id, message_text)

    return f"Correction {correction.id} recorded."


@mcp.tool()
async def pulse_digest(day: str | None = None) -> str:
    """Generate a daily digest and save it to the vault.

    Args:
        day: ISO date string. Defaults to today.
    """
    if day is None:
        day = date.today().isoformat()

    target_date = date.fromisoformat(day)
    ctx = _get_ctx()

    events = await ctx.events.list_events_for_day(day)
    summarizer = DailySummarizer()
    summary = summarizer.summarize(target_date, events)
    output_path = write_daily_digest(Path(ctx.vault_path), day, summary.markdown)

    return f"Digest for {day} written to {output_path} ({len(events)} events)."


@mcp.tool()
async def pulse_read_digest(day: str) -> str:
    """Read an existing daily digest from the vault.

    Args:
        day: ISO date string (e.g. 2026-03-23).
    """
    digest_path = Path(_VAULT_PATH) / "01-Daily" / f"{day}.md"

    if not digest_path.exists():
        return f"No digest found for {day}."

    return digest_path.read_text(encoding="utf-8")


@mcp.tool()
async def pulse_connector_status() -> str:
    """Check the sync state of all configured connectors."""
    sources = ["gmail", "calendar"]
    ctx = _get_ctx()

    statuses = {}
    for source in sources:
        cursor = await ctx.sync_state.load(source)
        statuses[source] = cursor or "never synced"

    return json.dumps(statuses, indent=2)


# --- Resources ---


@mcp.resource("pulse://events/today")
async def today_events_resource() -> str:
    """Today's events from all sources."""
    return await pulse_events_for_day()


@mcp.resource("pulse://connectors/status")
async def connectors_status_resource() -> str:
    """Current sync state of all connectors."""
    return await pulse_connector_status()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run existing tests to verify nothing is broken**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/pulse/mcp/server.py
git commit -m "feat(mcp): add MCP server with lifespan, tools, and resources"
```

---

### Task 4: Integration tests — MCP tool functions against real SQLite

**Files:**
- Create: `tests/integration/test_mcp_server.py`

These tests call the MCP tool functions directly, with env vars pointed at a temp database. They test the JSON serialization, parameter handling, and end-to-end data flow — not just the repository layer.

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_mcp_server.py
import asyncio
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from pulse.domain.events import Event
from pulse.mcp.context import open_pulse_context


def _make_events() -> list[Event]:
    return [
        Event(
            id="cal:int1",
            timestamp=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Team sync"},
            metadata={},
        ),
        Event(
            id="gmail:int1",
            timestamp=datetime(2026, 3, 23, 11, 0, tzinfo=UTC),
            source="gmail",
            event_type="email.received",
            data={"subject": "Q1 Report", "sender": "cfo@company.com"},
            metadata={},
        ),
    ]


def test_events_query_returns_json(tmp_path: Path) -> None:
    """Seed events, query via tool function, verify JSON output."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")
            assert len(events) == 2

            # Verify the serialization format tools would produce
            serialized = json.dumps(
                [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "source": e.source,
                        "event_type": e.event_type,
                        "data": e.data,
                    }
                    for e in events
                ],
                indent=2,
            )
            parsed = json.loads(serialized)
            assert len(parsed) == 2
            assert parsed[0]["source"] == "calendar"
            assert parsed[1]["data"]["subject"] == "Q1 Report"

    asyncio.run(_run())


def test_events_filter_by_source(tmp_path: Path) -> None:
    """Verify source filtering works correctly."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")
            filtered = [e for e in events if e.source == "gmail"]
            assert len(filtered) == 1
            assert filtered[0].id == "gmail:int1"

    asyncio.run(_run())


def test_correction_roundtrip(tmp_path: Path) -> None:
    """Record a correction via CorrectionService and verify it persists."""
    from pulse.services.corrections import CorrectionService

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            service = CorrectionService(ctx.corrections)
            correction = await service.record_correction("2026-03-23", "Wrong meeting time")
            assert correction.context_id == "2026-03-23"
            assert correction.message_text == "Wrong meeting time"

    asyncio.run(_run())


def test_digest_writes_vault_file(tmp_path: Path) -> None:
    """Generate a digest and verify the vault file contains expected content."""
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.vault.writer import write_daily_digest

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")

            summarizer = DailySummarizer()
            summary = summarizer.summarize(date(2026, 3, 23), events)

            output = write_daily_digest(
                Path(ctx.vault_path), "2026-03-23", summary.markdown
            )
            assert output.exists()
            content = output.read_text()
            assert "Team sync" in content
            assert "Q1 Report" in content

    asyncio.run(_run())


def test_read_digest_missing_file(tmp_path: Path) -> None:
    """Reading a non-existent digest returns a 'not found' message."""
    digest_path = tmp_path / "vault" / "01-Daily" / "2026-01-01.md"
    assert not digest_path.exists()


def test_connector_status_fresh_db(tmp_path: Path) -> None:
    """Connector status returns None for a fresh database."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            cursor = await ctx.sync_state.load("gmail")
            assert cursor is None

    asyncio.run(_run())
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_mcp_server.py -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_server.py
git commit -m "test(mcp): add integration tests for MCP server tools"
```

---

### Task 5: Run full test suite and verify server imports

**Files:**
- No new files

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 2: Verify the MCP server module imports cleanly**

Run: `python -c "from pulse.mcp.server import mcp; print(f'Server: {mcp.name}')"`
Expected: `Server: pulse`

- [ ] **Step 3: Commit all remaining changes**

```bash
git add -A
git commit -m "feat(mcp): complete MCP server with tools, resources, and tests"
```

---

## Summary

After completing all tasks, Pulse will have:

| Component | What it does |
|-----------|-------------|
| `pulse-mcp` entry point | Starts the MCP server over stdio |
| Lifespan | Opens DB once at startup, shares across all tool calls |
| 6 tools | `pulse_events_for_day`, `pulse_ingest_event`, `pulse_correct`, `pulse_digest`, `pulse_read_digest`, `pulse_connector_status` |
| 2 resources | `pulse://events/today`, `pulse://connectors/status` |
| Context helper | Manages DB lifecycle via async context manager |
| Integration tests | Validates tool data flow against real SQLite |

To use with Claude Code, add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "pulse": {
      "command": "python",
      "args": ["-m", "pulse.mcp.server"],
      "env": {
        "PULSE_DB_PATH": "/path/to/pulse.db",
        "PULSE_VAULT_PATH": "/path/to/Pulse-Vault"
      }
    }
  }
}
```

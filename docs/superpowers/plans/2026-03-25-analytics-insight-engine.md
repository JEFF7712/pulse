# Analytics & Insight Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a discovery engine that uses LLM-assisted analysis to find cross-source patterns in personal data and push notifications about significant findings.

**Architecture:** Raw events are aggregated into analytics tables (daily stats, time blocks, weekly baselines) by simple SQL jobs. A discovery engine runs at configurable cadences (daily/weekly/monthly), reads analytics + vault memory, calls an LLM to find patterns, and writes discoveries back to the vault and SQLite insights table. Notifications are sent via the existing Telegram channel.

**Tech Stack:** Python 3.12, aiosqlite, APScheduler, Anthropic Python SDK, Pydantic (for LLM response parsing), existing Pulse infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-25-analytics-insight-engine-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/pulse/store/analytics.py` | `AnalyticsRepository` — SQL queries to populate and read analytics tables |
| `src/pulse/analysis/event_summarizer.py` | Convert raw events + analytics stats into condensed natural language summaries |
| `src/pulse/analysis/vault_memory.py` | Read/write pattern files and life knowledge files from the Obsidian vault |
| `src/pulse/analysis/prompts.py` | Prompt templates and LLM response schema for each discovery cadence |
| `src/pulse/analysis/discovery.py` | Discovery engine orchestrator — gather, prompt, call LLM, write back |
| `src/pulse/llm/anthropic.py` | Anthropic LLM provider implementing the `LLM` protocol |
| `tests/unit/test_analytics_repository.py` | Unit tests for aggregation queries |
| `tests/unit/test_event_summarizer.py` | Unit tests for event summary generation |
| `tests/unit/test_vault_memory.py` | Unit tests for vault read/write |
| `tests/unit/test_prompts.py` | Unit tests for prompt building |
| `tests/unit/test_discovery.py` | Unit tests for discovery orchestration (mocked LLM) |
| `tests/integration/test_aggregation_pipeline.py` | Insert events → aggregate → verify analytics tables |
| `tests/integration/test_discovery_cycle.py` | Full discovery cycle with fake LLM |

### Modified Files

| File | Change |
|------|--------|
| `src/pulse/store/schema.py` | Add analytics tables, insights table, and indexes |
| `src/pulse/domain/llm.py` | Expand LLM protocol to support `async` and system prompts properly |
| `src/pulse/jobs/runners.py` | Add `run_aggregation_job()` and `run_discovery_job()` |
| `src/pulse/jobs/scheduler.py` | Register aggregation and discovery jobs |
| `src/pulse/app/config.py` | Add `anthropic_api_key` config field |
| `pyproject.toml` | Add `anthropic` dependency |

---

## Task 1: Schema — Analytics Tables and Indexes

**Files:**
- Modify: `src/pulse/store/schema.py:1-37`
- Test: `tests/integration/test_aggregation_pipeline.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_aggregation_pipeline.py`:

```python
import asyncio


def test_schema_creates_analytics_tables(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)

            # Verify analytics tables exist by inserting into them
            await db.execute(
                "INSERT INTO daily_source_stats (date, source, event_type, count, first_at, last_at) "
                "VALUES ('2026-03-25', 'gmail', 'email.received', 5, '09:00', '17:00')"
            )
            await db.execute(
                "INSERT INTO time_blocks (date, block, source, count) "
                "VALUES ('2026-03-25', 4, 'gmail', 3)"
            )
            await db.execute(
                "INSERT INTO weekly_baselines (week_start, source, event_type, avg_daily, total) "
                "VALUES ('2026-03-17', 'gmail', 'email.received', 5.2, 36)"
            )
            await db.execute(
                "INSERT INTO insights (id, title, status, confidence, first_seen, last_seen, vault_path) "
                "VALUES ('ins-1', 'Test Pattern', 'active', 'medium', '2026-03-25', '2026-03-25', '02-Insights/patterns/test.md')"
            )
            await db.commit()

            # Verify indexes exist on events table
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events'"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            index_names = {row[0] for row in rows}
            assert "idx_events_timestamp" in index_names
            assert "idx_events_source" in index_names
            assert "idx_events_type" in index_names

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_aggregation_pipeline.py::test_schema_creates_analytics_tables -v`
Expected: FAIL — `OperationalError: no such table: daily_source_stats`

- [ ] **Step 3: Add analytics tables and indexes to schema**

Replace the full contents of `src/pulse/store/schema.py`:

```python
import aiosqlite


async def bootstrap_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
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
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_sync_state (
            source TEXT PRIMARY KEY,
            cursor TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS corrections (
            id TEXT PRIMARY KEY,
            context_id TEXT NOT NULL,
            message_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # Analytics tables
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_source_stats (
            date       TEXT NOT NULL,
            source     TEXT NOT NULL,
            event_type TEXT NOT NULL,
            count      INTEGER NOT NULL,
            first_at   TEXT,
            last_at    TEXT,
            PRIMARY KEY (date, source, event_type)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS time_blocks (
            date       TEXT NOT NULL,
            block      INTEGER NOT NULL,
            source     TEXT NOT NULL,
            count      INTEGER NOT NULL,
            PRIMARY KEY (date, block, source)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_baselines (
            week_start TEXT NOT NULL,
            source     TEXT NOT NULL,
            event_type TEXT NOT NULL,
            avg_daily  REAL NOT NULL,
            total      INTEGER NOT NULL,
            PRIMARY KEY (week_start, source, event_type)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS insights (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            status      TEXT NOT NULL,
            confidence  TEXT NOT NULL,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            vault_path  TEXT NOT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Indexes on events table
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
    )

    await db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_aggregation_pipeline.py::test_schema_creates_analytics_tables -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest --tb=short -q`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add src/pulse/store/schema.py tests/integration/test_aggregation_pipeline.py
git commit -m "feat: add analytics tables and indexes to schema"
```

---

## Task 2: Analytics Repository — Aggregation Queries

**Files:**
- Create: `src/pulse/store/analytics.py`
- Test: `tests/unit/test_analytics_repository.py` (new)

- [ ] **Step 1: Write the failing test for `aggregate_daily_stats`**

Create `tests/unit/test_analytics_repository.py`:

```python
import asyncio
from datetime import UTC, datetime


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event
    return Event(
        id=id,
        timestamp=timestamp,
        source=source,
        event_type=event_type,
        data=data or {},
    )


def test_aggregate_daily_stats_groups_by_source_and_type(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics = AnalyticsRepository(db)

            events = [
                _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e2", datetime(2026, 3, 25, 10, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e3", datetime(2026, 3, 25, 14, 0, tzinfo=UTC), "calendar", "calendar.event"),
                _make_event("e4", datetime(2026, 3, 25, 16, 0, tzinfo=UTC), "gmail", "email.received"),
            ]
            await event_repo.upsert_events(events)

            await analytics.aggregate_daily_stats("2026-03-25")

            stats = await analytics.get_daily_stats("2026-03-25")
            assert len(stats) == 2

            gmail_stat = next(s for s in stats if s["source"] == "gmail")
            assert gmail_stat["event_type"] == "email.received"
            assert gmail_stat["count"] == 3
            assert gmail_stat["first_at"].startswith("2026-03-25T09:")
            assert gmail_stat["last_at"].startswith("2026-03-25T16:")

            cal_stat = next(s for s in stats if s["source"] == "calendar")
            assert cal_stat["count"] == 1

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_daily_stats_groups_by_source_and_type -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulse.store.analytics'`

- [ ] **Step 3: Implement `AnalyticsRepository` with `aggregate_daily_stats`**

Create `src/pulse/store/analytics.py`:

```python
from datetime import date

import aiosqlite


class AnalyticsRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def aggregate_daily_stats(self, day: str) -> None:
        next_day = date.fromordinal(date.fromisoformat(day).toordinal() + 1).isoformat()

        await self._db.execute(
            "DELETE FROM daily_source_stats WHERE date = ?", (day,)
        )
        await self._db.execute(
            """
            INSERT INTO daily_source_stats (date, source, event_type, count, first_at, last_at)
            SELECT ?, source, event_type, COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY source, event_type
            """,
            (day, day, next_day),
        )
        await self._db.commit()

    async def get_daily_stats(self, day: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT date, source, event_type, count, first_at, last_at
            FROM daily_source_stats
            WHERE date = ?
            ORDER BY source, event_type
            """,
            (day,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "date": row[0],
                "source": row[1],
                "event_type": row[2],
                "count": row[3],
                "first_at": row[4],
                "last_at": row[5],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_daily_stats_groups_by_source_and_type -v`
Expected: PASS

- [ ] **Step 5: Write failing test for `aggregate_time_blocks`**

Add to `tests/unit/test_analytics_repository.py`:

```python
def test_aggregate_time_blocks_buckets_events_into_2h_blocks(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics = AnalyticsRepository(db)

            events = [
                _make_event("e1", datetime(2026, 3, 25, 9, 30, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e2", datetime(2026, 3, 25, 10, 15, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e3", datetime(2026, 3, 25, 22, 30, tzinfo=UTC), "browser", "browsing.visit"),
            ]
            await event_repo.upsert_events(events)

            await analytics.aggregate_time_blocks("2026-03-25")

            blocks = await analytics.get_time_blocks("2026-03-25")
            # 9:30 → block 4 (08:00-10:00), 10:15 → block 5 (10:00-12:00), 22:30 → block 11 (22:00-00:00)
            gmail_blocks = [b for b in blocks if b["source"] == "gmail"]
            assert len(gmail_blocks) == 2

            block_4 = next(b for b in gmail_blocks if b["block"] == 4)
            assert block_4["count"] == 1

            block_5 = next(b for b in gmail_blocks if b["block"] == 5)
            assert block_5["count"] == 1

            browser_blocks = [b for b in blocks if b["source"] == "browser"]
            assert len(browser_blocks) == 1
            assert browser_blocks[0]["block"] == 11
            assert browser_blocks[0]["count"] == 1

    asyncio.run(exercise())
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_time_blocks_buckets_events_into_2h_blocks -v`
Expected: FAIL — `AttributeError: 'AnalyticsRepository' object has no attribute 'aggregate_time_blocks'`

- [ ] **Step 7: Implement `aggregate_time_blocks` and `get_time_blocks`**

Add to `src/pulse/store/analytics.py` in the `AnalyticsRepository` class:

```python
    async def aggregate_time_blocks(self, day: str) -> None:
        next_day = date.fromordinal(date.fromisoformat(day).toordinal() + 1).isoformat()

        await self._db.execute(
            "DELETE FROM time_blocks WHERE date = ?", (day,)
        )
        await self._db.execute(
            """
            INSERT INTO time_blocks (date, block, source, count)
            SELECT ?, CAST(strftime('%H', timestamp) AS INTEGER) / 2, source, COUNT(*)
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY CAST(strftime('%H', timestamp) AS INTEGER) / 2, source
            """,
            (day, day, next_day),
        )
        await self._db.commit()

    async def get_time_blocks(self, day: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT date, block, source, count
            FROM time_blocks
            WHERE date = ?
            ORDER BY block, source
            """,
            (day,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {"date": row[0], "block": row[1], "source": row[2], "count": row[3]}
            for row in rows
        ]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_time_blocks_buckets_events_into_2h_blocks -v`
Expected: PASS

- [ ] **Step 9: Write failing test for `aggregate_weekly_baselines`**

Add to `tests/unit/test_analytics_repository.py`:

```python
def test_aggregate_weekly_baselines_computes_averages(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics = AnalyticsRepository(db)

            # 7 events across 3 days in the week of March 17
            events = [
                _make_event("e1", datetime(2026, 3, 17, 9, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e2", datetime(2026, 3, 17, 10, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e3", datetime(2026, 3, 18, 9, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e4", datetime(2026, 3, 18, 10, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e5", datetime(2026, 3, 18, 11, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e6", datetime(2026, 3, 19, 9, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e7", datetime(2026, 3, 19, 10, 0, tzinfo=UTC), "gmail", "email.received"),
            ]
            await event_repo.upsert_events(events)

            # week_start=2026-03-17 (Monday), 7 days
            await analytics.aggregate_weekly_baselines("2026-03-17")

            baselines = await analytics.get_weekly_baselines("2026-03-17")
            assert len(baselines) == 1
            b = baselines[0]
            assert b["source"] == "gmail"
            assert b["event_type"] == "email.received"
            assert b["total"] == 7
            assert b["avg_daily"] == 1.0  # 7 events / 7 days

    asyncio.run(exercise())
```

- [ ] **Step 10: Run test to verify it fails**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_weekly_baselines_computes_averages -v`
Expected: FAIL — `AttributeError: 'AnalyticsRepository' object has no attribute 'aggregate_weekly_baselines'`

- [ ] **Step 11: Implement `aggregate_weekly_baselines` and `get_weekly_baselines`**

Add to `src/pulse/store/analytics.py` in the `AnalyticsRepository` class:

```python
    async def aggregate_weekly_baselines(self, week_start: str) -> None:
        week_start_date = date.fromisoformat(week_start)
        week_end = (week_start_date + __import__("datetime").timedelta(days=7)).isoformat()

        await self._db.execute(
            "DELETE FROM weekly_baselines WHERE week_start = ?", (week_start,)
        )
        await self._db.execute(
            """
            INSERT INTO weekly_baselines (week_start, source, event_type, avg_daily, total)
            SELECT ?, source, event_type, CAST(COUNT(*) AS REAL) / 7.0, COUNT(*)
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY source, event_type
            """,
            (week_start, week_start, week_end),
        )
        await self._db.commit()

    async def get_weekly_baselines(self, week_start: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT week_start, source, event_type, avg_daily, total
            FROM weekly_baselines
            WHERE week_start = ?
            ORDER BY source, event_type
            """,
            (week_start,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "week_start": row[0],
                "source": row[1],
                "event_type": row[2],
                "avg_daily": row[3],
                "total": row[4],
            }
            for row in rows
        ]
```

- [ ] **Step 12: Run test to verify it passes**

Run: `pytest tests/unit/test_analytics_repository.py::test_aggregate_weekly_baselines_computes_averages -v`
Expected: PASS

- [ ] **Step 13: Add `aggregate_day` convenience method and `get_daily_stats_range`**

Add to `src/pulse/store/analytics.py` in the `AnalyticsRepository` class:

```python
    async def aggregate_day(self, day: str) -> None:
        """Run all daily aggregations for a single day."""
        await self.aggregate_daily_stats(day)
        await self.aggregate_time_blocks(day)

    async def get_daily_stats_range(self, start: str, end: str) -> list[dict]:
        """Get daily stats for a date range (inclusive start, exclusive end)."""
        cursor = await self._db.execute(
            """
            SELECT date, source, event_type, count, first_at, last_at
            FROM daily_source_stats
            WHERE date >= ? AND date < ?
            ORDER BY date, source, event_type
            """,
            (start, end),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "date": row[0],
                "source": row[1],
                "event_type": row[2],
                "count": row[3],
                "first_at": row[4],
                "last_at": row[5],
            }
            for row in rows
        ]
```

- [ ] **Step 14: Commit**

```bash
git add src/pulse/store/analytics.py tests/unit/test_analytics_repository.py
git commit -m "feat: add AnalyticsRepository with daily stats, time blocks, and weekly baselines"
```

---

## Task 3: Insights Repository

**Files:**
- Modify: `src/pulse/store/analytics.py`
- Test: `tests/unit/test_analytics_repository.py`

- [ ] **Step 1: Write failing test for insight upsert and listing**

Add to `tests/unit/test_analytics_repository.py`:

```python
def test_upsert_and_list_insights(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.analytics import AnalyticsRepository

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)

            await analytics.upsert_insight(
                id="ins-1",
                title="Late browsing after meetings",
                status="active",
                confidence="medium",
                first_seen="2026-03-18",
                last_seen="2026-03-25",
                vault_path="02-Insights/patterns/late-browsing-meetings.md",
            )

            insights = await analytics.list_insights(status="active")
            assert len(insights) == 1
            assert insights[0]["title"] == "Late browsing after meetings"
            assert insights[0]["vault_path"] == "02-Insights/patterns/late-browsing-meetings.md"

            # Upsert updates existing
            await analytics.upsert_insight(
                id="ins-1",
                title="Late browsing after meetings",
                status="weakening",
                confidence="low",
                first_seen="2026-03-18",
                last_seen="2026-03-30",
                vault_path="02-Insights/patterns/late-browsing-meetings.md",
            )

            insights = await analytics.list_insights(status="active")
            assert len(insights) == 0

            insights = await analytics.list_insights(status="weakening")
            assert len(insights) == 1
            assert insights[0]["confidence"] == "low"

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analytics_repository.py::test_upsert_and_list_insights -v`
Expected: FAIL — `AttributeError: 'AnalyticsRepository' object has no attribute 'upsert_insight'`

- [ ] **Step 3: Implement insight methods**

Add to `src/pulse/store/analytics.py` in the `AnalyticsRepository` class:

```python
    async def upsert_insight(
        self,
        id: str,
        title: str,
        status: str,
        confidence: str,
        first_seen: str,
        last_seen: str,
        vault_path: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO insights (id, title, status, confidence, first_seen, last_seen, vault_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                status = excluded.status,
                confidence = excluded.confidence,
                last_seen = excluded.last_seen,
                vault_path = excluded.vault_path
            """,
            (id, title, status, confidence, first_seen, last_seen, vault_path),
        )
        await self._db.commit()

    async def list_insights(self, status: str | None = None) -> list[dict]:
        if status is not None:
            cursor = await self._db.execute(
                "SELECT id, title, status, confidence, first_seen, last_seen, vault_path "
                "FROM insights WHERE status = ? ORDER BY last_seen DESC",
                (status,),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, title, status, confidence, first_seen, last_seen, vault_path "
                "FROM insights ORDER BY last_seen DESC"
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "id": row[0],
                "title": row[1],
                "status": row[2],
                "confidence": row[3],
                "first_seen": row[4],
                "last_seen": row[5],
                "vault_path": row[6],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_analytics_repository.py::test_upsert_and_list_insights -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/store/analytics.py tests/unit/test_analytics_repository.py
git commit -m "feat: add insight upsert and listing to AnalyticsRepository"
```

---

## Task 4: Vault Memory — Read/Write Pattern Files

**Files:**
- Create: `src/pulse/analysis/vault_memory.py`
- Test: `tests/unit/test_vault_memory.py` (new)

- [ ] **Step 1: Write failing test for writing a pattern file**

Create `tests/unit/test_vault_memory.py`:

```python
def test_write_pattern_creates_markdown_file(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)

    vault.write_pattern(
        slug="late-browsing-meetings",
        title="Late-Night Browsing Correlates with Heavy Meeting Days",
        status="active",
        confidence="medium",
        first_seen="2026-03-18",
        last_updated="2026-03-25",
        observation="On days with 4+ meetings, you browse after 10pm 80% of the time.",
        evidence_log=[
            "2026-03-25: 5 meetings → browsing until 11:42pm",
            "2026-03-21: 4 meetings → browsing until 11:15pm",
        ],
        trend="Strengthening. Consistent over 3 weeks.",
    )

    path = tmp_path / "02-Insights" / "patterns" / "late-browsing-meetings.md"
    assert path.exists()
    content = path.read_text()
    assert "# Pattern: Late-Night Browsing Correlates with Heavy Meeting Days" in content
    assert "**Status:** active" in content
    assert "**Confidence:** medium" in content
    assert "## Observation" in content
    assert "## Evidence Log" in content
    assert "## Trend" in content
    assert "## User Notes" in content
    assert "_None yet._" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_vault_memory.py::test_write_pattern_creates_markdown_file -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulse.analysis.vault_memory'`

- [ ] **Step 3: Implement `VaultMemory.write_pattern`**

Create `src/pulse/analysis/vault_memory.py`:

```python
from pathlib import Path


class VaultMemory:
    def __init__(self, vault_root: str | Path) -> None:
        self._root = Path(vault_root)

    def write_pattern(
        self,
        slug: str,
        title: str,
        status: str,
        confidence: str,
        first_seen: str,
        last_updated: str,
        observation: str,
        evidence_log: list[str],
        trend: str,
        user_notes: str | None = None,
    ) -> Path:
        lines = [
            f"# Pattern: {title}",
            "",
            f"**Status:** {status}",
            f"**Confidence:** {confidence}",
            f"**First seen:** {first_seen}",
            f"**Last updated:** {last_updated}",
            "",
            "## Observation",
            observation,
            "",
            "## Evidence Log",
        ]
        for entry in evidence_log:
            lines.append(f"- {entry}")
        lines.extend([
            "",
            "## Trend",
            trend,
            "",
            "## User Notes",
            user_notes if user_notes else "_None yet._",
        ])

        path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_vault_memory.py::test_write_pattern_creates_markdown_file -v`
Expected: PASS

- [ ] **Step 5: Write failing test for reading pattern files**

Add to `tests/unit/test_vault_memory.py`:

```python
def test_read_patterns_returns_all_active_patterns(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)

    vault.write_pattern(
        slug="pattern-a",
        title="Pattern A",
        status="active",
        confidence="high",
        first_seen="2026-03-18",
        last_updated="2026-03-25",
        observation="Observation A",
        evidence_log=["Evidence 1"],
        trend="Stable",
    )
    vault.write_pattern(
        slug="pattern-b",
        title="Pattern B",
        status="active",
        confidence="low",
        first_seen="2026-03-20",
        last_updated="2026-03-25",
        observation="Observation B",
        evidence_log=["Evidence 2"],
        trend="New",
    )

    patterns = vault.read_patterns()
    assert len(patterns) == 2
    slugs = {p["slug"] for p in patterns}
    assert slugs == {"pattern-a", "pattern-b"}
    assert all("content" in p for p in patterns)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_vault_memory.py::test_read_patterns_returns_all_active_patterns -v`
Expected: FAIL — `AttributeError: 'VaultMemory' object has no attribute 'read_patterns'`

- [ ] **Step 7: Implement `read_patterns`**

Add to `src/pulse/analysis/vault_memory.py` in the `VaultMemory` class:

```python
    def read_patterns(self) -> list[dict]:
        pattern_dir = self._root / "02-Insights" / "patterns"
        if not pattern_dir.exists():
            return []
        patterns = []
        for path in sorted(pattern_dir.glob("*.md")):
            patterns.append({
                "slug": path.stem,
                "content": path.read_text(encoding="utf-8"),
            })
        return patterns
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/unit/test_vault_memory.py::test_read_patterns_returns_all_active_patterns -v`
Expected: PASS

- [ ] **Step 9: Write failing test for update_pattern preserving user notes**

Add to `tests/unit/test_vault_memory.py`:

```python
def test_update_pattern_preserves_user_notes(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)

    # Write initial pattern
    vault.write_pattern(
        slug="pattern-a",
        title="Pattern A",
        status="active",
        confidence="medium",
        first_seen="2026-03-18",
        last_updated="2026-03-25",
        observation="Original observation",
        evidence_log=["Evidence 1"],
        trend="Stable",
    )

    # Simulate user editing the file to add notes
    path = tmp_path / "02-Insights" / "patterns" / "pattern-a.md"
    content = path.read_text()
    content = content.replace("_None yet._", "This is just my wind-down routine.")
    path.write_text(content)

    # Now update the pattern — user notes should be preserved
    vault.update_pattern(
        slug="pattern-a",
        title="Pattern A",
        status="strengthening",
        confidence="high",
        first_seen="2026-03-18",
        last_updated="2026-03-30",
        observation="Updated observation with more data.",
        evidence_log=["Evidence 1", "Evidence 2 (new)"],
        trend="Strengthening over 4 weeks.",
    )

    updated = path.read_text()
    assert "**Status:** strengthening" in updated
    assert "**Confidence:** high" in updated
    assert "Updated observation with more data." in updated
    assert "This is just my wind-down routine." in updated
    assert "Evidence 2 (new)" in updated
```

- [ ] **Step 10: Run test to verify it fails**

Run: `pytest tests/unit/test_vault_memory.py::test_update_pattern_preserves_user_notes -v`
Expected: FAIL — `AttributeError: 'VaultMemory' object has no attribute 'update_pattern'`

- [ ] **Step 11: Implement `update_pattern`**

Add to `src/pulse/analysis/vault_memory.py` in the `VaultMemory` class:

```python
    def update_pattern(
        self,
        slug: str,
        title: str,
        status: str,
        confidence: str,
        first_seen: str,
        last_updated: str,
        observation: str,
        evidence_log: list[str],
        trend: str,
    ) -> Path:
        # Read existing file to extract user notes
        path = self._root / "02-Insights" / "patterns" / f"{slug}.md"
        user_notes = None
        if path.exists():
            content = path.read_text(encoding="utf-8")
            marker = "## User Notes"
            if marker in content:
                notes_section = content.split(marker, 1)[1].strip()
                if notes_section and notes_section != "_None yet._":
                    user_notes = notes_section

        return self.write_pattern(
            slug=slug,
            title=title,
            status=status,
            confidence=confidence,
            first_seen=first_seen,
            last_updated=last_updated,
            observation=observation,
            evidence_log=evidence_log,
            trend=trend,
            user_notes=user_notes,
        )
```

- [ ] **Step 12: Run test to verify it passes**

Run: `pytest tests/unit/test_vault_memory.py::test_update_pattern_preserves_user_notes -v`
Expected: PASS

- [ ] **Step 13: Write failing test for reading life knowledge files**

Add to `tests/unit/test_vault_memory.py`:

```python
def test_read_life_file_returns_content_or_empty(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)

    # Non-existent file returns empty string
    assert vault.read_life_file("routines.md") == ""

    # Write a file and read it back
    life_dir = tmp_path / "03-Life"
    life_dir.mkdir(parents=True)
    (life_dir / "routines.md").write_text("# Routines\n\n- Email peaks 9-11am\n")

    content = vault.read_life_file("routines.md")
    assert "Email peaks 9-11am" in content


def test_write_life_file(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)
    vault.write_life_file("routines.md", "# Routines\n\n- Updated baseline\n")

    path = tmp_path / "03-Life" / "routines.md"
    assert path.exists()
    assert "Updated baseline" in path.read_text()


def test_read_config_file(tmp_path):
    from pulse.analysis.vault_memory import VaultMemory

    vault = VaultMemory(vault_root=tmp_path)

    config_dir = tmp_path / "04-Config"
    config_dir.mkdir(parents=True)
    (config_dir / "profile.md").write_text("# Profile\n\nI'm a student.\n")

    content = vault.read_config_file("profile.md")
    assert "I'm a student" in content
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `pytest tests/unit/test_vault_memory.py::test_read_life_file_returns_content_or_empty tests/unit/test_vault_memory.py::test_write_life_file tests/unit/test_vault_memory.py::test_read_config_file -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 15: Implement life and config file methods**

Add to `src/pulse/analysis/vault_memory.py` in the `VaultMemory` class:

```python
    def read_life_file(self, filename: str) -> str:
        path = self._root / "03-Life" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_life_file(self, filename: str, content: str) -> Path:
        path = self._root / "03-Life" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_config_file(self, filename: str) -> str:
        path = self._root / "04-Config" / filename
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
```

- [ ] **Step 16: Run all vault_memory tests**

Run: `pytest tests/unit/test_vault_memory.py -v`
Expected: All PASS

- [ ] **Step 17: Commit**

```bash
git add src/pulse/analysis/vault_memory.py tests/unit/test_vault_memory.py
git commit -m "feat: add VaultMemory for reading/writing pattern and life knowledge files"
```

---

## Task 5: Event Summarizer

**Files:**
- Create: `src/pulse/analysis/event_summarizer.py`
- Test: `tests/unit/test_event_summarizer.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_event_summarizer.py`:

```python
from datetime import UTC, datetime


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event
    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})


def test_summarize_events_groups_by_source():
    from pulse.analysis.event_summarizer import EventSummarizer

    stats = [
        {"date": "2026-03-25", "source": "gmail", "event_type": "email.received", "count": 12, "first_at": "2026-03-25T09:00:00", "last_at": "2026-03-25T17:00:00"},
        {"date": "2026-03-25", "source": "spotify", "event_type": "media.spotify.play", "count": 8, "first_at": "2026-03-25T18:00:00", "last_at": "2026-03-25T22:00:00"},
    ]

    events = [
        _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Project update", "from": "alice@co.com"}),
        _make_event("e2", datetime(2026, 3, 25, 10, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Meeting notes", "from": "bob@co.com"}),
        _make_event("e3", datetime(2026, 3, 25, 18, 0, tzinfo=UTC), "spotify", "media.spotify.play", {"track_name": "Cool Song", "artist": "Artist A"}),
    ]

    baselines = [
        {"source": "gmail", "event_type": "email.received", "avg_daily": 8.0, "total": 56},
    ]

    summarizer = EventSummarizer()
    result = summarizer.summarize(
        date_range="March 25",
        stats=stats,
        events=events,
        baselines=baselines,
    )

    assert "## gmail" in result or "## Gmail" in result
    assert "12" in result  # event count
    assert "## spotify" in result or "## Spotify" in result
    assert "Cool Song" in result
    assert "baseline" in result.lower() or "avg" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_event_summarizer.py::test_summarize_events_groups_by_source -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `EventSummarizer`**

Create `src/pulse/analysis/event_summarizer.py`:

```python
from collections import defaultdict

from pulse.domain.events import Event


class EventSummarizer:
    def summarize(
        self,
        date_range: str,
        stats: list[dict],
        events: list[Event],
        baselines: list[dict] | None = None,
    ) -> str:
        baselines = baselines or []
        baseline_map = {
            (b["source"], b["event_type"]): b for b in baselines
        }

        # Group stats by source
        source_stats: dict[str, list[dict]] = defaultdict(list)
        for s in stats:
            source_stats[s["source"]].append(s)

        # Group events by source for content extraction
        source_events: dict[str, list[Event]] = defaultdict(list)
        for e in events:
            source_events[e.source].append(e)

        sections = []
        for source in sorted(source_stats.keys()):
            lines = [f"## {source} ({date_range})"]

            for stat in source_stats[source]:
                count = stat["count"]
                etype = stat["event_type"]
                line = f"- {etype}: {count} events"

                baseline = baseline_map.get((source, etype))
                if baseline:
                    avg = baseline["avg_daily"]
                    if avg > 0:
                        pct = ((count / avg) - 1) * 100
                        direction = "up" if pct > 0 else "down"
                        line += f" (baseline avg {avg:.1f}/day, {direction} {abs(pct):.0f}%)"

                lines.append(line)

            # Add content highlights from events
            highlights = _extract_highlights(source, source_events.get(source, []))
            if highlights:
                lines.append(f"- Highlights: {', '.join(highlights)}")

            sections.append("\n".join(lines))

        return "\n\n".join(sections)


def _extract_highlights(source: str, events: list[Event], max_items: int = 5) -> list[str]:
    highlights = []
    for event in events[:max_items]:
        if event.event_type == "email.received":
            subject = event.data.get("subject", "")
            sender = event.data.get("from", "")
            if subject:
                label = f'"{subject}"'
                if sender:
                    label += f" from {sender}"
                highlights.append(label)
        elif event.event_type == "media.spotify.play":
            track = event.data.get("track_name", "")
            artist = event.data.get("artist", "")
            if track:
                highlights.append(f"{track} by {artist}" if artist else track)
        elif event.event_type == "calendar.event":
            title = event.data.get("title", "")
            if title:
                highlights.append(title)
        elif event.event_type == "browsing.visit":
            title = event.data.get("title") or event.data.get("url", "")
            if title:
                highlights.append(title)
        elif event.event_type in ("media.youtube.activity", "media.youtube.like"):
            title = event.data.get("title", "")
            if title:
                highlights.append(title)
        else:
            # Generic: use event_type as fallback
            summary = event.data.get("title") or event.data.get("subject") or event.data.get("name")
            if summary:
                highlights.append(summary)
    return highlights
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_event_summarizer.py::test_summarize_events_groups_by_source -v`
Expected: PASS

- [ ] **Step 5: Write test for empty data**

Add to `tests/unit/test_event_summarizer.py`:

```python
def test_summarize_empty_data_returns_empty_string():
    from pulse.analysis.event_summarizer import EventSummarizer

    result = EventSummarizer().summarize(
        date_range="March 25",
        stats=[],
        events=[],
        baselines=[],
    )
    assert result == ""
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/test_event_summarizer.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/analysis/event_summarizer.py tests/unit/test_event_summarizer.py
git commit -m "feat: add EventSummarizer for condensing events into LLM-readable summaries"
```

---

## Task 6: LLM Protocol and Anthropic Provider

**Files:**
- Modify: `src/pulse/domain/llm.py:1-5`
- Create: `src/pulse/llm/anthropic.py`
- Modify: `pyproject.toml:11-20` (add anthropic dependency)
- Modify: `src/pulse/app/config.py:10-20` (add api key field)
- Test: `tests/unit/test_llm_provider.py` (new)

- [ ] **Step 1: Write failing test for the LLM protocol**

Create `tests/unit/test_llm_provider.py`:

```python
import asyncio


def test_anthropic_provider_satisfies_llm_protocol():
    from pulse.domain.llm import LLM
    from pulse.llm.anthropic import AnthropicProvider

    # Verify it has the right method signature (structural typing)
    provider = AnthropicProvider(api_key="fake-key")
    assert hasattr(provider, "complete")


def test_anthropic_provider_calls_api(monkeypatch):
    async def exercise():
        from pulse.llm.anthropic import AnthropicProvider

        calls = []

        class FakeMessages:
            def create(self, **kwargs):
                calls.append(kwargs)

                class FakeResponse:
                    class Content:
                        text = '{"patterns": []}'
                    content = [Content()]
                return FakeResponse()

        class FakeClient:
            messages = FakeMessages()

        provider = AnthropicProvider(api_key="fake-key")
        provider._client = FakeClient()

        result = await provider.complete(
            prompt="Find patterns",
            system_prompt="You are an insight engine",
        )

        assert result == '{"patterns": []}'
        assert len(calls) == 1
        assert calls[0]["system"] == "You are an insight engine"

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulse.llm'`

- [ ] **Step 3: Update LLM protocol**

Replace `src/pulse/domain/llm.py`:

```python
from typing import Protocol


class LLM(Protocol):
    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str: ...
```

- [ ] **Step 4: Create `src/pulse/llm/__init__.py`**

```python
```

(Empty `__init__.py` to make it a package.)

- [ ] **Step 5: Implement Anthropic provider**

Create `src/pulse/llm/anthropic.py`:

```python
import anthropic


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)
        return response.content[0].text
```

- [ ] **Step 6: Add anthropic dependency to pyproject.toml**

Add `"anthropic",` to the `dependencies` list in `pyproject.toml`.

- [ ] **Step 7: Add `anthropic_api_key` to config**

Add to `src/pulse/app/config.py` in `PulseConfig`:

```python
    anthropic_api_key: str | None = None
```

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_llm_provider.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/pulse/domain/llm.py src/pulse/llm/__init__.py src/pulse/llm/anthropic.py tests/unit/test_llm_provider.py pyproject.toml src/pulse/app/config.py
git commit -m "feat: add async LLM protocol and Anthropic provider"
```

---

## Task 7: Prompt Templates and Response Schema

**Files:**
- Create: `src/pulse/analysis/prompts.py`
- Test: `tests/unit/test_prompts.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_prompts.py`:

```python
def test_build_discovery_prompt_includes_all_sections():
    from pulse.analysis.prompts import build_discovery_prompt

    result = build_discovery_prompt(
        cadence="weekly",
        date_range="March 19-25, 2026",
        event_summary="## gmail\n- 47 emails received",
        active_patterns="# Pattern: Late browsing\n**Status:** active",
        baselines="- Email: 5.2/day",
        user_profile="I'm a student.",
    )

    assert "March 19-25, 2026" in result["user_prompt"]
    assert "47 emails received" in result["user_prompt"]
    assert "Late browsing" in result["user_prompt"]
    assert "5.2/day" in result["user_prompt"]
    assert "I'm a student" in result["user_prompt"]
    assert "system_prompt" in result
    assert "JSON" in result["system_prompt"]


def test_build_discovery_prompt_handles_empty_patterns():
    from pulse.analysis.prompts import build_discovery_prompt

    result = build_discovery_prompt(
        cadence="daily",
        date_range="March 25, 2026",
        event_summary="## gmail\n- 5 emails",
        active_patterns="",
        baselines="",
        user_profile="",
    )

    assert "No active patterns yet" in result["user_prompt"]
    assert "March 25, 2026" in result["user_prompt"]


def test_parse_discovery_response_extracts_fields():
    import json
    from pulse.analysis.prompts import parse_discovery_response

    raw = json.dumps({
        "new_patterns": [
            {
                "title": "Test Pattern",
                "observation": "Something interesting",
                "confidence": "medium",
                "evidence": ["data point 1"],
                "trend": "New",
            }
        ],
        "updated_patterns": [
            {
                "slug": "old-pattern",
                "status": "strengthening",
                "confidence": "high",
                "update_note": "More evidence found",
                "new_evidence": ["data point 2"],
                "trend": "Strengthening over 4 weeks",
            }
        ],
        "notifications": [
            {
                "title": "New Pattern Found",
                "body": "Something interesting was discovered.",
                "priority": "normal",
            }
        ],
        "baseline_updates": None,
    })

    result = parse_discovery_response(raw)

    assert len(result.new_patterns) == 1
    assert result.new_patterns[0].title == "Test Pattern"
    assert len(result.updated_patterns) == 1
    assert result.updated_patterns[0].slug == "old-pattern"
    assert len(result.notifications) == 1


def test_parse_discovery_response_handles_malformed_json():
    from pulse.analysis.prompts import parse_discovery_response

    result = parse_discovery_response("not valid json {{{")
    assert result.new_patterns == []
    assert result.updated_patterns == []
    assert result.notifications == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement prompts module**

Create `src/pulse/analysis/prompts.py`:

```python
import json
from dataclasses import dataclass, field

SYSTEM_PROMPT = """You are Pulse's insight engine. You analyze personal data to find cross-source patterns and correlations the user wouldn't notice on their own. You maintain a set of tracked patterns that evolve over time.

Rules:
- Only surface genuinely interesting or actionable findings
- Update existing patterns with new evidence (strengthening/weakening)
- Mark patterns as "invalidated" if the data no longer supports them
- Be specific — cite actual data points, not vague observations
- Look for CROSS-SOURCE connections (e.g., email + calendar + browsing, not just one source)
- Output valid JSON matching the schema below

Output JSON schema:
{
  "new_patterns": [
    {
      "title": "Short descriptive title",
      "observation": "Detailed observation with specific data",
      "confidence": "low|medium|high",
      "evidence": ["specific data point 1", "specific data point 2"],
      "trend": "Description of trend direction"
    }
  ],
  "updated_patterns": [
    {
      "slug": "existing-pattern-slug",
      "status": "active|strengthening|weakening|invalidated",
      "confidence": "low|medium|high",
      "update_note": "What changed",
      "new_evidence": ["new data point"],
      "trend": "Updated trend description"
    }
  ],
  "notifications": [
    {
      "title": "Notification title",
      "body": "Concise notification text worth pushing to the user",
      "priority": "low|normal|high"
    }
  ],
  "baseline_updates": "Updated baselines text if significant changes detected, or null"
}"""


def build_discovery_prompt(
    cadence: str,
    date_range: str,
    event_summary: str,
    active_patterns: str,
    baselines: str,
    user_profile: str,
) -> dict[str, str]:
    cadence_instructions = {
        "daily": "Focus on what was notable or unusual today compared to baselines.",
        "weekly": "Look for cross-source patterns and correlations across the full week.",
        "monthly": "Review long-term trends. How have tracked patterns evolved? Any new macro patterns?",
    }

    sections = [f"## Current Data ({date_range})", event_summary, ""]

    if active_patterns:
        sections.extend(["## Your Active Patterns", active_patterns, ""])
    else:
        sections.extend(["## Your Active Patterns", "No active patterns yet. Look for new ones.", ""])

    if baselines:
        sections.extend(["## Known Baselines", baselines, ""])
    else:
        sections.extend(["## Known Baselines", "No baselines established yet.", ""])

    if user_profile:
        sections.extend(["## User Profile", user_profile, ""])

    instruction = cadence_instructions.get(cadence, cadence_instructions["weekly"])
    sections.extend(["---", instruction])
    sections.append("What new patterns do you see? How have existing patterns changed?")

    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": "\n".join(sections),
    }


@dataclass(slots=True)
class NewPattern:
    title: str
    observation: str
    confidence: str
    evidence: list[str]
    trend: str


@dataclass(slots=True)
class UpdatedPattern:
    slug: str
    status: str
    confidence: str
    update_note: str
    new_evidence: list[str]
    trend: str


@dataclass(slots=True)
class NotificationItem:
    title: str
    body: str
    priority: str


@dataclass(slots=True)
class DiscoveryResponse:
    new_patterns: list[NewPattern] = field(default_factory=list)
    updated_patterns: list[UpdatedPattern] = field(default_factory=list)
    notifications: list[NotificationItem] = field(default_factory=list)
    baseline_updates: str | None = None


def parse_discovery_response(raw: str) -> DiscoveryResponse:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return DiscoveryResponse()

    new_patterns = [
        NewPattern(
            title=p.get("title", ""),
            observation=p.get("observation", ""),
            confidence=p.get("confidence", "low"),
            evidence=p.get("evidence", []),
            trend=p.get("trend", ""),
        )
        for p in data.get("new_patterns", [])
    ]

    updated_patterns = [
        UpdatedPattern(
            slug=p.get("slug", ""),
            status=p.get("status", "active"),
            confidence=p.get("confidence", "medium"),
            update_note=p.get("update_note", ""),
            new_evidence=p.get("new_evidence", []),
            trend=p.get("trend", ""),
        )
        for p in data.get("updated_patterns", [])
    ]

    notifications = [
        NotificationItem(
            title=n.get("title", ""),
            body=n.get("body", ""),
            priority=n.get("priority", "normal"),
        )
        for n in data.get("notifications", [])
    ]

    return DiscoveryResponse(
        new_patterns=new_patterns,
        updated_patterns=updated_patterns,
        notifications=notifications,
        baseline_updates=data.get("baseline_updates"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/prompts.py tests/unit/test_prompts.py
git commit -m "feat: add discovery prompt templates and response parsing"
```

---

## Task 8: Discovery Engine Orchestrator

**Files:**
- Create: `src/pulse/analysis/discovery.py`
- Test: `tests/unit/test_discovery.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_discovery.py`:

```python
import asyncio
import json
from datetime import UTC, date, datetime


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event
    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})


def test_discovery_engine_full_cycle(tmp_path):
    """End-to-end test: events → aggregation → discovery → vault + insights + notifications."""
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.analysis.discovery import DiscoveryEngine

        db_path = tmp_path / "test.db"
        vault_path = tmp_path / "vault"

        # Seed events
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Project update", "from": "alice@co.com"}),
                _make_event("e2", datetime(2026, 3, 25, 10, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Meeting notes", "from": "bob@co.com"}),
                _make_event("e3", datetime(2026, 3, 25, 22, 0, tzinfo=UTC), "browser", "browsing.visit", {"url": "https://youtube.com", "title": "YouTube"}),
                _make_event("e4", datetime(2026, 3, 25, 14, 0, tzinfo=UTC), "calendar", "calendar.event", {"title": "Team sync"}),
            ])

        # Fake LLM that returns a canned discovery response
        llm_response = json.dumps({
            "new_patterns": [
                {
                    "title": "Late Browsing After Meetings",
                    "observation": "On days with meetings, browsing occurs after 10pm.",
                    "confidence": "medium",
                    "evidence": ["2026-03-25: 1 meeting + browsing at 10pm"],
                    "trend": "New — needs more data",
                }
            ],
            "updated_patterns": [],
            "notifications": [
                {
                    "title": "New Pattern Detected",
                    "body": "You tend to browse late on meeting days.",
                    "priority": "normal",
                }
            ],
            "baseline_updates": None,
        })

        class FakeLLM:
            calls: list[dict] = []

            async def complete(self, prompt, *, system_prompt=None):
                self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
                return llm_response

        fake_llm = FakeLLM()
        sent_notifications: list = []

        class FakeChannel:
            def send(self, notification):
                sent_notifications.append(notification)
                return True

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_path,
            llm=fake_llm,
            notification_channel=FakeChannel(),
        )

        result = await engine.run_discovery(
            cadence="daily",
            target_date=date(2026, 3, 25),
        )

        # Verify LLM was called
        assert len(fake_llm.calls) == 1
        assert "gmail" in fake_llm.calls[0]["prompt"].lower() or "email" in fake_llm.calls[0]["prompt"].lower()

        # Verify pattern was written to vault
        vault = VaultMemory(vault_root=vault_path)
        patterns = vault.read_patterns()
        assert len(patterns) == 1
        assert "Late Browsing" in patterns[0]["content"]

        # Verify insight was stored in DB
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()
            assert len(insights) == 1
            assert insights[0]["status"] == "active"

        # Verify notification was sent
        assert len(sent_notifications) == 1
        assert "New Pattern Detected" in sent_notifications[0].title

    asyncio.run(exercise())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_discovery.py::test_discovery_engine_full_cycle -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pulse.analysis.discovery'`

- [ ] **Step 3: Implement `DiscoveryEngine`**

Create `src/pulse/analysis/discovery.py`:

```python
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from pulse.analysis.event_summarizer import EventSummarizer
from pulse.analysis.prompts import build_discovery_prompt, parse_discovery_response
from pulse.analysis.vault_memory import VaultMemory
from pulse.domain.notifications import Notification
from pulse.store.analytics import AnalyticsRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema


@dataclass(slots=True)
class DiscoveryResult:
    new_patterns: int
    updated_patterns: int
    notifications_sent: int


DATA_WINDOWS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


class DiscoveryEngine:
    def __init__(
        self,
        database_path: str | Path,
        vault_root: str | Path,
        llm,
        notification_channel=None,
    ) -> None:
        self._db_path = database_path
        self._vault = VaultMemory(vault_root)
        self._llm = llm
        self._channel = notification_channel

    async def run_discovery(
        self,
        cadence: str,
        target_date: date,
    ) -> DiscoveryResult:
        window_days = DATA_WINDOWS.get(cadence, 7)
        start_date = target_date - timedelta(days=window_days - 1)

        async with connect_db(self._db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics = AnalyticsRepository(db)

            # Step 1: Aggregate stats for the window
            for day_offset in range(window_days):
                day = (start_date + timedelta(days=day_offset)).isoformat()
                await analytics.aggregate_day(day)

            # Step 2: Gather stats and events
            stats = await analytics.get_daily_stats_range(
                start_date.isoformat(),
                (target_date + timedelta(days=1)).isoformat(),
            )

            all_events = []
            for day_offset in range(window_days):
                day = (start_date + timedelta(days=day_offset)).isoformat()
                day_events = await event_repo.list_events_for_day(day)
                all_events.extend(day_events)

            # Step 3: Get baselines
            baselines = []
            # Use most recent available baselines
            for weeks_back in range(1, 5):
                week_start = (target_date - timedelta(weeks=weeks_back)).isoformat()
                baselines = await analytics.get_weekly_baselines(week_start)
                if baselines:
                    break

            # Step 4: Build event summary
            summarizer = EventSummarizer()
            date_range = (
                target_date.isoformat()
                if window_days == 1
                else f"{start_date.isoformat()} to {target_date.isoformat()}"
            )
            event_summary = summarizer.summarize(
                date_range=date_range,
                stats=stats,
                events=all_events,
                baselines=baselines,
            )

            # Step 5: Read vault memory
            patterns = self._vault.read_patterns()
            active_patterns = "\n\n---\n\n".join(p["content"] for p in patterns) if patterns else ""
            baselines_text = self._vault.read_life_file("routines.md")
            user_profile = self._vault.read_config_file("profile.md")

            # Step 6: Build prompt and call LLM
            prompt = build_discovery_prompt(
                cadence=cadence,
                date_range=date_range,
                event_summary=event_summary,
                active_patterns=active_patterns,
                baselines=baselines_text,
                user_profile=user_profile,
            )

            raw_response = await self._llm.complete(
                prompt=prompt["user_prompt"],
                system_prompt=prompt["system_prompt"],
            )

            # Step 7: Parse response
            response = parse_discovery_response(raw_response)

            # Step 8: Write back
            today = target_date.isoformat()

            # New patterns → vault + insights table
            for pattern in response.new_patterns:
                slug = _slugify(pattern.title)
                self._vault.write_pattern(
                    slug=slug,
                    title=pattern.title,
                    status="active",
                    confidence=pattern.confidence,
                    first_seen=today,
                    last_updated=today,
                    observation=pattern.observation,
                    evidence_log=pattern.evidence,
                    trend=pattern.trend,
                )
                await analytics.upsert_insight(
                    id=slug,
                    title=pattern.title,
                    status="active",
                    confidence=pattern.confidence,
                    first_seen=today,
                    last_seen=today,
                    vault_path=f"02-Insights/patterns/{slug}.md",
                )

            # Updated patterns → vault + insights table
            for update in response.updated_patterns:
                self._vault.update_pattern(
                    slug=update.slug,
                    title=update.slug.replace("-", " ").title(),
                    status=update.status,
                    confidence=update.confidence,
                    first_seen="",  # preserved by update_pattern
                    last_updated=today,
                    observation=update.update_note,
                    evidence_log=update.new_evidence,
                    trend=update.trend,
                )
                await analytics.upsert_insight(
                    id=update.slug,
                    title=update.slug.replace("-", " ").title(),
                    status=update.status,
                    confidence=update.confidence,
                    first_seen="",
                    last_seen=today,
                    vault_path=f"02-Insights/patterns/{update.slug}.md",
                )

            # Baseline updates → vault
            if response.baseline_updates:
                self._vault.write_life_file("routines.md", response.baseline_updates)

            # Notifications → channel
            notifications_sent = 0
            if self._channel:
                for notif in response.notifications:
                    notification = Notification(
                        title=notif.title,
                        body=notif.body,
                        category="insight",
                        priority=notif.priority,
                    )
                    if self._channel.send(notification):
                        notifications_sent += 1

        return DiscoveryResult(
            new_patterns=len(response.new_patterns),
            updated_patterns=len(response.updated_patterns),
            notifications_sent=notifications_sent,
        )


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_discovery.py::test_discovery_engine_full_cycle -v`
Expected: PASS

- [ ] **Step 5: Write test for discovery with no notification channel**

Add to `tests/unit/test_discovery.py`:

```python
def test_discovery_engine_works_without_notification_channel(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.analysis.discovery import DiscoveryEngine

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Hi"}),
            ])

        class FakeLLM:
            async def complete(self, prompt, *, system_prompt=None):
                return json.dumps({
                    "new_patterns": [],
                    "updated_patterns": [],
                    "notifications": [{"title": "Test", "body": "Test", "priority": "normal"}],
                    "baseline_updates": None,
                })

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=tmp_path / "vault",
            llm=FakeLLM(),
            notification_channel=None,
        )

        result = await engine.run_discovery(cadence="daily", target_date=date(2026, 3, 25))
        assert result.notifications_sent == 0

    asyncio.run(exercise())
```

- [ ] **Step 6: Run all discovery tests**

Run: `pytest tests/unit/test_discovery.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/pulse/analysis/discovery.py tests/unit/test_discovery.py
git commit -m "feat: add DiscoveryEngine orchestrator for LLM-assisted pattern finding"
```

---

## Task 9: Job Runners and Scheduler Integration

**Files:**
- Modify: `src/pulse/jobs/runners.py:1-77`
- Modify: `src/pulse/jobs/scheduler.py:1-158`
- Test: `tests/unit/test_scheduler.py` (existing — add new tests)

- [ ] **Step 1: Write failing test for aggregation runner**

Add to a new file `tests/integration/test_aggregation_pipeline.py` (append to the file created in Task 1):

```python
def test_run_aggregation_job(tmp_path):
    async def exercise():
        from datetime import UTC, datetime, date
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository
        from pulse.jobs.runners import run_aggregation_job

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received"),
                _make_event("e2", datetime(2026, 3, 25, 14, 0, tzinfo=UTC), "gmail", "email.received"),
            ])

        result = await run_aggregation_job(
            day=date(2026, 3, 25),
            database_path=db_path,
        )
        assert result.status == "success"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            stats = await analytics.get_daily_stats("2026-03-25")
            assert len(stats) == 1
            assert stats[0]["count"] == 2

    import asyncio
    asyncio.run(exercise())


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event
    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_aggregation_pipeline.py::test_run_aggregation_job -v`
Expected: FAIL — `ImportError: cannot import name 'run_aggregation_job'`

- [ ] **Step 3: Add `run_aggregation_job` to runners.py**

Add to `src/pulse/jobs/runners.py`:

```python
async def run_aggregation_job(
    day: date, database_path: str | Path
) -> JobResult:
    from pulse.store.analytics import AnalyticsRepository

    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        analytics = AnalyticsRepository(db)
        await analytics.aggregate_day(day.isoformat())

    return JobResult(status="success", detail=f"Aggregated stats for {day.isoformat()}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_aggregation_pipeline.py::test_run_aggregation_job -v`
Expected: PASS

- [ ] **Step 5: Write failing test for discovery runner**

Add to `tests/integration/test_discovery_cycle.py` (new file):

```python
import asyncio
import json
from datetime import UTC, date, datetime

from pulse.domain.events import Event


def _make_event(id, timestamp, source, event_type, data=None):
    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})


def test_run_discovery_job(tmp_path):
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.jobs.runners import run_discovery_job

        db_path = tmp_path / "test.db"
        vault_path = tmp_path / "vault"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e1", datetime(2026, 3, 25, 9, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Hi"}),
            ])

        class FakeLLM:
            async def complete(self, prompt, *, system_prompt=None):
                return json.dumps({
                    "new_patterns": [],
                    "updated_patterns": [],
                    "notifications": [],
                    "baseline_updates": None,
                })

        result = await run_discovery_job(
            cadence="daily",
            target_date=date(2026, 3, 25),
            database_path=db_path,
            vault_path=vault_path,
            llm=FakeLLM(),
            notification_channel=None,
        )
        assert result.status == "success"

    asyncio.run(exercise())
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/integration/test_discovery_cycle.py::test_run_discovery_job -v`
Expected: FAIL — `ImportError: cannot import name 'run_discovery_job'`

- [ ] **Step 7: Add `run_discovery_job` to runners.py**

Add to `src/pulse/jobs/runners.py`:

```python
async def run_discovery_job(
    cadence: str,
    target_date: date,
    database_path: str | Path,
    vault_path: str | Path,
    llm,
    notification_channel=None,
) -> JobResult:
    from pulse.analysis.discovery import DiscoveryEngine

    engine = DiscoveryEngine(
        database_path=database_path,
        vault_root=vault_path,
        llm=llm,
        notification_channel=notification_channel,
    )
    result = await engine.run_discovery(cadence=cadence, target_date=target_date)
    return JobResult(
        status="success",
        detail=(
            f"Discovery ({cadence}): {result.new_patterns} new patterns, "
            f"{result.updated_patterns} updated, {result.notifications_sent} notifications"
        ),
    )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/integration/test_discovery_cycle.py::test_run_discovery_job -v`
Expected: PASS

- [ ] **Step 9: Add discovery jobs to scheduler**

Add to `src/pulse/jobs/scheduler.py` in `build_scheduler()`, after the morning_briefing job (line 70):

```python
    # Aggregation job — hourly
    scheduler.add_job(
        _make_aggregation_job(config),
        "interval",
        hours=1,
        id="aggregation",
    )

    # Discovery jobs
    scheduler.add_job(
        _make_discovery_job("daily", config),
        "cron",
        hour=23,
        id="discovery_daily",
    )
    scheduler.add_job(
        _make_discovery_job("weekly", config),
        "cron",
        day_of_week="sun",
        hour=20,
        id="discovery_weekly",
    )
    scheduler.add_job(
        _make_discovery_job("monthly", config),
        "cron",
        day=1,
        hour=10,
        id="discovery_monthly",
    )
```

Add the helper functions at the bottom of `scheduler.py`:

```python
def _make_aggregation_job(config):
    async def job():
        from pulse.jobs.runners import run_aggregation_job
        day = _resolve_current_day(config)
        return await run_aggregation_job(day=day, database_path=config.database_path)
    return job


def _make_discovery_job(cadence, config):
    async def job():
        from pulse.jobs.runners import run_discovery_job
        from pulse.llm.anthropic import AnthropicProvider

        day = _resolve_current_day(config)
        llm = None
        if config.anthropic_api_key:
            llm = AnthropicProvider(api_key=config.anthropic_api_key)

        if llm is None:
            return JobResult(
                status="skipped",
                detail=f"Discovery ({cadence}) skipped: no LLM provider configured",
            )

        channel = _build_telegram_channel(config)
        return await run_discovery_job(
            cadence=cadence,
            target_date=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=llm,
            notification_channel=channel,
        )
    return job
```

- [ ] **Step 10: Run the existing scheduler tests to check for regressions**

Run: `pytest tests/unit/test_scheduler.py -v`
Expected: All PASS

- [ ] **Step 11: Run the full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 12: Commit**

```bash
git add src/pulse/jobs/runners.py src/pulse/jobs/scheduler.py tests/integration/test_aggregation_pipeline.py tests/integration/test_discovery_cycle.py
git commit -m "feat: wire aggregation and discovery jobs into runners and scheduler"
```

---

## Task 10: Integration Test — Full Discovery Cycle with Pattern Evolution

**Files:**
- Test: `tests/integration/test_discovery_cycle.py` (extend)

- [ ] **Step 1: Write the multi-pass evolution test**

Add to `tests/integration/test_discovery_cycle.py`:

```python
def test_pattern_evolution_across_multiple_passes(tmp_path):
    """Run discovery twice: first creates a pattern, second updates it."""
    async def exercise():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.analysis.discovery import DiscoveryEngine

        db_path = tmp_path / "test.db"
        vault_path = tmp_path / "vault"

        # Seed week 1 events
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e1", datetime(2026, 3, 20, 9, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Meeting prep"}),
                _make_event("e2", datetime(2026, 3, 20, 22, 0, tzinfo=UTC), "browser", "browsing.visit", {"title": "YouTube"}),
            ])

        # Pass 1: LLM discovers a new pattern
        pass1_response = json.dumps({
            "new_patterns": [{
                "title": "Late Browsing Pattern",
                "observation": "Browsing after 10pm on email-heavy days",
                "confidence": "low",
                "evidence": ["2026-03-20: email + late browsing"],
                "trend": "New — needs more data",
            }],
            "updated_patterns": [],
            "notifications": [],
            "baseline_updates": None,
        })

        call_count = {"n": 0}

        # Pass 2: LLM sees the existing pattern and strengthens it
        pass2_response = json.dumps({
            "new_patterns": [],
            "updated_patterns": [{
                "slug": "late-browsing-pattern",
                "status": "strengthening",
                "confidence": "medium",
                "update_note": "Pattern confirmed with new data",
                "new_evidence": ["2026-03-25: same pattern repeated"],
                "trend": "Strengthening — 2 weeks consistent",
            }],
            "notifications": [{
                "title": "Pattern Strengthening",
                "body": "Late browsing on busy days is becoming a consistent pattern.",
                "priority": "normal",
            }],
            "baseline_updates": None,
        })

        class FakeLLM:
            async def complete(self, prompt, *, system_prompt=None):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return pass1_response
                return pass2_response

        sent = []

        class FakeChannel:
            def send(self, notification):
                sent.append(notification)
                return True

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_path,
            llm=FakeLLM(),
            notification_channel=FakeChannel(),
        )

        # Pass 1
        result1 = await engine.run_discovery(cadence="weekly", target_date=date(2026, 3, 20))
        assert result1.new_patterns == 1

        # Verify pattern file exists
        vault = VaultMemory(vault_root=vault_path)
        patterns = vault.read_patterns()
        assert len(patterns) == 1
        assert "**Confidence:** low" in patterns[0]["content"]

        # Add more events for week 2
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events([
                _make_event("e3", datetime(2026, 3, 25, 10, 0, tzinfo=UTC), "gmail", "email.received", {"subject": "Sprint review"}),
                _make_event("e4", datetime(2026, 3, 25, 23, 0, tzinfo=UTC), "browser", "browsing.visit", {"title": "Reddit"}),
            ])

        # Pass 2
        result2 = await engine.run_discovery(cadence="weekly", target_date=date(2026, 3, 25))
        assert result2.updated_patterns == 1
        assert result2.notifications_sent == 1

        # Verify pattern file was updated
        patterns = vault.read_patterns()
        assert len(patterns) == 1
        assert "strengthening" in patterns[0]["content"].lower() or "Strengthening" in patterns[0]["content"]

        # Verify insight status updated in DB
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()
            assert len(insights) == 1
            assert insights[0]["status"] == "strengthening"

        # Verify notification was sent
        assert len(sent) == 1

    asyncio.run(exercise())
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/integration/test_discovery_cycle.py::test_pattern_evolution_across_multiple_passes -v`
Expected: PASS (all code from previous tasks should support this)

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_discovery_cycle.py
git commit -m "test: add multi-pass pattern evolution integration test"
```

---

## Task 11: Final Verification and Cleanup

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: All tests pass, no warnings

- [ ] **Step 2: Run linter**

Run: `ruff check src/pulse/store/analytics.py src/pulse/analysis/discovery.py src/pulse/analysis/event_summarizer.py src/pulse/analysis/vault_memory.py src/pulse/analysis/prompts.py src/pulse/llm/anthropic.py`
Expected: No errors (fix any that appear)

- [ ] **Step 3: Verify file structure matches spec**

Verify these files exist:
- `src/pulse/store/analytics.py`
- `src/pulse/analysis/discovery.py`
- `src/pulse/analysis/event_summarizer.py`
- `src/pulse/analysis/vault_memory.py`
- `src/pulse/analysis/prompts.py`
- `src/pulse/llm/__init__.py`
- `src/pulse/llm/anthropic.py`

- [ ] **Step 4: Commit any cleanup**

```bash
git add -A
git commit -m "chore: lint fixes and cleanup for analytics + insight engine"
```

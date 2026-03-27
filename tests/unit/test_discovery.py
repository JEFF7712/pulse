"""Tests for DiscoveryEngine — LLM-assisted pattern discovery orchestrator."""
import asyncio
import json
from datetime import UTC, date, datetime

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event

    return Event(
        id=id,
        timestamp=timestamp,
        source=source,
        event_type=event_type,
        data=data or {},
    )


# Canned LLM response: 1 new pattern, 0 updated patterns, 1 notification
_LLM_RESPONSE = json.dumps({
    "new_patterns": [
        {
            "title": "Late Night Focus Sessions",
            "observation": "User consistently works after 22:00 on weeknights.",
            "confidence": 0.85,
            "evidence": ["2026-03-19: coding session 22:00-01:00", "2026-03-20: writing 23:00-00:30"],
            "trend": "new",
        }
    ],
    "updated_patterns": [],
    "notifications": [
        {
            "title": "New Pattern Detected",
            "body": "You have a late-night focus pattern emerging.",
            "priority": "medium",
        }
    ],
    "baseline_updates": "Late-night coding sessions avg 2h per weeknight.",
})


class FakeLLM:
    def __init__(self, response: str):
        self.calls: list[dict] = []
        self._response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, "model": model})
        return self._response


class FakeChannel:
    def __init__(self):
        self.sent: list = []

    def send(self, notification):
        self.sent.append(notification)
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_discovery_engine_full_cycle(tmp_path):
    """Seeds events, runs discovery with FakeLLM, verifies all side-effects."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)

            # Seed some events on the target day
            events = [
                _make_event(
                    "e1",
                    datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                    {"subject": "Project update", "from": "alice@example.com"},
                ),
                _make_event(
                    "e2",
                    datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                    "github",
                    "commit.pushed",
                    {"message": "fix: improve caching"},
                ),
                _make_event(
                    "e3",
                    datetime(2026, 3, 20, 23, 0, tzinfo=UTC),
                    "github",
                    "commit.pushed",
                    {"message": "feat: add new endpoint"},
                ),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        result = await engine.run_discovery("daily", target_date)

        # Return everything we need to verify
        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory
        vault = VaultMemory(vault_root)
        patterns = vault.read_patterns()

        return result, insights, patterns

    result, insights, patterns = asyncio.run(exercise())

    # LLM was called
    assert len(fake_llm.calls) >= 1, "LLM should have been called at least once"

    # New pattern counts
    assert result.new_patterns == 1
    assert result.updated_patterns == 0

    # Notification was sent
    assert result.notifications_sent == 1
    assert len(fake_channel.sent) == 1
    notif = fake_channel.sent[0]
    assert notif.title == "New Pattern Detected"
    assert notif.body == "You have a late-night focus pattern emerging."

    # Pattern was written to vault
    assert len(patterns) == 1
    assert patterns[0]["slug"] == "late-night-focus-sessions"
    assert "Late Night Focus Sessions" in patterns[0]["content"]

    # Insight stored in DB
    assert len(insights) == 1
    assert insights[0]["title"] == "Late Night Focus Sessions"
    assert insights[0]["status"] == "active"
    assert insights[0]["vault_path"] == "02-Insights/patterns/late-night-focus-sessions.md"


def test_discovery_engine_works_without_notification_channel(tmp_path):
    """Discovery run with no notification channel yields notifications_sent == 0."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)

            events = [
                _make_event(
                    "e1",
                    datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
                    "calendar",
                    "calendar.event",
                    {"title": "Weekly Sync"},
                ),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        return await engine.run_discovery("daily", target_date)

    result = asyncio.run(exercise())

    assert result.notifications_sent == 0
    assert result.new_patterns == 1


def test_discovery_engine_uses_source_summarizer(tmp_path):
    """Discovery should make Haiku summarization calls before the Sonnet discovery call."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            events = [
                _make_event("e1", datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                            "gmail", "email.received",
                            {"subject": "Project update", "from": "alice@example.com"}),
                _make_event("e2", datetime(2026, 3, 20, 14, 0, tzinfo=UTC),
                            "browser", "browsing.visit",
                            {"url": "https://docs.rs/tokio", "title": "tokio - Rust"}),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
            summarization_model="claude-haiku-4-5-20251001",
            discovery_model="claude-sonnet-4-6",
        )
        return await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    # Should have summarization calls (haiku) + 1 discovery call (sonnet)
    haiku_calls = [c for c in fake_llm.calls if c["model"] == "claude-haiku-4-5-20251001"]
    sonnet_calls = [c for c in fake_llm.calls if c["model"] == "claude-sonnet-4-6"]

    assert len(haiku_calls) >= 1, "Should have at least one Haiku summarization call"
    assert len(sonnet_calls) == 1, "Should have exactly one Sonnet discovery call"

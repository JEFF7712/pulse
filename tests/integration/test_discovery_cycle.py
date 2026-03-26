import asyncio
import json
from datetime import UTC, date, datetime

from pulse.domain.events import Event


def _make_event(id, timestamp, source, event_type, data=None):
    return Event(id=id, timestamp=timestamp, source=source, event_type=event_type, data=data or {})


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

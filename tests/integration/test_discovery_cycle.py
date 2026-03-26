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

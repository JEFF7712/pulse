import asyncio
from datetime import UTC, date, datetime


def test_run_daily_digest_job_writes_digest_for_requested_day(tmp_path):
    async def exercise() -> None:
        from pulse.domain.events import Event
        from pulse.jobs.runners import run_daily_digest_job
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events.db"
        vault_path = tmp_path / "vault"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EventRepository(db)
            await repository.upsert_events(
                [
                    Event(
                        id="evt-1",
                        timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="calendar.event",
                        data={"title": "Team sync"},
                    ),
                    Event(
                        id="evt-2",
                        timestamp=datetime(2026, 3, 22, 10, 30, tzinfo=UTC),
                        source="email",
                        event_type="email.received",
                        data={"subject": "Project update"},
                    ),
                    Event(
                        id="evt-3",
                        timestamp=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="calendar.event",
                        data={"title": "Tomorrow planning"},
                    ),
                ]
            )

        result = await run_daily_digest_job(
            day=date(2026, 3, 22),
            database_path=db_path,
            vault_path=vault_path,
        )

        output_path = vault_path / "01-Daily" / "2026-03-22.md"

        assert result.status == "success"
        assert result.detail == str(output_path)
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == "\n".join(
            [
                "# 2026-03-22",
                "",
                "## Timeline",
                "- Team sync",
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
                "## Tags",
                "- No tags.",
            ]
        )

    asyncio.run(exercise())

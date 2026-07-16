import asyncio


def test_run_aggregation_job(tmp_path):
    async def exercise():
        from datetime import UTC, datetime, date
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.events import EventRepository
        from pulse.store.analytics import AnalyticsRepository
        from pulse.jobs.runners import run_aggregation_job
        from pulse.domain.events import Event

        db_path = tmp_path / "test.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(
                [
                    Event(
                        id="e1",
                        timestamp=datetime(2026, 3, 25, 9, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={},
                    ),
                    Event(
                        id="e2",
                        timestamp=datetime(2026, 3, 25, 14, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={},
                    ),
                ]
            )

        result = await run_aggregation_job(day=date(2026, 3, 25), database_path=db_path)
        assert result.status == "success"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            stats = await analytics.get_daily_stats("2026-03-25")
            assert len(stats) == 1
            assert stats[0]["count"] == 2

    asyncio.run(exercise())


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

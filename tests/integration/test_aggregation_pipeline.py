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

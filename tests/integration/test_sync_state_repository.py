import asyncio


def test_sync_state_repository_saves_and_loads_latest_cursor(tmp_path):
    async def exercise() -> None:
        import aiosqlite

        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        db_path = tmp_path / "sync-state.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = SyncStateRepository(db)

            assert await repository.load("telegram") is None

            await repository.save(source="telegram", cursor="cursor-1")
            await repository.save(source="telegram", cursor="cursor-2")
            await repository.save(source="slack", cursor="cursor-a")

            assert await repository.load("telegram") == "cursor-2"
            assert await repository.load("slack") == "cursor-a"

            cursor = await db.execute(
                "SELECT source, cursor FROM connector_sync_state ORDER BY source ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()

            assert rows == [
                ("slack", "cursor-a"),
                ("telegram", "cursor-2"),
            ]

        raw_db = await aiosqlite.connect(db_path)
        try:
            cursor = await raw_db.execute("SELECT COUNT(*) FROM connector_sync_state")
            row = await cursor.fetchone()
            await cursor.close()
        finally:
            await raw_db.close()

        assert row == (2,)

    asyncio.run(exercise())


def test_sync_state_repository_refreshes_updated_at_on_conflict(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        db_path = tmp_path / "sync-state-updated-at.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = SyncStateRepository(db)

            await repository.save(source="telegram", cursor="cursor-1")
            await db.execute(
                """
                UPDATE connector_sync_state
                SET updated_at = '2000-01-01 00:00:00'
                WHERE source = ?
                """,
                ("telegram",),
            )
            await db.commit()

            await repository.save(source="telegram", cursor="cursor-2")

            cursor = await db.execute(
                "SELECT cursor, updated_at FROM connector_sync_state WHERE source = ?",
                ("telegram",),
            )
            row = await cursor.fetchone()
            await cursor.close()

            assert row is not None
            assert row[0] == "cursor-2"
            assert row[1] != "2000-01-01 00:00:00"

    asyncio.run(exercise())

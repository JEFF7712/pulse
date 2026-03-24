import asyncio


def test_connect_db_creates_missing_parent_directories(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db

        db_path = tmp_path / "data" / "pulse.db"

        assert not db_path.parent.exists()

        async with connect_db(db_path) as db:
            cursor = await db.execute("SELECT 1")
            row = await cursor.fetchone()
            await cursor.close()

        assert row == (1,)
        assert db_path.parent.exists()
        assert db_path.exists()

    asyncio.run(exercise())

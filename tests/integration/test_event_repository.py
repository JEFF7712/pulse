import asyncio
from datetime import UTC, datetime


def test_event_repository_upserts_and_lists_events_for_day(tmp_path):
    async def exercise() -> None:
        import aiosqlite

        from pulse.domain.events import Event
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EventRepository(db)

            event = Event(
                id="evt-1",
                timestamp=datetime(2026, 3, 22, 9, 30, tzinfo=UTC),
                source="telegram",
                event_type="message.created",
                data={"text": "hello"},
                metadata={"chat_id": 123},
            )
            replacement = Event(
                id="evt-1",
                timestamp=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
                source="telegram",
                event_type="message.updated",
                data={"text": "hello again"},
                metadata={"chat_id": 123, "edited": True},
            )
            other_day = Event(
                id="evt-2",
                timestamp=datetime(2026, 3, 23, 8, 0, tzinfo=UTC),
                source="telegram",
                event_type="message.created",
                data={"text": "tomorrow"},
            )

            await repository.upsert_events([event, replacement, other_day])

            events = await repository.list_events_for_day("2026-03-22")

            assert events == [replacement]
            assert events[0].data == {"text": "hello again"}
            assert events[0].metadata == {"chat_id": 123, "edited": True}
            assert events[0].timestamp == datetime(2026, 3, 22, 10, 0, tzinfo=UTC)

            cursor = await db.execute(
                "SELECT data, metadata FROM events WHERE id = ?",
                ("evt-1",),
            )
            row = await cursor.fetchone()
            await cursor.close()

            assert row == (
                '{"text": "hello again"}',
                '{"chat_id": 123, "edited": true}',
            )

        raw_db = await aiosqlite.connect(db_path)
        try:
            cursor = await raw_db.execute("SELECT COUNT(*) FROM events")
            row = await cursor.fetchone()
            await cursor.close()
        finally:
            await raw_db.close()

        assert row == (2,)

    asyncio.run(exercise())

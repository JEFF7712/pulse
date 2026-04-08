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


def test_event_repository_lists_events_for_local_day_window(tmp_path):
    async def exercise() -> None:
        from pulse.domain.events import Event
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events-local-day.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EventRepository(db)

            await repository.upsert_events(
                [
                    Event(
                        id="before",
                        timestamp=datetime(2026, 1, 15, 7, 59, tzinfo=UTC),
                        source="calendar",
                        event_type="event.created",
                        data={"title": "before window"},
                    ),
                    Event(
                        id="start",
                        timestamp=datetime(2026, 1, 15, 8, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="event.created",
                        data={"title": "start boundary"},
                    ),
                    Event(
                        id="end-minus-one",
                        timestamp=datetime(2026, 1, 16, 7, 59, tzinfo=UTC),
                        source="calendar",
                        event_type="event.created",
                        data={"title": "end boundary minus one minute"},
                    ),
                    Event(
                        id="after",
                        timestamp=datetime(2026, 1, 16, 8, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="event.created",
                        data={"title": "after window"},
                    ),
                ]
            )

            events = await repository.list_events_for_day(
                "2026-01-15", timezone="America/Los_Angeles"
            )

            assert [event.id for event in events] == ["start", "end-minus-one"]

    asyncio.run(exercise())


def test_event_repository_includes_preexisting_offset_rows_in_local_day_window(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events-offset-row.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EventRepository(db)

            await db.execute(
                """
                INSERT INTO events (id, timestamp, source, event_type, data, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-offset",
                    "2026-01-15T01:00:00-08:00",
                    "calendar",
                    "event.created",
                    '{"title": "legacy offset row"}',
                    "{}",
                ),
            )
            await db.commit()

            events = await repository.list_events_for_day(
                "2026-01-15", timezone="America/Los_Angeles"
            )

            assert [event.id for event in events] == ["legacy-offset"]

    asyncio.run(exercise())

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


def _ev(id_, ts, source, etype, data):
    from pulse.domain.events import Event

    return Event(id=id_, timestamp=ts, source=source, event_type=etype, data=data)


def test_query_events_filters_by_range_source_text_and_paginates(tmp_path):
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    async def exercise() -> None:
        async with connect_db(tmp_path / "events.db") as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)

            await repo.upsert_events(
                [
                    _ev(
                        "a",
                        datetime(2026, 7, 1, 9, tzinfo=UTC),
                        "gmail",
                        "email.received",
                        {"subject": "invoice due"},
                    ),
                    _ev(
                        "b",
                        datetime(2026, 7, 1, 10, tzinfo=UTC),
                        "github",
                        "commit",
                        {"message": "fix bug"},
                    ),
                    _ev(
                        "c",
                        datetime(2026, 7, 2, 9, tzinfo=UTC),
                        "gmail",
                        "email.received",
                        {"subject": "lunch"},
                    ),
                ]
            )
            # range excludes Jul 2
            got = await repo.query_events(
                start="2026-07-01T00:00:00+00:00",
                end="2026-07-02T00:00:00+00:00",
            )
            assert [e.id for e in got] == ["b", "a"]  # newest-first
            # source filter
            got = await repo.query_events(sources=["gmail"])
            assert {e.id for e in got} == {"a", "c"}
            # text filter (case-insensitive substring over serialized data)
            got = await repo.query_events(text="invoice")
            assert [e.id for e in got] == ["a"]
            # pagination
            page1 = await repo.query_events(limit=1, offset=0)
            page2 = await repo.query_events(limit=1, offset=1)
            assert page1[0].id != page2[0].id

    asyncio.run(exercise())


def test_count_events_matches_filters(tmp_path):
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    async def exercise() -> None:
        async with connect_db(tmp_path / "events.db") as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)

            await repo.upsert_events(
                [
                    _ev(
                        "a",
                        datetime(2026, 7, 1, 9, tzinfo=UTC),
                        "gmail",
                        "email",
                        {"x": 1},
                    ),
                    _ev(
                        "b",
                        datetime(2026, 7, 1, 10, tzinfo=UTC),
                        "github",
                        "commit",
                        {"x": 2},
                    ),
                ]
            )
            assert await repo.count_events(sources=["gmail"]) == 1
            assert await repo.count_events() == 2

    asyncio.run(exercise())

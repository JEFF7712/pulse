import asyncio
from datetime import UTC, datetime


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event

    return Event(
        id=id,
        timestamp=timestamp,
        source=source,
        event_type=event_type,
        data=data or {},
    )


def test_aggregate_daily_stats_groups_by_source_and_type(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics_repo = AnalyticsRepository(db)

            events = [
                _make_event(
                    "e1",
                    datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e2",
                    datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e3",
                    datetime(2026, 3, 10, 11, 0, tzinfo=UTC),
                    "calendar",
                    "event.created",
                ),
                _make_event(
                    "e4",
                    datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
                    "gmail",
                    "email.sent",
                ),
            ]
            await event_repo.upsert_events(events)
            await analytics_repo.aggregate_daily_stats("2026-03-10")
            stats = await analytics_repo.get_daily_stats("2026-03-10")
            return stats

    stats = asyncio.run(exercise())

    by_key = {(s["source"], s["event_type"]): s for s in stats}
    assert ("gmail", "email.received") in by_key
    assert by_key[("gmail", "email.received")]["count"] == 2
    assert by_key[("gmail", "email.received")]["first_at"].startswith("2026-03-10T09")
    assert by_key[("gmail", "email.received")]["last_at"].startswith("2026-03-10T10")
    assert ("calendar", "event.created") in by_key
    assert by_key[("calendar", "event.created")]["count"] == 1
    assert ("gmail", "email.sent") in by_key
    assert by_key[("gmail", "email.sent")]["count"] == 1


def test_aggregate_time_blocks_buckets_events_into_2h_blocks(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics_repo = AnalyticsRepository(db)

            events = [
                # 9:30 => block 4 (hour 9 / 2 = 4)
                _make_event(
                    "e1",
                    datetime(2026, 3, 10, 9, 30, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                # 10:15 => block 5 (hour 10 / 2 = 5)
                _make_event(
                    "e2",
                    datetime(2026, 3, 10, 10, 15, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                # 22:30 => block 11 (hour 22 / 2 = 11)
                _make_event(
                    "e3",
                    datetime(2026, 3, 10, 22, 30, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
            ]
            await event_repo.upsert_events(events)
            await analytics_repo.aggregate_time_blocks("2026-03-10")
            blocks = await analytics_repo.get_time_blocks("2026-03-10")
            return blocks

    blocks = asyncio.run(exercise())

    by_block = {b["block"]: b for b in blocks}
    assert 4 in by_block
    assert by_block[4]["count"] == 1
    assert by_block[4]["source"] == "gmail"
    assert 5 in by_block
    assert by_block[5]["count"] == 1
    assert 11 in by_block
    assert by_block[11]["count"] == 1


def test_aggregate_weekly_baselines_computes_averages(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            analytics_repo = AnalyticsRepository(db)

            # 7 events across 3 days in a week starting 2026-03-09 (Mon)
            events = [
                _make_event(
                    "e1",
                    datetime(2026, 3, 9, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e2",
                    datetime(2026, 3, 9, 10, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e3",
                    datetime(2026, 3, 9, 11, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e4",
                    datetime(2026, 3, 10, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e5",
                    datetime(2026, 3, 11, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e6",
                    datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
                _make_event(
                    "e7",
                    datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                ),
            ]
            await event_repo.upsert_events(events)
            await analytics_repo.aggregate_weekly_baselines("2026-03-09")
            baselines = await analytics_repo.get_weekly_baselines("2026-03-09")
            return baselines

    baselines = asyncio.run(exercise())

    assert len(baselines) == 1
    baseline = baselines[0]
    assert baseline["source"] == "gmail"
    assert baseline["event_type"] == "email.received"
    assert baseline["total"] == 7
    assert abs(baseline["avg_daily"] - 1.0) < 1e-9


def test_upsert_and_list_insights(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics_repo = AnalyticsRepository(db)

            # Insert first insight
            await analytics_repo.upsert_insight(
                id="ins-1",
                title="Gmail spike",
                status="new",
                confidence="high",
                first_seen="2026-03-10",
                last_seen="2026-03-10",
                vault_path="insights/gmail-spike.md",
            )

            # Insert second insight with different status
            await analytics_repo.upsert_insight(
                id="ins-2",
                title="Calendar gap",
                status="reviewed",
                confidence="medium",
                first_seen="2026-03-09",
                last_seen="2026-03-11",
                vault_path="insights/calendar-gap.md",
            )

            # List all
            all_insights = await analytics_repo.list_insights()

            # List filtered by status
            new_insights = await analytics_repo.list_insights(status="new")
            reviewed_insights = await analytics_repo.list_insights(status="reviewed")

            # Upsert updates existing: change status of ins-1 to "archived"
            await analytics_repo.upsert_insight(
                id="ins-1",
                title="Gmail spike",
                status="archived",
                confidence="high",
                first_seen="2026-03-10",
                last_seen="2026-03-12",
                vault_path="insights/gmail-spike.md",
            )

            updated_new = await analytics_repo.list_insights(status="new")
            archived = await analytics_repo.list_insights(status="archived")

            return all_insights, new_insights, reviewed_insights, updated_new, archived

    all_insights, new_insights, reviewed_insights, updated_new, archived = asyncio.run(
        exercise()
    )

    assert len(all_insights) == 2
    # ordered by last_seen DESC
    assert all_insights[0]["id"] == "ins-2"  # last_seen 2026-03-11 > 2026-03-10
    assert all_insights[1]["id"] == "ins-1"

    assert len(new_insights) == 1
    assert new_insights[0]["id"] == "ins-1"

    assert len(reviewed_insights) == 1
    assert reviewed_insights[0]["id"] == "ins-2"

    # After upsert, ins-1 is now archived, not new
    assert len(updated_new) == 0
    assert len(archived) == 1
    assert archived[0]["status"] == "archived"
    assert archived[0]["last_seen"] == "2026-03-12"

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

from pulse.domain.notifications import Notification


@dataclass(slots=True)
class RecordingChannel:
    notifications: list[Notification]

    def send(self, notification: Notification) -> bool:
        self.notifications.append(notification)
        return True


@dataclass(slots=True)
class RejectingChannel:
    notifications: list[Notification]

    def send(self, notification: Notification) -> bool:
        self.notifications.append(notification)
        return False


def test_run_morning_briefing_job_sends_one_notification_with_digest_lines(tmp_path):
    async def exercise() -> None:
        from pulse.domain.events import Event
        from pulse.jobs.runners import run_morning_briefing_job
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events.db"
        vault_path = tmp_path / "vault"
        channel = RecordingChannel(notifications=[])

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
                ]
            )

        result = await run_morning_briefing_job(
            day=date(2026, 3, 22),
            database_path=db_path,
            vault_path=vault_path,
            channel=channel,
        )

        assert result.status == "success"
        assert result.detail == "Sent morning briefing for 2026-03-22"
        assert len(channel.notifications) == 1

        notification = channel.notifications[0]
        assert notification.title == "Morning briefing for 2026-03-22"
        assert notification.category == "morning_briefing"
        assert "Team sync" in notification.body
        assert "Project update" in notification.body
        assert "No spending recorded." in notification.body

    asyncio.run(exercise())


def test_run_morning_briefing_job_returns_failure_when_delivery_is_rejected(tmp_path):
    async def exercise() -> None:
        from pulse.domain.events import Event
        from pulse.jobs.runners import run_morning_briefing_job
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "events.db"
        vault_path = tmp_path / "vault"
        channel = RejectingChannel(notifications=[])

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
                    )
                ]
            )

        result = await run_morning_briefing_job(
            day=date(2026, 3, 22),
            database_path=db_path,
            vault_path=vault_path,
            channel=channel,
        )

        assert result.status == "failed"
        assert result.detail == "Failed to send morning briefing for 2026-03-22"
        assert len(channel.notifications) == 1

    asyncio.run(exercise())

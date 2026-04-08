import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.main import create_app
from pulse.domain.notifications import Notification


@dataclass(slots=True)
class FakeChannel:
    notifications: list[Notification] = field(default_factory=list)

    def send(self, notification: Notification) -> bool:
        self.notifications.append(notification)
        return True


def test_backend_first_vertical_slice_records_reply_and_writes_digest(tmp_path) -> None:
    async def seed_and_run() -> Notification:
        from pulse.domain.events import Event
        from pulse.jobs.runners import run_daily_digest_job, run_morning_briefing_job
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "pulse.db"
        vault_path = tmp_path / "vault"
        channel = FakeChannel()

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EventRepository(db)
            await repository.upsert_events(
                [
                    Event(
                        id="calendar-1",
                        timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="calendar.event",
                        data={"title": "Team sync"},
                    ),
                    Event(
                        id="email-1",
                        timestamp=datetime(2026, 3, 22, 10, 30, tzinfo=UTC),
                        source="email",
                        event_type="email.received",
                        data={"subject": "Project update"},
                    ),
                ]
            )

        await run_daily_digest_job(
            day=date(2026, 3, 22),
            database_path=db_path,
            vault_path=vault_path,
        )
        await run_morning_briefing_job(
            day=date(2026, 3, 22),
            database_path=db_path,
            vault_path=vault_path,
            channel=channel,
        )

        assert len(channel.notifications) == 1
        return channel.notifications[0]

    notification = asyncio.run(seed_and_run())
    db_path = tmp_path / "pulse.db"
    vault_path = tmp_path / "vault"

    app = create_app(
        settings=Settings(database_path=str(db_path), vault_path=str(vault_path))
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "The email should mention the roadmap, not the project update.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": f"{notification.title}\n\n{notification.body}",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_corrections() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db

        async with connect_db(db_path) as db:
            cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch_corrections()) == [
        (
            "2026-03-22",
            "The email should mention the roadmap, not the project update.",
        )
    ]
    digest_text = (vault_path / "01-Daily" / "2026-03-22.md").read_text(
        encoding="utf-8"
    )
    assert "Team sync" in digest_text
    assert "Project update" in digest_text

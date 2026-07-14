import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pulse.app.config import PulseConfig
from pulse.domain.correction_applications import CorrectionApplication
from pulse.domain.corrections import Correction
from pulse.domain.notifications import Notification


def test_corrections_backlog_notify_respects_cooldown(tmp_path: Path) -> None:
    sent: list[Notification] = []

    class Ch:
        def send(self, n: Notification) -> bool:
            sent.append(n)
            return True

    async def seed_db(db_path: Path) -> None:
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        now = datetime(2026, 3, 27, 12, 0, tzinfo=UTC)
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cr = CorrectionRepository(db)
            ar = CorrectionApplicationRepository(db)
            await cr.add(
                Correction(
                    id="c1",
                    context_id="x",
                    message_text="m",
                    created_at=now,
                )
            )
            await ar.add(
                CorrectionApplication(
                    id="a1",
                    correction_id="c1",
                    status="needs_review",
                    target_type="none",
                    target_ref="",
                    operation="needs_review",
                    summary="s",
                    error_message=None,
                    created_at=now,
                    updated_at=now,
                )
            )

    async def go():
        db_path = tmp_path / "c.db"
        await seed_db(db_path)
        cfg = PulseConfig(
            database_path=str(db_path),
            notify_on_corrections_backlog=True,
            corrections_backlog_alert_cooldown="1h",
            telegram_bot_token="x",
            telegram_chat_id="y",
        )
        from pulse.jobs.corrections_notifications import (
            notify_corrections_backlog_if_needed,
        )

        with patch(
            "pulse.jobs.corrections_notifications.build_notification_channel",
            return_value=Ch(),
        ):
            await notify_corrections_backlog_if_needed(cfg)
            await notify_corrections_backlog_if_needed(cfg)

    asyncio.run(go())
    assert len(sent) == 1
    assert "correction backlog" in sent[0].title.lower()
    assert sent[0].category == "operations"

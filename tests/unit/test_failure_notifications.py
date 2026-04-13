import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from pulse.app.config import PulseConfig
from pulse.domain.notifications import Notification


class _RecordingChannel:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return True


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "t.db"


def test_notify_skips_when_disabled(db_path: Path) -> None:
    from pulse.jobs.failure_notifications import notify_scheduled_job_failure

    ch = _RecordingChannel()
    cfg = PulseConfig(
        database_path=str(db_path),
        notify_on_job_failure=False,
        telegram_bot_token="x",
        telegram_chat_id="y",
    )

    async def go():
        with patch(
            "pulse.jobs.failure_notifications.build_notification_channel",
            return_value=ch,
        ):
            await notify_scheduled_job_failure(
                cfg, "discovery_daily", RuntimeError("boom")
            )

    asyncio.run(go())
    assert ch.sent == []


def test_notify_sends_when_enabled_and_respects_cooldown(db_path: Path) -> None:
    from pulse.jobs.failure_notifications import notify_scheduled_job_failure

    ch = _RecordingChannel()
    cfg = PulseConfig(
        database_path=str(db_path),
        notify_on_job_failure=True,
        job_failure_alert_cooldown="1h",
        telegram_bot_token="x",
        telegram_chat_id="y",
    )

    async def go():
        with patch(
            "pulse.jobs.failure_notifications.build_notification_channel",
            return_value=ch,
        ):
            await notify_scheduled_job_failure(
                cfg, "discovery_daily", RuntimeError("first")
            )
            await notify_scheduled_job_failure(
                cfg, "discovery_daily", RuntimeError("second")
            )

    asyncio.run(go())
    assert len(ch.sent) == 1
    assert ch.sent[0].category == "operations"
    assert "discovery_daily" in ch.sent[0].title
    assert "first" in ch.sent[0].body


def test_notify_different_job_keys_both_send(db_path: Path) -> None:
    from pulse.jobs.failure_notifications import notify_scheduled_job_failure

    ch = _RecordingChannel()
    cfg = PulseConfig(
        database_path=str(db_path),
        notify_on_job_failure=True,
        job_failure_alert_cooldown="1h",
        telegram_bot_token="x",
        telegram_chat_id="y",
    )

    async def go():
        with patch(
            "pulse.jobs.failure_notifications.build_notification_channel",
            return_value=ch,
        ):
            await notify_scheduled_job_failure(
                cfg, "discovery_daily", RuntimeError("a")
            )
            await notify_scheduled_job_failure(
                cfg, "discovery_weekly", RuntimeError("b")
            )

    asyncio.run(go())
    assert len(ch.sent) == 2


def test_invalid_cooldown_falls_back_to_six_hours(db_path: Path) -> None:
    from pulse.jobs.failure_notifications import notify_scheduled_job_failure

    ch = _RecordingChannel()
    cfg = PulseConfig(
        database_path=str(db_path),
        notify_on_job_failure=True,
        job_failure_alert_cooldown="not-a-duration",
        telegram_bot_token="x",
        telegram_chat_id="y",
    )

    async def go():
        with patch(
            "pulse.jobs.failure_notifications.build_notification_channel",
            return_value=ch,
        ):
            await notify_scheduled_job_failure(cfg, "aggregation", ValueError("e"))

    asyncio.run(go())
    assert len(ch.sent) == 1

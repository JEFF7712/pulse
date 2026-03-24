from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import date

from pulse.app.config import Settings
from pulse.jobs.runners import JobResult


def test_build_scheduler_registers_core_jobs():
    from pulse.jobs.scheduler import build_scheduler

    scheduler = build_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert isinstance(scheduler, AsyncIOScheduler)
    assert set(jobs) == {
        "daily_digest",
        "morning_briefing",
    }

    daily_digest = jobs["daily_digest"]
    assert isinstance(daily_digest.trigger, IntervalTrigger)
    assert daily_digest.trigger.interval.days == 1
    assert daily_digest.trigger.interval.seconds == 0

    morning_briefing = jobs["morning_briefing"]
    assert isinstance(morning_briefing.trigger, CronTrigger)
    fields = {field.name: str(field) for field in morning_briefing.trigger.fields}
    assert fields["hour"] == "8"
    assert fields["minute"] == "0"
    assert fields["second"] == "0"


def test_daily_digest_job_calls_runner_with_resolved_settings(monkeypatch):
    import asyncio

    from pulse.jobs import scheduler

    settings = Settings(
        database_path="/tmp/pulse.db",
        vault_path="/tmp/vault",
        timezone="UTC",
    )
    expected_day = date(2026, 3, 22)
    captured: dict[str, object] = {}

    monkeypatch.setattr(scheduler, "_resolve_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "_resolve_current_day", lambda _: expected_day)

    async def fake_run_daily_digest_job(*, day, database_path, vault_path):
        captured.update(
            day=day,
            database_path=database_path,
            vault_path=vault_path,
        )
        return JobResult(status="success", detail="ok")

    monkeypatch.setattr(scheduler, "run_daily_digest_job", fake_run_daily_digest_job)

    result = asyncio.run(scheduler._daily_digest_job())

    assert result == JobResult(status="success", detail="ok")
    assert captured == {
        "day": expected_day,
        "database_path": "/tmp/pulse.db",
        "vault_path": "/tmp/vault",
    }


def test_morning_briefing_job_calls_runner_with_optional_telegram_channel(monkeypatch):
    import asyncio

    from pulse.jobs import scheduler

    settings = Settings(
        database_path="/tmp/pulse.db",
        vault_path="/tmp/vault",
        timezone="UTC",
        telegram_bot_token="token",
        telegram_chat_id="chat-id",
    )
    expected_day = date(2026, 3, 22)
    channel = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(scheduler, "_resolve_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "_resolve_current_day", lambda _: expected_day)
    monkeypatch.setattr(scheduler, "_build_telegram_channel", lambda _: channel)

    async def fake_run_morning_briefing_job(*, day, database_path, vault_path, channel):
        captured.update(
            day=day,
            database_path=database_path,
            vault_path=vault_path,
            channel=channel,
        )
        return JobResult(status="success", detail="sent")

    monkeypatch.setattr(
        scheduler, "run_morning_briefing_job", fake_run_morning_briefing_job
    )

    result = asyncio.run(scheduler._morning_briefing_job())

    assert result == JobResult(status="success", detail="sent")
    assert captured == {
        "day": expected_day,
        "database_path": "/tmp/pulse.db",
        "vault_path": "/tmp/vault",
        "channel": channel,
    }


def test_morning_briefing_job_skips_when_telegram_is_not_configured(monkeypatch):
    import asyncio

    from pulse.jobs import scheduler

    settings = Settings(
        database_path="/tmp/pulse.db",
        vault_path="/tmp/vault",
        timezone="UTC",
    )
    expected_day = date(2026, 3, 22)

    monkeypatch.setattr(scheduler, "_resolve_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "_resolve_current_day", lambda _: expected_day)

    async def fail_if_called(**kwargs):
        raise AssertionError(f"runner should not be called: {kwargs}")

    monkeypatch.setattr(scheduler, "run_morning_briefing_job", fail_if_called)

    result = asyncio.run(scheduler._morning_briefing_job())

    assert result == JobResult(
        status="skipped",
        detail="Skipped morning briefing for 2026-03-22: Telegram channel not configured",
    )

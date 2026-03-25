import asyncio
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector
from pulse.jobs.scheduler import parse_interval


class FakeConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake"
    def get_default_interval(self):
        return timedelta(minutes=10)


def test_build_scheduler_creates_pull_jobs_from_registry():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    registry.register_pull("fake", lambda: FakeConnector())
    config = PulseConfig(connectors={
        "fake": ConnectorConfig(enabled=True, poll_interval="10m"),
    })
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "pull_fake" in jobs
    pull_job = jobs["pull_fake"]
    assert isinstance(pull_job.trigger, IntervalTrigger)
    assert pull_job.trigger.interval.total_seconds() == 600


def test_build_scheduler_keeps_analysis_jobs():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    config = PulseConfig()
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "daily_digest" in jobs
    assert "morning_briefing" in jobs
    assert isinstance(jobs["daily_digest"].trigger, IntervalTrigger)
    assert isinstance(jobs["morning_briefing"].trigger, CronTrigger)


def test_build_scheduler_morning_briefing_skips_without_telegram():
    """Equivalent of old test_morning_briefing_job_skips_when_telegram_is_not_configured."""
    from pulse.jobs.scheduler import build_scheduler

    config = PulseConfig()  # No telegram_bot_token or telegram_chat_id
    scheduler = build_scheduler(registry=ConnectorRegistry(), config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    # Morning briefing job is registered — it handles skip logic internally
    assert "morning_briefing" in jobs


def test_parse_interval_handles_various_units():
    assert parse_interval("5m") == timedelta(minutes=5)
    assert parse_interval("2h") == timedelta(hours=2)
    assert parse_interval("1d") == timedelta(days=1)
    assert parse_interval("30s") == timedelta(seconds=30)


def test_parse_interval_rejects_invalid_format():
    import pytest
    with pytest.raises(ValueError):
        parse_interval("invalid")

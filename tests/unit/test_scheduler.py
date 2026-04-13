import asyncio
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector
from pulse.jobs.intervals import parse_interval


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

    assert "aggregation" in jobs
    assert isinstance(jobs["aggregation"].trigger, IntervalTrigger)
    assert "discovery_daily" in jobs
    assert isinstance(jobs["discovery_daily"].trigger, CronTrigger)


def test_parse_interval_handles_various_units():
    assert parse_interval("5m") == timedelta(minutes=5)
    assert parse_interval("2h") == timedelta(hours=2)
    assert parse_interval("1d") == timedelta(days=1)
    assert parse_interval("30s") == timedelta(seconds=30)


def test_parse_interval_rejects_invalid_format():
    import pytest
    with pytest.raises(ValueError):
        parse_interval("invalid")


from pulse.connectors.spotify import SupplementaryPullMixin


class FakeSupplementaryConnector(Connector, SupplementaryPullMixin):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "supplementary_fake"
    def get_default_interval(self):
        return timedelta(minutes=30)
    def get_supplementary_jobs(self, config):
        return [("extra", timedelta(hours=2), self._extra_pull)]
    async def _extra_pull(self):
        return []


def test_build_scheduler_creates_supplementary_jobs():
    from pulse.jobs.scheduler import build_scheduler

    registry = ConnectorRegistry()
    registry.register_pull("supplementary_fake", lambda: FakeSupplementaryConnector())
    config = PulseConfig(connectors={
        "supplementary_fake": ConnectorConfig(enabled=True, poll_interval="30m"),
    })
    asyncio.run(registry.build_active_connectors(config))

    scheduler = build_scheduler(registry=registry, config=config)
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "pull_supplementary_fake" in jobs
    assert "pull_supplementary_fake_extra" in jobs
    supp_job = jobs["pull_supplementary_fake_extra"]
    assert isinstance(supp_job.trigger, IntervalTrigger)
    assert supp_job.trigger.interval.total_seconds() == 7200

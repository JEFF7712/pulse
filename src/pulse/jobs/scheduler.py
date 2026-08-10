import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.failure_notifications import notify_scheduled_job_failure
from pulse.jobs.intervals import parse_interval
from pulse.semantic.factory import semantic_enabled

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


logger = logging.getLogger(__name__)


def build_scheduler(
    registry: ConnectorRegistry | None = None,
    config: PulseConfig | None = None,
) -> AsyncIOScheduler:
    if config is None:
        config = load_config()

    # coalesce: collapse a backlog of suspend-missed runs into one.
    # misfire_grace_time: still fire a job that a laptop-sleep pushed past its
    # scheduled time, instead of silently dropping it (APScheduler's default).
    scheduler = AsyncIOScheduler(
        job_defaults={"coalesce": True, "misfire_grace_time": 3600},
    )

    # Pull connector jobs
    if registry is not None:
        for connector, cc in registry.get_pull_connectors():
            interval = parse_interval(cc.poll_interval)
            scheduler.add_job(
                _make_pull_job(connector, config),
                trigger=IntervalTrigger(seconds=int(interval.total_seconds())),
                id=f"pull_{connector.get_source_name()}",
            )

            # Supplementary jobs (if connector supports them)
            if hasattr(connector, "get_supplementary_jobs"):
                for suffix, supp_interval, job_fn in connector.get_supplementary_jobs(
                    cc
                ):
                    sup_key = f"pull_{connector.get_source_name()}_{suffix}"
                    scheduler.add_job(
                        _make_supplementary_job(job_fn, config, sup_key),
                        trigger=IntervalTrigger(
                            seconds=int(supp_interval.total_seconds())
                        ),
                        id=sup_key,
                    )

    # Aggregation job — hourly
    scheduler.add_job(
        _make_aggregation_job(config),
        "interval",
        hours=1,
        id="aggregation",
    )

    if config.discovery is not None and config.discovery.enabled:
        from apscheduler.triggers.cron import CronTrigger

        hh, mm = (config.discovery.at.split(":") + ["0"])[:2]
        scheduler.add_job(
            _make_discovery_job(config),
            trigger=CronTrigger(hour=int(hh), minute=int(mm), timezone=config.timezone),
            id="discovery",
            # A check missed while the laptop slept should still run on the next wake.
            # The check itself is cheap and usually finds nothing, so a late run costs
            # nothing; skipping one could drop the day a pattern first became visible.
            misfire_grace_time=None,
        )

        # Novelty detection compares against embeddings, so they have to keep up with
        # ingest. `pulse embed` alone is a one-off backfill: without this job the
        # newest events — the ones any discovery pass is about — are never embedded.
        if semantic_enabled(config):
            scheduler.add_job(
                _make_embed_job(config),
                "interval",
                hours=6,
                id="embed",
            )

    return scheduler


def _make_pull_job(connector, config):
    source = connector.get_source_name()
    job_key = f"pull_{source}"

    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        try:
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                sync_state = SyncStateRepository(db)

                cursor = await sync_state.load(source)
                since = datetime.fromisoformat(cursor) if cursor else None

                events = await connector.pull(since=since)
                if events:
                    await event_repo.upsert_events(events)
                    # Prefer connector-provided sync timestamp (e.g. calendar
                    # uses pull time to avoid future-event cursor drift).
                    if hasattr(connector, "get_sync_timestamp"):
                        ts = connector.get_sync_timestamp()
                    else:
                        ts = max(e.timestamp for e in events)
                    await sync_state.save(source, ts.isoformat())
        except Exception as e:
            await notify_scheduled_job_failure(config, job_key, e)
            logger.exception("Scheduled pull failed: %s", source)
            raise

    return job


def _make_supplementary_job(job_fn, config, job_key: str):
    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        try:
            events = await job_fn()
            if events:
                async with connect_db(config.database_path) as db:
                    await bootstrap_schema(db)
                    event_repo = EventRepository(db)
                    await event_repo.upsert_events(events)
        except Exception as e:
            await notify_scheduled_job_failure(config, job_key, e)
            logger.exception("Supplementary job failed: %s", job_key)
            raise

    return job


def _make_aggregation_job(config):
    async def job():
        from pulse.jobs.runners import run_aggregation_job

        try:
            day = _resolve_current_day(config)
            result = await run_aggregation_job(
                day=day,
                database_path=config.database_path,
                timezone=config.timezone,
            )
            return result
        except Exception as e:
            await notify_scheduled_job_failure(config, "aggregation", e)
            logger.exception("Aggregation job failed")
            raise

    return job


def _make_discovery_job(config):
    async def job():
        from pulse.jobs.discovery import run_discovery
        from pulse.notifications.factory import build_notification_channel

        try:
            channel = build_notification_channel(config)
            return await run_discovery(config, channel=channel)
        except Exception as e:
            await notify_scheduled_job_failure(config, "discovery", e)
            logger.exception("Discovery job failed")
            raise

    return job


def _make_embed_job(config):
    async def job():
        from pulse.jobs.runners import run_embed_job

        try:
            return await run_embed_job(config)
        except Exception as e:
            await notify_scheduled_job_failure(config, "embed", e)
            logger.exception("Embedding job failed")
            raise

    return job


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()

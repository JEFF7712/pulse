import logging
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.failure_notifications import notify_scheduled_job_failure
from pulse.jobs.intervals import parse_interval

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

    scheduler = AsyncIOScheduler()

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


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()

import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.failure_notifications import notify_scheduled_job_failure
from pulse.jobs.intervals import parse_interval
from pulse.jobs.runners import JobResult
from pulse.llm.factory import (
    create_providers_from_config,
    discovery_model_for_discovery,
    summarization_model_for_source_summaries,
)
from pulse.notifications.factory import build_notification_channel

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


logger = logging.getLogger(__name__)


def _log_llm_related_job_failure(job_label: str, exc: Exception) -> None:
    from pulse.llm.anthropic_errors import user_message_for_anthropic_exception

    hint = user_message_for_anthropic_exception(exc)
    if hint:
        logger.error("%s: %s", job_label, hint, exc_info=exc)
    else:
        logger.exception("%s failed", job_label)


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

    # Discovery jobs
    scheduler.add_job(
        _make_discovery_job("daily", config),
        "cron",
        hour=23,
        id="discovery_daily",
    )
    scheduler.add_job(
        _make_discovery_job("weekly", config),
        "cron",
        day_of_week="sun",
        hour=20,
        id="discovery_weekly",
    )
    scheduler.add_job(
        _make_discovery_job("monthly", config),
        "cron",
        day=1,
        hour=10,
        id="discovery_monthly",
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
            return await run_aggregation_job(
                day=day,
                database_path=config.database_path,
                timezone=config.timezone,
            )
        except Exception as e:
            await notify_scheduled_job_failure(config, "aggregation", e)
            logger.exception("Aggregation job failed")
            raise

    return job


def _make_discovery_job(cadence, config):
    async def job():
        try:
            from pulse.jobs.runners import run_discovery_job

            day = _resolve_current_day(config)
            _, disc_llm = create_providers_from_config(config)

            if disc_llm is None:
                return JobResult(
                    status="skipped",
                    detail=f"Discovery ({cadence}) skipped: no LLM provider configured",
                )

            channel = build_notification_channel(config)
            return await run_discovery_job(
                cadence=cadence,
                target_date=day,
                database_path=config.database_path,
                vault_path=config.vault_path,
                llm=disc_llm,
                timezone=config.timezone,
                notification_channel=channel,
                summarization_model=summarization_model_for_source_summaries(config)
                or "",
                discovery_model=discovery_model_for_discovery(config) or "",
            )
        except Exception as e:
            await notify_scheduled_job_failure(
                config, f"discovery_{cadence}", e
            )
            _log_llm_related_job_failure(f"discovery_{cadence}", e)
            raise

    return job


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()

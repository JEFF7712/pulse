import logging
import re
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.runners import run_daily_digest_job, run_morning_briefing_job, JobResult
from pulse.llm.factory import (
    create_providers_from_config,
    discovery_model_for_discovery,
    summarization_model_for_digest,
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


def parse_interval(interval_str: str) -> timedelta:
    match = re.fullmatch(r"(\d+)\s*(m|h|d|s)", interval_str.strip())
    if not match:
        raise ValueError(f"Invalid interval format: '{interval_str}'")
    value = int(match.group(1))
    unit = match.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: value})


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
                for suffix, supp_interval, job_fn in connector.get_supplementary_jobs(cc):
                    scheduler.add_job(
                        _make_supplementary_job(job_fn, config),
                        trigger=IntervalTrigger(seconds=int(supp_interval.total_seconds())),
                        id=f"pull_{connector.get_source_name()}_{suffix}",
                    )

    # Analysis jobs (unchanged)
    scheduler.add_job(
        _make_daily_digest_job(config),
        "interval",
        days=1,
        id="daily_digest",
    )
    scheduler.add_job(
        _make_morning_briefing_job(config),
        "cron",
        hour=8,
        minute=0,
        id="morning_briefing",
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
    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            source = connector.get_source_name()
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

    return job


def _make_supplementary_job(job_fn, config):
    async def job():
        from pulse.store.db import connect_db
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        events = await job_fn()
        if events:
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                await event_repo.upsert_events(events)

    return job


def _make_daily_digest_job(config):
    async def job():
        try:
            day = _resolve_current_day(config)

            summ_llm, _ = create_providers_from_config(config)

            return await run_daily_digest_job(
                day=day,
                database_path=config.database_path,
                vault_path=config.vault_path,
                llm=summ_llm,
                summarization_model=summarization_model_for_digest(config),
            )
        except Exception as e:
            _log_llm_related_job_failure("daily_digest", e)
            raise
    return job


def _make_morning_briefing_job(config):
    async def job():
        try:
            day = _resolve_current_day(config)
            channel = build_notification_channel(config)
            if channel is None:
                return JobResult(
                    status="skipped",
                    detail=(
                        f"Skipped morning briefing for {day.isoformat()}: "
                        "no notification channel configured"
                    ),
                )
            summ_llm, _ = create_providers_from_config(config)
            return await run_morning_briefing_job(
                day=day,
                database_path=config.database_path,
                vault_path=config.vault_path,
                channel=channel,
                llm=summ_llm,
                summarization_model=summarization_model_for_digest(config),
            )
        except Exception as e:
            _log_llm_related_job_failure("morning_briefing", e)
            raise

    return job


def _make_aggregation_job(config):
    async def job():
        from pulse.jobs.runners import run_aggregation_job
        day = _resolve_current_day(config)
        return await run_aggregation_job(day=day, database_path=config.database_path)
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
                notification_channel=channel,
                summarization_model=summarization_model_for_digest(config),
                discovery_model=discovery_model_for_discovery(config),
            )
        except Exception as e:
            _log_llm_related_job_failure(f"discovery_{cadence}", e)
            raise

    return job


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()

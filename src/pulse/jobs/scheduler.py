import re
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.registry import ConnectorRegistry
from pulse.jobs.runners import run_daily_digest_job, run_morning_briefing_job, JobResult
from pulse.notifications.telegram import TelegramChannel

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


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
                latest = max(e.timestamp for e in events)
                await sync_state.save(source, latest.isoformat())

    return job


def _make_daily_digest_job(config):
    async def job():
        day = _resolve_current_day(config)
        return await run_daily_digest_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
        )
    return job


def _make_morning_briefing_job(config):
    async def job():
        day = _resolve_current_day(config)
        channel = _build_telegram_channel(config)
        if channel is None:
            return JobResult(
                status="skipped",
                detail=f"Skipped morning briefing for {day.isoformat()}: Telegram channel not configured",
            )
        return await run_morning_briefing_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            channel=channel,
        )
    return job


def _resolve_current_day(config: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(config.timezone)).date()


def _build_telegram_channel(config: PulseConfig) -> TelegramChannel | None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        return None
    return TelegramChannel(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )

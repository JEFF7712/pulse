from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.jobs.runners import JobResult
from pulse.jobs.runners import run_daily_digest_job
from pulse.jobs.runners import run_morning_briefing_job
from pulse.notifications.telegram import TelegramChannel

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_daily_digest_job, "interval", days=1, id="daily_digest")
    scheduler.add_job(
        _morning_briefing_job,
        "cron",
        hour=8,
        minute=0,
        id="morning_briefing",
    )
    return scheduler


async def _daily_digest_job() -> JobResult:
    settings = _resolve_settings()
    return await run_daily_digest_job(
        day=_resolve_current_day(settings),
        database_path=settings.database_path,
        vault_path=settings.vault_path,
    )


async def _morning_briefing_job() -> JobResult:
    settings = _resolve_settings()
    day = _resolve_current_day(settings)
    channel = _build_telegram_channel(settings)
    if channel is None:
        return JobResult(
            status="skipped",
            detail=(
                f"Skipped morning briefing for {day.isoformat()}: "
                "Telegram channel not configured"
            ),
        )

    return await run_morning_briefing_job(
        day=day,
        database_path=settings.database_path,
        vault_path=settings.vault_path,
        channel=channel,
    )


def _resolve_settings() -> Settings:
    return get_settings()


def _resolve_current_day(settings: Settings) -> date:
    if ZoneInfo is None:
        return date.today()

    return datetime.now(ZoneInfo(settings.timezone)).date()


def _build_telegram_channel(settings: Settings) -> TelegramChannel | None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return None

    return TelegramChannel(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

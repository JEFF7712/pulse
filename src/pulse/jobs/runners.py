from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulse.analysis.briefing import build_morning_briefing
from pulse.domain.notifications import Notification
from pulse.domain.notifications import append_reply_context
from pulse.domain.notifications import NotificationChannel
from pulse.analysis.summarizer import DailySummarizer
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.vault.writer import write_daily_digest


@dataclass(slots=True)
class JobResult:
    status: str
    detail: str


async def run_daily_digest_job(
    day: date, database_path: str | Path, vault_path: str | Path
) -> JobResult:
    summary = await _build_daily_summary(day=day, database_path=database_path)
    output_path = write_daily_digest(
        vault_root=Path(vault_path),
        date_slug=day.isoformat(),
        content=summary.markdown,
    )
    return JobResult(status="success", detail=str(output_path))


async def run_morning_briefing_job(
    day: date,
    database_path: str | Path,
    vault_path: str | Path,
    channel: NotificationChannel,
) -> JobResult:
    summary = await _build_daily_summary(day=day, database_path=database_path)
    notification = build_morning_briefing(day=day, digest_markdown=summary.markdown)
    notification = _attach_reply_context(notification)
    delivered = channel.send(notification)
    if not delivered:
        return JobResult(
            status="failed",
            detail=f"Failed to send morning briefing for {day.isoformat()}",
        )
    return JobResult(
        status="success", detail=f"Sent morning briefing for {day.isoformat()}"
    )


async def _build_daily_summary(
    day: date,
    database_path: str | Path,
):
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        events = await repository.list_events_for_day(day.isoformat())

    return await DailySummarizer().summarize(day, events)


def _attach_reply_context(notification: Notification) -> Notification:
    if notification.context_id is None:
        return notification

    return Notification(
        title=notification.title,
        body=append_reply_context(notification.body, notification.context_id),
        category=notification.category,
        context_id=notification.context_id,
        priority=notification.priority,
    )

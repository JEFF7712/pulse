from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulse.analysis.briefing import build_morning_briefing
from pulse.domain.notifications import Notification
from pulse.domain.notifications import append_reply_context
from pulse.domain.notifications import NotificationChannel
from pulse.analysis.summarizer import DailySummarizer
from pulse.store.analytics import AnalyticsRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.vault.writer import write_daily_digest


@dataclass(slots=True)
class JobResult:
    status: str
    detail: str


async def run_daily_digest_job(
    day: date, database_path: str | Path, vault_path: str | Path,
    llm=None, summarization_model: str = "claude-haiku-4-5-20251001",
) -> JobResult:
    summary = await _build_daily_summary(
        day=day, database_path=database_path,
        llm=llm, summarization_model=summarization_model,
    )
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
    llm=None,
    summarization_model: str = "claude-haiku-4-5-20251001",
):
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        events = await repository.list_events_for_day(day.isoformat())

    summarizer = DailySummarizer(llm=llm, summarization_model=summarization_model)
    if llm is not None:
        return await summarizer.summarize_async(day, events)
    return summarizer.summarize(day, events)


async def run_aggregation_job(day: date, database_path: str | Path) -> JobResult:
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        analytics = AnalyticsRepository(db)
        await analytics.aggregate_day(day.isoformat())
    return JobResult(status="success", detail=f"Aggregated stats for {day.isoformat()}")


async def run_discovery_job(
    cadence: str,
    target_date: date,
    database_path: str | Path,
    vault_path: str | Path,
    llm,
    notification_channel=None,
    summarization_model: str = "claude-haiku-4-5-20251001",
    discovery_model: str = "claude-sonnet-4-5-20250514",
) -> JobResult:
    from pulse.analysis.discovery import DiscoveryEngine

    engine = DiscoveryEngine(
        database_path=database_path,
        vault_root=Path(vault_path),
        llm=llm,
        notification_channel=notification_channel,
        summarization_model=summarization_model,
        discovery_model=discovery_model,
    )
    result = await engine.run_discovery(cadence=cadence, target_date=target_date)
    return JobResult(
        status="success",
        detail=(
            f"Discovery ({cadence}): {result.new_patterns} new patterns, "
            f"{result.updated_patterns} updated, {result.notifications_sent} notifications"
        ),
    )


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

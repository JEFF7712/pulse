from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulse.store.analytics import AnalyticsRepository
from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema
from pulse.vault.onboarding import ensure_vault_onboarding


@dataclass(slots=True)
class JobResult:
    status: str
    detail: str


async def run_aggregation_job(
    day: date, database_path: str | Path, timezone: str = "UTC"
) -> JobResult:
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        analytics = AnalyticsRepository(db)
        await analytics.aggregate_day(day.isoformat(), timezone=timezone)
    return JobResult(status="success", detail=f"Aggregated stats for {day.isoformat()}")


async def run_discovery_job(
    cadence: str,
    target_date: date,
    database_path: str | Path,
    vault_path: str | Path,
    llm,
    timezone: str = "UTC",
    notification_channel=None,
    summarization_model: str = "",
    discovery_model: str = "",
) -> JobResult:
    from pulse.analysis.discovery import DiscoveryEngine

    ensure_vault_onboarding(vault_path)

    engine = DiscoveryEngine(
        database_path=database_path,
        vault_root=Path(vault_path),
        llm=llm,
        timezone=timezone,
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

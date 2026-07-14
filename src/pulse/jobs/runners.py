from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pulse.store.analytics import AnalyticsRepository
from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema


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

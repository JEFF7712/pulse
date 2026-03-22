from dataclasses import dataclass
from datetime import date
from pathlib import Path

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
    output_path = await _run_daily_digest_job(
        day=day,
        database_path=database_path,
        vault_path=vault_path,
    )
    return JobResult(status="success", detail=str(output_path))


async def _run_daily_digest_job(
    day: date,
    database_path: str | Path,
    vault_path: str | Path,
) -> Path:
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        events = await repository.list_events_for_day(day.isoformat())

    summary = DailySummarizer().summarize(day, events)
    return write_daily_digest(
        vault_root=Path(vault_path),
        date_slug=day.isoformat(),
        content=summary.markdown,
    )

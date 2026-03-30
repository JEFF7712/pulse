import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from mcp.server.fastmcp import Context, FastMCP

from pulse.app.config_loader import load_config
from pulse.domain.events import Event
from pulse.jobs.runners import run_aggregation_job, run_daily_digest_job
from pulse.llm.factory import (
    create_providers_from_config,
    summarization_model_for_digest,
)
from pulse.mcp.context import PulseContext, open_pulse_context
from pulse.services.corrections import build_correction_service


def _parse_day(day: str) -> date | str:
    """Parse an ISO date string, returning a date or an error string."""
    try:
        return date.fromisoformat(day)
    except ValueError:
        return f"Invalid date '{day}'. Expected ISO format YYYY-MM-DD."


@asynccontextmanager
async def pulse_lifespan(server: FastMCP) -> AsyncIterator[PulseContext]:
    config = load_config(require_files=True)
    async with open_pulse_context(
        db_path=config.database_path,
        vault_path=config.vault_path,
        config=config,
    ) as ctx:
        yield ctx


mcp = FastMCP("pulse", lifespan=pulse_lifespan)


def _get_pulse_ctx(ctx: Context) -> PulseContext:
    """Extract PulseContext from the MCP request context's lifespan state."""
    return ctx.request_context.lifespan_context


@mcp.tool()
async def pulse_events_for_day(
    day: str | None = None, source: str | None = None, ctx: Context = None
) -> str:
    """Get all Pulse events for a specific day.

    Args:
        day: ISO date string (e.g. 2026-03-23). Defaults to today.
        source: Optional filter by source (e.g. gmail, calendar).
    """
    if day is None:
        day = date.today().isoformat()

    parsed = _parse_day(day)
    if isinstance(parsed, str):
        return parsed

    pulse_ctx = _get_pulse_ctx(ctx)
    events = await pulse_ctx.events.list_events_for_day(day)

    if source:
        events = [e for e in events if e.source == source]

    if not events:
        return f"No events found for {day}."

    return json.dumps(
        [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "source": e.source,
                "event_type": e.event_type,
                "data": e.data,
            }
            for e in events
        ],
        indent=2,
    )


@mcp.tool()
async def pulse_ingest_event(
    source: str,
    event_type: str,
    data: str,
    event_id: str | None = None,
    ctx: Context = None,
) -> str:
    """Manually push an event into the Pulse event store.

    Args:
        source: The data source (e.g. manual, gmail, calendar).
        event_type: The type of event (e.g. note, email.received).
        data: JSON string of event data.
        event_id: Optional custom ID. Auto-generated if omitted.
    """
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON in 'data': {exc}"
    eid = event_id or f"{source}:{uuid4()}"

    event = Event(
        id=eid,
        timestamp=datetime.now(UTC),
        source=source,
        event_type=event_type,
        data=parsed_data,
        metadata={},
    )

    pulse_ctx = _get_pulse_ctx(ctx)
    await pulse_ctx.events.upsert_events([event])

    return f"Event {eid} ingested successfully."


@mcp.tool()
async def pulse_correct(context_id: str, message_text: str, ctx: Context = None) -> str:
    """Record a correction or feedback about a Pulse insight.

    Args:
        context_id: The ID of the notification or digest being corrected.
        message_text: The correction text.
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    service = build_correction_service(
        pulse_ctx.corrections,
        config=pulse_ctx.config,
        correction_applications=pulse_ctx.correction_applications,
        vault_path=pulse_ctx.vault_path,
    )
    correction = await service.record_correction(context_id, message_text)

    return f"Correction {correction.id} recorded."


@mcp.tool()
async def pulse_digest(day: str | None = None, ctx: Context = None) -> str:
    """Generate a daily digest and save it to the vault.

    Args:
        day: ISO date string. Defaults to today.
    """
    if day is None:
        day = date.today().isoformat()

    target_date = _parse_day(day)
    if isinstance(target_date, str):
        return target_date
    pulse_ctx = _get_pulse_ctx(ctx)
    config = pulse_ctx.config if pulse_ctx.config is not None else load_config()
    summ_llm, _ = create_providers_from_config(config)
    model = summarization_model_for_digest(config) or ""

    await run_aggregation_job(
        day=target_date, database_path=pulse_ctx.database_path
    )
    job = await run_daily_digest_job(
        day=target_date,
        database_path=pulse_ctx.database_path,
        vault_path=pulse_ctx.vault_path,
        llm=summ_llm,
        summarization_model=model,
    )

    events = await pulse_ctx.events.list_events_for_day(day)
    return f"Digest for {day} written to {job.detail} ({len(events)} events)."


@mcp.tool()
async def pulse_read_digest(day: str, ctx: Context = None) -> str:
    """Read an existing daily digest from the vault.

    Args:
        day: ISO date string (e.g. 2026-03-23).
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    digest_path = Path(pulse_ctx.vault_path) / "01-Daily" / f"{day}.md"

    if not digest_path.exists():
        return f"No digest found for {day}."

    return digest_path.read_text(encoding="utf-8")


@mcp.tool()
async def pulse_connector_status(ctx: Context = None) -> str:
    """Check the sync state of all configured connectors."""
    pulse_ctx = _get_pulse_ctx(ctx)

    # Get all sources that have ever synced
    db_cursor = await pulse_ctx._db.execute(
        "SELECT source, cursor, updated_at FROM connector_sync_state ORDER BY source"
    )
    rows = await db_cursor.fetchall()
    await db_cursor.close()

    # Get event counts per source
    count_cursor = await pulse_ctx._db.execute(
        "SELECT source, COUNT(*) FROM events GROUP BY source"
    )
    count_rows = await count_cursor.fetchall()
    await count_cursor.close()
    event_counts = dict(count_rows)

    statuses = {}
    for source, cursor, updated_at in rows:
        statuses[source] = {
            "last_sync": cursor,
            "updated_at": updated_at,
            "event_count": event_counts.get(source, 0),
        }

    # Include enabled pull connectors that have not synced yet
    cfg = pulse_ctx.config
    if cfg:
        for name, cc in cfg.connectors.items():
            if not cc.enabled or name == "companion":
                continue
            if name not in statuses:
                statuses[name] = {
                    "last_sync": "never",
                    "updated_at": None,
                    "event_count": event_counts.get(name, 0),
                }

    return json.dumps(statuses, indent=2)


# --- Resources ---


@mcp.resource("pulse://events/today")
async def today_events_resource() -> str:
    """Today's events from all sources."""
    ctx = mcp.get_context()
    return await pulse_events_for_day(ctx=ctx)


@mcp.resource("pulse://connectors/status")
async def connectors_status_resource() -> str:
    """Current sync state of all connectors."""
    ctx = mcp.get_context()
    return await pulse_connector_status(ctx=ctx)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

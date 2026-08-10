import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import Context, FastMCP

from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.vault_memory import VaultMemory
from pulse.app.config_loader import load_config
from pulse.domain.events import Event
from pulse.mcp.context import PulseContext, open_pulse_context


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


def _context_timezone(pulse_ctx: PulseContext) -> str:
    if pulse_ctx.config is None:
        return "UTC"
    return pulse_ctx.config.timezone


def _today_for_timezone(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


_MAX_STR = 240


def _trim_value(v, full: bool):
    if full:
        return v
    if isinstance(v, str) and len(v) > _MAX_STR:
        return v[:_MAX_STR] + f"… (+{len(v) - _MAX_STR} chars)"
    if isinstance(v, list) and len(v) > 20:
        return v[:20] + [f"… (+{len(v) - 20} more)"]
    if isinstance(v, dict):
        return {k: _trim_value(val, full) for k, val in v.items()}
    return v


async def _maybe_semantic_query(pulse_ctx, start, end, source_list, text, limit):
    """Rank matching events by embedding similarity to ``text``.

    Returns ``(events, total)`` when semantic search is active, else ``None`` so
    the caller falls back to the substring path. Active only when ``text`` is set,
    semantic is enabled in config, and an embedder is present on the context.
    """
    if not text or getattr(pulse_ctx, "embedder", None) is None:
        return None
    from pulse.semantic.factory import semantic_enabled

    if pulse_ctx.config is None or not semantic_enabled(pulse_ctx.config):
        return None

    from pulse.semantic.search import rank_ids
    from pulse.store.embeddings import EmbeddingRepository

    candidate_ids = await pulse_ctx.events.query_event_ids(
        start=start, end=end, sources=source_list
    )
    if not candidate_ids:
        return [], 0
    emb_repo = EmbeddingRepository(pulse_ctx._db)
    candidates = await emb_repo.load_for_ids(candidate_ids)
    if not candidates:
        return None  # nothing embedded yet → let substring handle it
    query_vec = pulse_ctx.embedder.embed([text])[0]
    ranked_ids = rank_ids(query_vec, candidates, limit)
    by_id = await pulse_ctx.events.get_events_by_ids(ranked_ids)
    events = [by_id[i] for i in ranked_ids if i in by_id]
    return events, len(candidates)


@mcp.tool()
async def pulse_events_for_day(
    day: str | None = None, source: str | None = None, ctx: Context = None
) -> str:
    """Get all Pulse events for a specific day.

    Args:
        day: ISO date string (e.g. 2026-03-23). Defaults to today.
        source: Optional filter by source (e.g. gmail, calendar).
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    if day is None:
        day = _today_for_timezone(_context_timezone(pulse_ctx))

    parsed = _parse_day(day)
    if isinstance(parsed, str):
        return parsed

    events = await pulse_ctx.events.list_events_for_day(
        day, timezone=_context_timezone(pulse_ctx)
    )

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
async def pulse_query_events(
    start: str | None = None,
    end: str | None = None,
    sources: str | None = None,
    text: str | None = None,
    limit: int = 100,
    full: bool = False,
    ctx: Context = None,
) -> str:
    """Query events by time range, source(s), and text; newest first, paginated.

    Args:
        start: ISO datetime/date lower bound (inclusive). Optional.
        end: ISO datetime/date upper bound (exclusive). Optional.
        sources: comma-separated source names (e.g. "gmail,github"). Optional.
        text: case-insensitive substring over event data/type. Optional.
        limit: max events to return (default 100, hard cap 500).
        full: if true, return untrimmed event data.
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    limit = max(1, min(limit, 500))
    source_list = (
        [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    )

    semantic_events = await _maybe_semantic_query(
        pulse_ctx, start, end, source_list, text, limit
    )
    if semantic_events is not None:
        events, total = semantic_events
    else:
        total = await pulse_ctx.events.count_events(
            start=start, end=end, sources=source_list, text=text
        )
        events = await pulse_ctx.events.query_events(
            start=start, end=end, sources=source_list, text=text, limit=limit
        )
    payload = {
        "count": total,
        "returned": len(events),
        "truncated": total > len(events),
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "source": e.source,
                "event_type": e.event_type,
                "data": _trim_value(e.data, full),
            }
            for e in events
        ],
    }
    return json.dumps(payload, indent=2)


def _dc(obj):
    if is_dataclass(obj):
        return {k: _dc(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_dc(x) for x in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@mcp.tool()
async def pulse_digest(day: str | None = None, ctx: Context = None) -> str:
    """Deterministic day digest: per-source counts + clustered activity (no LLM).

    Args:
        day: ISO date (defaults to today).
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    tz = _context_timezone(pulse_ctx)
    if day is None:
        day = _today_for_timezone(tz)
    parsed = _parse_day(day)
    if isinstance(parsed, str):
        return parsed
    events = await pulse_ctx.events.list_events_for_day(day, timezone=tz)
    counts: dict[str, int] = {}
    for e in events:
        counts[e.source] = counts.get(e.source, 0) + 1
    preprocessed = EventPreprocessor().preprocess(events)
    return json.dumps(
        {
            "day": day,
            "total_events": len(events),
            "by_source": counts,
            "clusters": _dc(preprocessed),
        },
        indent=2,
        default=str,
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
async def pulse_coverage(ctx: Context = None) -> str:
    """Per-source coverage: last sync, event count, and freshness."""
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

    # Freshness: most-recent event timestamp per source
    fresh_cursor = await pulse_ctx._db.execute(
        "SELECT source, MAX(timestamp) FROM events GROUP BY source"
    )
    fresh_rows = await fresh_cursor.fetchall()
    await fresh_cursor.close()
    last_events = dict(fresh_rows)

    def _entry(source: str, *, last_sync, updated_at) -> dict:
        return {
            "last_sync": last_sync,
            "updated_at": updated_at,
            "event_count": event_counts.get(source, 0),
            "last_event": last_events.get(source),
        }

    statuses = {}
    for source, cursor, updated_at in rows:
        statuses[source] = _entry(source, last_sync=cursor, updated_at=updated_at)

    # Include sources that have events but no sync state
    for source in event_counts:
        if source not in statuses:
            statuses[source] = _entry(source, last_sync=None, updated_at=None)

    # Include enabled pull connectors that have not synced yet
    cfg = pulse_ctx.config
    if cfg:
        for name, cc in cfg.connectors.items():
            if not cc.enabled:
                continue
            if name not in statuses:
                statuses[name] = _entry(name, last_sync="never", updated_at=None)

    return json.dumps(statuses, indent=2)


def _vault(pulse_ctx: PulseContext) -> VaultMemory:
    return VaultMemory(pulse_ctx.vault_path)


@mcp.tool()
async def pulse_vault_read(path: str, ctx: Context = None) -> str:
    """Read a markdown note from the vault (returns '' if absent)."""
    try:
        return (
            _vault(_get_pulse_ctx(ctx)).read_note(path) or f"(empty or missing: {path})"
        )
    except ValueError as exc:
        return f"Error: {exc}"


@mcp.tool()
async def pulse_vault_list(ctx: Context = None) -> str:
    """List all markdown notes in the vault (relative paths)."""
    return json.dumps(_vault(_get_pulse_ctx(ctx)).list_notes(), indent=2)


@mcp.tool()
async def pulse_vault_write(path: str, content: str, ctx: Context = None) -> str:
    """Create or overwrite a markdown note in the vault."""
    try:
        p = _vault(_get_pulse_ctx(ctx)).write_note(path, content)
        return f"Wrote {p}."
    except ValueError as exc:
        return f"Error: {exc}"


@mcp.tool()
async def pulse_vault_append_section(
    path: str, heading: str, body: str, ctx: Context = None
) -> str:
    """Upsert a '## heading' section with the given body in a vault note."""
    try:
        p = _vault(_get_pulse_ctx(ctx)).append_section(path, heading, body)
        return f"Updated section {heading!r} in {p}."
    except ValueError as exc:
        return f"Error: {exc}"


@mcp.tool()
async def pulse_change_surface(
    window_end: str | None = None,
    window_days: int = 7,
    baseline_days: int = 56,
    ctx: Context = None,
) -> str:
    """What is different about a window versus the user's own trailing baseline.

    Deterministic, no LLM. Returns entities that are new, returning after dormancy,
    or off their usual rate, plus clusters of events whose text is unlike anything in
    the baseline. Start here rather than with a full digest: the digest tells you what
    happened, this tells you what changed, and only the latter can be new.

    An empty result is a normal and common outcome. It means nothing notable happened,
    and the correct response is to report nothing.

    Args:
        window_end: ISO date, last day of the window (defaults to today).
        window_days: Length of the window in days.
        baseline_days: Days of history before the window to compare against.
    """
    pulse_ctx = _get_pulse_ctx(ctx)
    tz = _context_timezone(pulse_ctx)
    if window_end is None:
        window_end = _today_for_timezone(tz)
    parsed = _parse_day(window_end)
    if isinstance(parsed, str):
        return parsed

    from pulse.services.change_detection import detect_changes

    surface = await detect_changes(
        pulse_ctx._db,
        window_end=parsed,
        timezone=tz,
        window_days=max(1, window_days),
        baseline_days=max(1, baseline_days),
    )
    return json.dumps(_dc(surface), indent=2, default=str)


# --- Patterns ---


@mcp.tool()
async def pulse_pattern_list(ctx: Context = None) -> str:
    """List recorded patterns with status, confidence and observation.

    Read this before proposing anything. A finding already on file is not a discovery,
    and re-reporting one is the single most common way these reviews become noise.
    """
    from pulse.analysis.pattern_gate import snapshot_patterns

    vault = _vault(_get_pulse_ctx(ctx))
    snaps = snapshot_patterns(vault.read_patterns())
    return json.dumps(
        [
            {
                "slug": slug,
                "title": snap.title,
                "status": snap.status,
                "observation": snap.observation,
                "evidence_count": len(snap.evidence),
            }
            for slug, snap in sorted(snaps.items())
        ],
        indent=2,
    )


@mcp.tool()
async def pulse_pattern_read(slug: str, ctx: Context = None) -> str:
    """Read one pattern's full markdown (returns '' if absent)."""
    try:
        return _vault(_get_pulse_ctx(ctx)).read_pattern_by_slug(slug) or (
            f"(no pattern: {slug})"
        )
    except ValueError as exc:
        return f"Error: {exc}"


@mcp.tool()
async def pulse_pattern_upsert(
    slug: str,
    title: str,
    observation: str,
    evidence: list[str],
    confidence: float = 0.5,
    status: str = "active",
    trend: str = "stable",
    ctx: Context = None,
) -> str:
    """Record a pattern, subject to a novelty check.

    The check is the point: a proposal too close to an existing pattern is rejected as
    a duplicate, and an update that merely restates the pattern's current observation
    is rejected as a restatement. Do not work around a rejection by rewording — a
    rejection means the finding is already on file.

    Never pass the *absence* of activity as evidence ("no such activity today"). A
    pattern that is not showing up should have its status set to inactive via
    pulse_pattern_set_status, not be fed negative evidence.

    Args:
        slug: Stable kebab-case identifier; reuse it to update an existing pattern.
        title: Short human-readable name.
        observation: What the pattern is, in a few sentences.
        evidence: Concrete grounding — counts, dates, entity names.
        confidence: 0.0-1.0.
        status: active | inactive.
        trend: increasing | decreasing | stable.
    """
    from pulse.analysis.pattern_gate import (
        find_duplicate,
        is_restatement,
        snapshot_patterns,
    )

    pulse_ctx = _get_pulse_ctx(ctx)
    vault = _vault(pulse_ctx)
    embedder = getattr(pulse_ctx, "embedder", None)
    existing = snapshot_patterns(vault.read_patterns())
    today = _today_for_timezone(_context_timezone(pulse_ctx))

    if not evidence:
        return "Rejected: a pattern needs at least one concrete piece of evidence."

    prior = existing.get(slug)
    if prior is None:
        duplicate = find_duplicate(title, observation, existing, embedder=embedder)
        if duplicate is not None:
            other, score = duplicate
            return (
                f"Rejected as duplicate of '{other}' (similarity {score:.2f}). "
                "Update that pattern instead, or drop this finding."
            )
    elif is_restatement(observation, prior.observation, embedder=embedder):
        return (
            f"Rejected as a restatement: '{slug}' already says this. Record an update "
            "only when the pattern has genuinely changed."
        )

    try:
        if prior is None:
            path = vault.write_pattern(
                slug=slug,
                title=title,
                status=status,
                confidence=confidence,
                first_seen=today,
                last_updated=today,
                observation=observation,
                evidence_log=list(evidence),
                trend=trend,
            )
            return f"Created pattern '{slug}' at {path}."
        path = vault.update_pattern(
            slug=slug,
            title=title,
            status=status,
            confidence=confidence,
            first_seen=today,
            last_updated=today,
            observation=observation,
            evidence_log=list(evidence),
            trend=trend,
        )
        return f"Updated pattern '{slug}' at {path}."
    except (ValueError, OSError) as exc:
        return f"Error: {exc}"


@mcp.tool()
async def pulse_pattern_set_status(slug: str, status: str, ctx: Context = None) -> str:
    """Set a pattern's status (active | inactive).

    Use this when a pattern stops showing up, instead of appending evidence that it
    was absent. Inactive patterns are moved to the vault archive.
    """
    try:
        path = _vault(_get_pulse_ctx(ctx)).update_pattern_status(slug, status)
        return f"Pattern '{slug}' is now {status} ({path})."
    except FileNotFoundError:
        return f"No pattern '{slug}'."
    except ValueError as exc:
        return f"Error: {exc}"


# --- Resources ---


@mcp.resource("pulse://digest/today")
async def digest_today_resource() -> str:
    """Today's deterministic digest (per-source counts + clusters)."""
    ctx = mcp.get_context()
    return await pulse_digest(ctx=ctx)


@mcp.resource("pulse://coverage")
async def coverage_resource() -> str:
    """Per-source coverage: last sync, event count, and freshness."""
    ctx = mcp.get_context()
    return await pulse_coverage(ctx=ctx)


@mcp.resource("pulse://vault/index")
async def vault_index_resource() -> str:
    """Index of markdown notes in the vault."""
    ctx = mcp.get_context()
    return await pulse_vault_list(ctx=ctx)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Load a window and its trailing baseline out of the store, and diff them."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from pulse.analysis.change_surface import ChangeSurface, build_change_surface
from pulse.domain.events import Event
from pulse.store.embeddings import EmbeddingRepository
from pulse.store.events import EventRepository

# Enough history for "new" and "dormant" to mean something without reaching back into
# a different phase of the user's life.
DEFAULT_BASELINE_DAYS = 56
DEFAULT_WINDOW_DAYS = 7
# Guard rails so a huge store cannot blow up memory or wall clock.
MAX_WINDOW_EVENTS = 4000
MAX_BASELINE_EVENTS = 40000


def _bounds(day: date, days: int, timezone: str) -> tuple[str, str]:
    tz = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    end = datetime.combine(day + timedelta(days=days), time.min, tzinfo=tz).astimezone(
        ZoneInfo("UTC")
    )
    return start.isoformat(), end.isoformat()


async def _load(
    events: EventRepository, start: str, end: str, limit: int
) -> list[Event]:
    return await events.query_events(start=start, end=end, limit=limit)


async def detect_changes(
    db: aiosqlite.Connection,
    *,
    window_end: date,
    timezone: str = "UTC",
    window_days: int = DEFAULT_WINDOW_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    use_embeddings: bool = True,
) -> ChangeSurface:
    """Build the change surface for the ``window_days`` ending on ``window_end``."""
    window_start = window_end - timedelta(days=window_days - 1)
    baseline_start = window_start - timedelta(days=baseline_days)

    events = EventRepository(db)
    win_from, win_to = _bounds(window_start, window_days, timezone)
    base_from, base_to = _bounds(baseline_start, baseline_days, timezone)

    window = await _load(events, win_from, win_to, MAX_WINDOW_EVENTS)
    baseline = await _load(events, base_from, base_to, MAX_BASELINE_EVENTS)

    vectors: dict[str, list[float]] = {}
    if use_embeddings:
        emb = EmbeddingRepository(db)
        ids = [e.id for e in window] + [e.id for e in baseline]
        vectors = dict(await emb.load_for_ids(ids))

    return build_change_surface(
        window,
        baseline,
        window_start=window_start,
        window_end=window_end,
        baseline_start=baseline_start,
        vectors=vectors or None,
    )

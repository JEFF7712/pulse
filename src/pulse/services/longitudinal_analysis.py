"""Load a long history out of the store and compute its longitudinal profile."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from pulse.analysis.longitudinal import LongitudinalProfile, build_longitudinal_profile
from pulse.store.events import EventRepository

# Structure needs a long horizon to exist at all; a quarter is the practical floor
# and a year lets seasonality and rotation show.
DEFAULT_HISTORY_DAYS = 400
# Guard rail: a very large store should not blow up memory in one pass.
MAX_EVENTS = 200_000


async def analyse_history(
    db: aiosqlite.Connection,
    *,
    as_of: date,
    timezone: str = "UTC",
    history_days: int = DEFAULT_HISTORY_DAYS,
    sources: list[str] | None = None,
) -> LongitudinalProfile:
    tz = ZoneInfo(timezone)
    start = as_of - timedelta(days=history_days)
    lo = datetime.combine(start, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    hi = datetime.combine(as_of + timedelta(days=1), time.min, tzinfo=tz).astimezone(
        ZoneInfo("UTC")
    )

    events = await EventRepository(db).query_events(
        start=lo.isoformat(), end=hi.isoformat(), sources=sources, limit=MAX_EVENTS
    )
    # Timestamps are stored in UTC; local-time structure (bedtime, hour-of-day) is
    # meaningless until they are converted to where the user actually lives.
    for event in events:
        event.timestamp = event.timestamp.astimezone(tz)

    return build_longitudinal_profile(events, as_of=as_of)

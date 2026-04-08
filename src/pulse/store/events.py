import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import aiosqlite

from pulse.domain.events import Event


def _local_day_bounds(day: str, timezone: str) -> tuple[str, str]:
    day_date = date.fromisoformat(day)
    tz = ZoneInfo(timezone)
    start = datetime.combine(day_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(
        day_date + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(UTC)
    return start.isoformat(), end.isoformat()


def _normalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("Event timestamps must be timezone-aware")
    return timestamp.astimezone(UTC)


class EventRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert_events(self, events: list[Event]) -> int:
        """Upsert events and return the number of genuinely new rows inserted."""
        if not events:
            return 0

        ids = [e.id for e in events]
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._db.execute(
            f"SELECT id FROM events WHERE id IN ({placeholders})", ids
        )
        existing = {row[0] for row in await cursor.fetchall()}
        await cursor.close()

        await self._db.executemany(
            """
            INSERT INTO events (
                id,
                timestamp,
                source,
                event_type,
                data,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                timestamp = excluded.timestamp,
                source = excluded.source,
                event_type = excluded.event_type,
                data = excluded.data,
                metadata = excluded.metadata
            """,
            [
                (
                    event.id,
                    _normalize_timestamp(event.timestamp).isoformat(),
                    event.source,
                    event.event_type,
                    json.dumps(event.data),
                    json.dumps(event.metadata),
                )
                for event in events
            ],
        )
        await self._db.commit()
        return len(events) - len(existing)

    async def list_events_for_day(self, day: str, timezone: str = "UTC") -> list[Event]:
        start, end = _local_day_bounds(day, timezone)

        cursor = await self._db.execute(
            """
            SELECT id, timestamp, source, event_type, data, metadata
            FROM events
            WHERE unixepoch(timestamp) >= unixepoch(?)
              AND unixepoch(timestamp) < unixepoch(?)
            ORDER BY unixepoch(timestamp) ASC, id ASC
            """,
            (start, end),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        return [
            Event(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                source=row[2],
                event_type=row[3],
                data=json.loads(row[4]),
                metadata=json.loads(row[5]),
            )
            for row in rows
        ]

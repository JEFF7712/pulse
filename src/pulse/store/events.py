import json
from datetime import date
from datetime import datetime

import aiosqlite

from pulse.domain.events import Event


class EventRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert_events(self, events: list[Event]) -> None:
        if not events:
            return

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
                    event.timestamp.isoformat(),
                    event.source,
                    event.event_type,
                    json.dumps(event.data),
                    json.dumps(event.metadata),
                )
                for event in events
            ],
        )
        await self._db.commit()

    async def list_events_for_day(self, day: str) -> list[Event]:
        start = date.fromisoformat(day).isoformat()
        end = date.fromordinal(date.fromisoformat(day).toordinal() + 1).isoformat()

        cursor = await self._db.execute(
            """
            SELECT id, timestamp, source, event_type, data, metadata
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC, id ASC
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

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import aiosqlite


def _local_day_bounds(day: str, timezone: str) -> tuple[str, str]:
    day_date = date.fromisoformat(day)
    tz = ZoneInfo(timezone)
    start = datetime.combine(day_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(
        day_date + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(UTC)
    return start.isoformat(), end.isoformat()


def _local_window_bounds(start_day: str, days: int, timezone: str) -> tuple[str, str]:
    day_date = date.fromisoformat(start_day)
    tz = ZoneInfo(timezone)
    start = datetime.combine(day_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(
        day_date + timedelta(days=days), time.min, tzinfo=tz
    ).astimezone(UTC)
    return start.isoformat(), end.isoformat()


class AnalyticsRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Daily source stats
    # ------------------------------------------------------------------

    async def aggregate_daily_stats(self, day: str, timezone: str = "UTC") -> None:
        start, end = _local_day_bounds(day, timezone)

        await self._db.execute(
            "DELETE FROM daily_source_stats WHERE date = ?",
            (day,),
        )
        await self._db.execute(
            """
            WITH filtered_events AS (
                SELECT source, event_type, timestamp
                FROM events
                WHERE unixepoch(timestamp) >= unixepoch(?)
                  AND unixepoch(timestamp) < unixepoch(?)
            ),
            aggregated AS (
                SELECT source, event_type, COUNT(*) AS count
                FROM filtered_events
                GROUP BY source, event_type
            )
            INSERT INTO daily_source_stats (date, source, event_type, count, first_at, last_at)
            SELECT
                ? AS date,
                a.source,
                a.event_type,
                a.count,
                (
                    SELECT f.timestamp
                    FROM filtered_events f
                    WHERE f.source = a.source AND f.event_type = a.event_type
                    ORDER BY unixepoch(f.timestamp) ASC, f.timestamp ASC
                    LIMIT 1
                ) AS first_at,
                (
                    SELECT f.timestamp
                    FROM filtered_events f
                    WHERE f.source = a.source AND f.event_type = a.event_type
                    ORDER BY unixepoch(f.timestamp) DESC, f.timestamp DESC
                    LIMIT 1
                ) AS last_at
            FROM aggregated a
            """,
            (start, end, day),
        )
        await self._db.commit()

    async def get_daily_stats(self, day: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT date, source, event_type, count, first_at, last_at
            FROM daily_source_stats
            WHERE date = ?
            ORDER BY source, event_type
            """,
            (day,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "date": row[0],
                "source": row[1],
                "event_type": row[2],
                "count": row[3],
                "first_at": row[4],
                "last_at": row[5],
            }
            for row in rows
        ]

    async def get_daily_stats_range(self, start: str, end: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT date, source, event_type, count, first_at, last_at
            FROM daily_source_stats
            WHERE date >= ? AND date < ?
            ORDER BY date, source, event_type
            """,
            (start, end),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "date": row[0],
                "source": row[1],
                "event_type": row[2],
                "count": row[3],
                "first_at": row[4],
                "last_at": row[5],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Time blocks
    # ------------------------------------------------------------------

    async def aggregate_time_blocks(self, day: str, timezone: str = "UTC") -> None:
        start, end = _local_day_bounds(day, timezone)
        tz = ZoneInfo(timezone)

        await self._db.execute(
            "DELETE FROM time_blocks WHERE date = ?",
            (day,),
        )
        cursor = await self._db.execute(
            """
            SELECT source, timestamp
            FROM events
            WHERE unixepoch(timestamp) >= unixepoch(?)
              AND unixepoch(timestamp) < unixepoch(?)
            """,
            (start, end),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        counts: dict[tuple[int, str], int] = {}
        for source, timestamp in rows:
            local_hour = datetime.fromisoformat(timestamp).astimezone(tz).hour
            key = (local_hour // 2, source)
            counts[key] = counts.get(key, 0) + 1

        await self._db.executemany(
            """
            INSERT INTO time_blocks (date, block, source, count)
            VALUES (?, ?, ?, ?)
            """,
            [
                (day, block, source, count)
                for (block, source), count in sorted(counts.items())
            ],
        )
        await self._db.commit()

    async def get_time_blocks(self, day: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT date, block, source, count
            FROM time_blocks
            WHERE date = ?
            ORDER BY block, source
            """,
            (day,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "date": row[0],
                "block": row[1],
                "source": row[2],
                "count": row[3],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Weekly baselines
    # ------------------------------------------------------------------

    async def aggregate_weekly_baselines(
        self, week_start: str, timezone: str = "UTC"
    ) -> None:
        start, end = _local_window_bounds(week_start, 7, timezone)

        await self._db.execute(
            "DELETE FROM weekly_baselines WHERE week_start = ?",
            (week_start,),
        )
        await self._db.execute(
            """
            INSERT INTO weekly_baselines (week_start, source, event_type, avg_daily, total)
            SELECT
                ? AS week_start,
                source,
                event_type,
                COUNT(*) / 7.0 AS avg_daily,
                COUNT(*) AS total
            FROM events
            WHERE unixepoch(timestamp) >= unixepoch(?)
              AND unixepoch(timestamp) < unixepoch(?)
            GROUP BY source, event_type
            """,
            (week_start, start, end),
        )
        await self._db.commit()

    async def get_weekly_baselines(self, week_start: str) -> list[dict]:
        cursor = await self._db.execute(
            """
            SELECT week_start, source, event_type, avg_daily, total
            FROM weekly_baselines
            WHERE week_start = ?
            ORDER BY source, event_type
            """,
            (week_start,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "week_start": row[0],
                "source": row[1],
                "event_type": row[2],
                "avg_daily": row[3],
                "total": row[4],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def aggregate_day(self, day: str, timezone: str = "UTC") -> None:
        await self.aggregate_daily_stats(day, timezone=timezone)
        await self.aggregate_time_blocks(day, timezone=timezone)

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    async def upsert_insight(
        self,
        id: str,
        title: str,
        status: str,
        confidence: str,
        first_seen: str,
        last_seen: str,
        vault_path: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO insights (id, title, status, confidence, first_seen, last_seen, vault_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                status = excluded.status,
                confidence = excluded.confidence,
                first_seen = excluded.first_seen,
                last_seen = excluded.last_seen,
                vault_path = excluded.vault_path
            """,
            (id, title, status, confidence, first_seen, last_seen, vault_path),
        )
        await self._db.commit()

    async def get_insight(self, id: str) -> dict | None:
        cursor = await self._db.execute(
            """
            SELECT id, title, status, confidence, first_seen, last_seen, vault_path
            FROM insights
            WHERE id = ?
            """,
            (id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None

        return {
            "id": row[0],
            "title": row[1],
            "status": row[2],
            "confidence": row[3],
            "first_seen": row[4],
            "last_seen": row[5],
            "vault_path": row[6],
        }

    async def delete_insights(self, ids: list[str]) -> None:
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        await self._db.execute(
            f"DELETE FROM insights WHERE id IN ({placeholders})",
            tuple(ids),
        )
        await self._db.commit()

    async def list_insights(self, status: str | None = None) -> list[dict]:
        if status is not None:
            cursor = await self._db.execute(
                """
                SELECT id, title, status, confidence, first_seen, last_seen, vault_path
                FROM insights
                WHERE status = ?
                ORDER BY last_seen DESC
                """,
                (status,),
            )
        else:
            cursor = await self._db.execute(
                """
                SELECT id, title, status, confidence, first_seen, last_seen, vault_path
                FROM insights
                ORDER BY last_seen DESC
                """
            )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "id": row[0],
                "title": row[1],
                "status": row[2],
                "confidence": row[3],
                "first_seen": row[4],
                "last_seen": row[5],
                "vault_path": row[6],
            }
            for row in rows
        ]

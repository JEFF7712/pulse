from datetime import date, timedelta

import aiosqlite


class AnalyticsRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Daily source stats
    # ------------------------------------------------------------------

    async def aggregate_daily_stats(self, day: str) -> None:
        start = date.fromisoformat(day).isoformat()
        end = date.fromordinal(date.fromisoformat(day).toordinal() + 1).isoformat()

        await self._db.execute(
            "DELETE FROM daily_source_stats WHERE date = ?",
            (day,),
        )
        await self._db.execute(
            """
            INSERT INTO daily_source_stats (date, source, event_type, count, first_at, last_at)
            SELECT
                ? AS date,
                source,
                event_type,
                COUNT(*) AS count,
                MIN(timestamp) AS first_at,
                MAX(timestamp) AS last_at
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY source, event_type
            """,
            (day, start, end),
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

    async def aggregate_time_blocks(self, day: str) -> None:
        start = date.fromisoformat(day).isoformat()
        end = date.fromordinal(date.fromisoformat(day).toordinal() + 1).isoformat()

        await self._db.execute(
            "DELETE FROM time_blocks WHERE date = ?",
            (day,),
        )
        await self._db.execute(
            """
            INSERT INTO time_blocks (date, block, source, count)
            SELECT
                ? AS date,
                CAST(strftime('%H', timestamp) AS INTEGER) / 2 AS block,
                source,
                COUNT(*) AS count
            FROM events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY block, source
            """,
            (day, start, end),
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

    async def aggregate_weekly_baselines(self, week_start: str) -> None:
        start = date.fromisoformat(week_start).isoformat()
        end = (date.fromisoformat(week_start) + timedelta(days=7)).isoformat()

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
            WHERE timestamp >= ? AND timestamp < ?
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

    async def aggregate_day(self, day: str) -> None:
        await self.aggregate_daily_stats(day)
        await self.aggregate_time_blocks(day)

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

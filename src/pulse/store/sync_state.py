import aiosqlite


class SyncStateRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(self, source: str, cursor: str) -> None:
        await self._db.execute(
            """
            INSERT INTO connector_sync_state (source, cursor)
            VALUES (?, ?)
            ON CONFLICT(source) DO UPDATE SET
                cursor = excluded.cursor,
                updated_at = CURRENT_TIMESTAMP
            """,
            (source, cursor),
        )
        await self._db.commit()

    async def load(self, source: str) -> str | None:
        db_cursor = await self._db.execute(
            "SELECT cursor FROM connector_sync_state WHERE source = ?",
            (source,),
        )
        row = await db_cursor.fetchone()
        await db_cursor.close()
        if row is None:
            return None
        return str(row[0])

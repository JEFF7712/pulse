"""Repository for FCM device token storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import aiosqlite


class DeviceTokenRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, token: str, platform: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO device_tokens (token, platform, registered_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET updated_at = ?
            """,
            (token, platform, now, now, now),
        )
        await self._db.commit()

    async def list_active(self) -> list[dict[str, Any]]:
        cursor = await self._db.execute(
            "SELECT token, platform, registered_at, updated_at FROM device_tokens ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "token": row[0],
                "platform": row[1],
                "registered_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

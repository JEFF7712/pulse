from datetime import datetime

import aiosqlite


class OAuthTokenRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def save(
        self,
        provider: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        scopes: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at, scopes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                scopes = excluded.scopes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (provider, access_token, refresh_token, expires_at.isoformat(), scopes),
        )
        await self._db.commit()

    async def load(self, provider: str) -> dict[str, str] | None:
        cursor = await self._db.execute(
            "SELECT access_token, refresh_token, expires_at, scopes FROM oauth_tokens WHERE provider = ?",
            (provider,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return {
            "access_token": row[0],
            "refresh_token": row[1],
            "expires_at": row[2],
            "scopes": row[3],
        }

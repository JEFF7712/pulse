import aiosqlite

from pulse.domain.corrections import Correction


class CorrectionRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def add(self, correction: Correction) -> None:
        await self._db.execute(
            """
            INSERT INTO corrections (id, context_id, message_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                correction.id,
                correction.context_id,
                correction.message_text,
                correction.created_at.isoformat(),
            ),
        )
        await self._db.commit()

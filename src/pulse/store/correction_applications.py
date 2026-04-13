from datetime import UTC, datetime

import aiosqlite

from pulse.domain.correction_applications import CorrectionApplication


class CorrectionApplicationRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def add(self, application: CorrectionApplication) -> None:
        await self._db.execute(
            """
            INSERT INTO correction_applications (
                id,
                correction_id,
                status,
                target_type,
                target_ref,
                operation,
                summary,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application.id,
                application.correction_id,
                application.status,
                application.target_type,
                application.target_ref,
                application.operation,
                application.summary,
                application.error_message,
                _serialize_timestamp(application.created_at),
                _serialize_timestamp(application.updated_at),
            ),
        )
        await self._db.commit()

    async def count_with_status_in(self, statuses: tuple[str, ...]) -> int:
        if not statuses:
            return 0
        placeholders = ",".join("?" * len(statuses))
        cursor = await self._db.execute(
            f"""
            SELECT COUNT(*) FROM correction_applications
            WHERE status IN ({placeholders})
            """,
            tuple(statuses),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0]) if row and row[0] is not None else 0

    async def list_for_correction(
        self, correction_id: str
    ) -> list[CorrectionApplication]:
        cursor = await self._db.execute(
            """
            SELECT
                id,
                correction_id,
                status,
                target_type,
                target_ref,
                operation,
                summary,
                error_message,
                created_at,
                updated_at
            FROM correction_applications
            WHERE correction_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (correction_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        return [
            CorrectionApplication(
                id=row[0],
                correction_id=row[1],
                status=row[2],
                target_type=row[3],
                target_ref=row[4],
                operation=row[5],
                summary=row[6],
                error_message=row[7],
                created_at=_parse_timestamp(row[8]),
                updated_at=_parse_timestamp(row[9]),
            )
            for row in rows
        ]


def _serialize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

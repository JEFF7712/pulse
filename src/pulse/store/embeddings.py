from array import array

import aiosqlite


def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


class EmbeddingRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert_embeddings(self, items: list[tuple[str, list[float]]]) -> None:
        if not items:
            return
        await self._db.executemany(
            "INSERT INTO event_embeddings (event_id, dim, vector) VALUES (?, ?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET dim=excluded.dim, vector=excluded.vector",
            [(eid, len(vec), _pack(vec)) for eid, vec in items],
        )
        await self._db.commit()

    async def load_all(self) -> list[tuple[str, list[float]]]:
        cur = await self._db.execute("SELECT event_id, vector FROM event_embeddings")
        rows = await cur.fetchall()
        await cur.close()
        return [(r[0], _unpack(r[1])) for r in rows]

    async def missing_ids(self, candidate_ids: list[str]) -> list[str]:
        if not candidate_ids:
            return []
        placeholders = ",".join("?" for _ in candidate_ids)
        cur = await self._db.execute(
            f"SELECT event_id FROM event_embeddings WHERE event_id IN ({placeholders})",
            candidate_ids,
        )
        have = {r[0] for r in await cur.fetchall()}
        await cur.close()
        return [cid for cid in candidate_ids if cid not in have]

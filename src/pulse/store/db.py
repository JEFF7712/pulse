from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


@asynccontextmanager
async def connect_db(path: str | Path) -> AsyncIterator[aiosqlite.Connection]:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(path)
    try:
        yield db
    finally:
        await db.close()

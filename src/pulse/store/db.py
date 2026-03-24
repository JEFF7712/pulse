from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


@asynccontextmanager
async def connect_db(path: str | Path) -> AsyncIterator[aiosqlite.Connection]:
    db = await aiosqlite.connect(path)
    try:
        yield db
    finally:
        await db.close()

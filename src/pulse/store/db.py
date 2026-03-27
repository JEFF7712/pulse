from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


@asynccontextmanager
async def connect_db(path: str | Path) -> AsyncIterator[aiosqlite.Connection]:
    db = await aiosqlite.connect(path)
    await enable_foreign_keys(db)
    try:
        yield db
    finally:
        await db.close()


async def enable_foreign_keys(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA foreign_keys = ON")

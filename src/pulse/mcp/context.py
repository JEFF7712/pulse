from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiosqlite

from pulse.app.config import PulseConfig
from pulse.store.db import enable_foreign_keys
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository
from pulse.vault.onboarding import ensure_vault_onboarding


@dataclass
class PulseContext:
    events: EventRepository
    sync_state: SyncStateRepository
    vault_path: str
    database_path: str
    _db: aiosqlite.Connection
    config: PulseConfig | None = None

    async def close(self) -> None:
        await self._db.close()


@asynccontextmanager
async def open_pulse_context(
    *, db_path: str, vault_path: str, config: PulseConfig | None = None
) -> AsyncIterator[PulseContext]:
    db = await aiosqlite.connect(db_path)
    await enable_foreign_keys(db)
    await bootstrap_schema(db)
    ensure_vault_onboarding(vault_path)
    try:
        yield PulseContext(
            events=EventRepository(db),
            sync_state=SyncStateRepository(db),
            vault_path=vault_path,
            database_path=db_path,
            _db=db,
            config=config,
        )
    finally:
        await db.close()

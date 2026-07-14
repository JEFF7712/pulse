import asyncio
from pathlib import Path

from pulse.mcp.context import PulseContext, open_pulse_context


def test_pulse_context_direct_construction_remains_compatible() -> None:
    ctx = PulseContext(
        events=object(),
        sync_state=object(),
        vault_path="vault",
        database_path="data/pulse.db",
        _db=object(),
    )

    assert ctx.events is not None
    assert ctx.sync_state is not None
    assert ctx.vault_path == "vault"


def test_context_provides_repos(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(db_path), vault_path=str(tmp_path / "vault")
        ) as ctx:
            assert ctx.events is not None
            assert ctx.sync_state is not None
            assert ctx.vault_path == str(tmp_path / "vault")
            assert ctx.database_path == str(db_path)

    asyncio.run(_run())


def test_open_pulse_context_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(db_path), vault_path=str(tmp_path / "vault")
        ) as ctx:
            cursor = await ctx._db.execute("PRAGMA foreign_keys")
            row = await cursor.fetchone()
            await cursor.close()

            assert row == (1,)

    asyncio.run(_run())

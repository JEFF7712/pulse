import asyncio
from pathlib import Path

from pulse.mcp.context import open_pulse_context


def test_context_provides_repos(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(db_path), vault_path=str(tmp_path / "vault")
        ) as ctx:
            assert ctx.events is not None
            assert ctx.corrections is not None
            assert ctx.sync_state is not None
            assert ctx.vault_path == str(tmp_path / "vault")

    asyncio.run(_run())

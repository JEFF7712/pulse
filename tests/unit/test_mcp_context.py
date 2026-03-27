import asyncio
from pathlib import Path

import aiosqlite

from pulse.mcp.context import PulseContext, open_pulse_context


def test_pulse_context_direct_construction_remains_compatible() -> None:
    ctx = PulseContext(
        events=object(),
        corrections=object(),
        sync_state=object(),
        vault_path="vault",
        _db=object(),
    )

    assert ctx.events is not None
    assert ctx.corrections is not None
    assert ctx.correction_applications is None
    assert ctx.sync_state is not None
    assert ctx.vault_path == "vault"


def test_context_provides_repos(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(db_path), vault_path=str(tmp_path / "vault")
        ) as ctx:
            assert ctx.events is not None
            assert ctx.corrections is not None
            assert ctx.correction_applications is not None
            assert ctx.sync_state is not None
            assert ctx.vault_path == str(tmp_path / "vault")

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

            with pytest.raises(aiosqlite.IntegrityError):
                await ctx._db.execute(
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
                        "app-missing-parent",
                        "missing-correction",
                        "failed",
                        "file",
                        "src/pulse/app.py",
                        "replace",
                        "Should fail",
                        "missing parent",
                        "2026-03-27T12:00:00+00:00",
                        "2026-03-27T12:05:00+00:00",
                    ),
                )

    import pytest

    asyncio.run(_run())

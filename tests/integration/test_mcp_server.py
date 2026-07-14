import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from pulse.domain.events import Event
from pulse.mcp.context import open_pulse_context


def _make_events() -> list[Event]:
    return [
        Event(
            id="cal:int1",
            timestamp=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Team sync"},
            metadata={},
        ),
        Event(
            id="gmail:int1",
            timestamp=datetime(2026, 3, 23, 11, 0, tzinfo=UTC),
            source="gmail",
            event_type="email.received",
            data={"subject": "Q1 Report", "sender": "cfo@company.com"},
            metadata={},
        ),
    ]


def test_events_query_returns_json(tmp_path: Path) -> None:
    """Seed events, query via repository, verify JSON serialization format."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")
            assert len(events) == 2

            serialized = json.dumps(
                [
                    {
                        "id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "source": e.source,
                        "event_type": e.event_type,
                        "data": e.data,
                    }
                    for e in events
                ],
                indent=2,
            )
            parsed = json.loads(serialized)
            assert len(parsed) == 2
            assert parsed[0]["source"] == "calendar"
            assert parsed[1]["data"]["subject"] == "Q1 Report"

    asyncio.run(_run())


def test_events_filter_by_source(tmp_path: Path) -> None:
    """Verify source filtering works correctly."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")
            filtered = [e for e in events if e.source == "gmail"]
            assert len(filtered) == 1
            assert filtered[0].id == "gmail:int1"

    asyncio.run(_run())


def test_pulse_events_for_day_defaults_to_configured_local_day(
    tmp_path: Path, monkeypatch
) -> None:
    from pulse.app.config import PulseConfig
    from pulse.mcp import server as server_module

    class FakeDatetime:
        @staticmethod
        def now(tz):
            assert str(tz) == "America/Los_Angeles"
            return datetime(2026, 1, 15, 23, 30, tzinfo=tz)

    monkeypatch.setattr(server_module, "datetime", FakeDatetime)

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
            timezone="America/Los_Angeles",
        )
        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            await pulse_ctx.events.upsert_events(
                [
                    Event(
                        id="local-day",
                        timestamp=datetime(2026, 1, 15, 20, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="calendar.event",
                        data={"title": "Local day event"},
                        metadata={},
                    )
                ]
            )
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_events_for_day(ctx=ctx)

            parsed = json.loads(result)
            assert [item["id"] for item in parsed] == ["local-day"]

    asyncio.run(_run())


def test_connector_status_fresh_db(tmp_path: Path) -> None:
    """Connector status returns None for a fresh database."""

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            cursor = await ctx.sync_state.load("gmail")
            assert cursor is None

    asyncio.run(_run())


def test_pulse_query_events_trims_by_default_and_supports_full(tmp_path: Path) -> None:
    """pulse_query_events returns trimmed data by default; full=True keeps raw."""
    from pulse.mcp import server as server_module

    long_body = "x" * 300

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as pulse_ctx:
            await pulse_ctx.events.upsert_events(
                [
                    Event(
                        id="gmail:q1",
                        timestamp=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "invoice", "body": long_body},
                        metadata={},
                    ),
                    Event(
                        id="github:q1",
                        timestamp=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                        source="github",
                        event_type="commit",
                        data={"message": "fix bug"},
                        metadata={},
                    ),
                    Event(
                        id="calendar:q1",
                        timestamp=datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
                        source="calendar",
                        event_type="calendar.event",
                        data={"title": "standup"},
                        metadata={},
                    ),
                ]
            )
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_query_events(ctx=ctx)
            parsed = json.loads(result)
            assert set(parsed.keys()) >= {"count", "returned", "events"}
            assert parsed["count"] == 3
            assert parsed["returned"] == 3
            assert len(parsed["events"]) == 3

            gmail = next(e for e in parsed["events"] if e["id"] == "gmail:q1")
            assert "… (+" in gmail["data"]["body"]
            assert len(gmail["data"]["body"]) < len(long_body)

            full = json.loads(
                await server_module.pulse_query_events(full=True, ctx=ctx)
            )
            gmail_full = next(e for e in full["events"] if e["id"] == "gmail:q1")
            assert gmail_full["data"]["body"] == long_body

            filtered = json.loads(
                await server_module.pulse_query_events(sources="gmail,github", ctx=ctx)
            )
            assert filtered["count"] == 2
            assert {e["source"] for e in filtered["events"]} == {"gmail", "github"}

    asyncio.run(_run())


def test_pulse_vault_tools_round_trip_list_append_and_reject_unsafe(
    tmp_path: Path,
) -> None:
    """Vault tools write/read round-trip, list, append section, and reject unsafe paths."""
    from pulse.mcp import server as server_module

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as pulse_ctx:
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            wrote = await server_module.pulse_vault_write(
                path="notes/today.md",
                content="# Today\n\nIntro.\n",
                ctx=ctx,
            )
            assert "Wrote" in wrote

            content = await server_module.pulse_vault_read(
                path="notes/today.md", ctx=ctx
            )
            assert content == "# Today\n\nIntro.\n"

            listed = json.loads(await server_module.pulse_vault_list(ctx=ctx))
            assert "notes/today.md" in listed

            updated = await server_module.pulse_vault_append_section(
                path="notes/today.md",
                heading="## Log",
                body="- did a thing",
                ctx=ctx,
            )
            assert "Updated section" in updated
            after = await server_module.pulse_vault_read(path="notes/today.md", ctx=ctx)
            assert "## Log" in after
            assert "- did a thing" in after

            unsafe = await server_module.pulse_vault_read(path="../escape.md", ctx=ctx)
            assert unsafe.startswith("Error:")
            assert "Unsafe vault path" in unsafe

    asyncio.run(_run())

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


def test_pulse_coverage_returns_per_source_counts_and_freshness(
    tmp_path: Path,
) -> None:
    """pulse_coverage returns JSON keyed by source with event_count and last_event."""
    from pulse.mcp import server as server_module

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as pulse_ctx:
            await pulse_ctx.events.upsert_events(
                [
                    Event(
                        id="gmail:c1",
                        timestamp=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "hi"},
                        metadata={},
                    ),
                    Event(
                        id="gmail:c2",
                        timestamp=datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "later"},
                        metadata={},
                    ),
                ]
            )
            await pulse_ctx.sync_state.save("github", "cursor-abc")

            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_coverage(ctx=ctx)
            parsed = json.loads(result)

            assert "gmail" in parsed
            assert parsed["gmail"]["event_count"] == 2
            assert parsed["gmail"]["last_event"] == "2026-07-01T11:00:00+00:00"

            assert "github" in parsed
            assert parsed["github"]["last_sync"] == "cursor-abc"
            assert parsed["github"]["event_count"] == 0
            assert parsed["github"]["last_event"] is None

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


def test_pulse_digest_returns_source_counts_and_clusters(tmp_path: Path) -> None:
    """pulse_digest returns per-source counts and preprocessor clusters for a day."""
    from pulse.mcp import server as server_module

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as pulse_ctx:
            await pulse_ctx.events.upsert_events(
                [
                    Event(
                        id="browser:d1",
                        timestamp=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                        source="browser",
                        event_type="browsing.visit",
                        data={
                            "url": "https://docs.rs/tokio",
                            "title": "tokio - Rust",
                        },
                        metadata={},
                    ),
                    Event(
                        id="browser:d2",
                        timestamp=datetime(2026, 7, 1, 10, 10, tzinfo=UTC),
                        source="browser",
                        event_type="browsing.visit",
                        data={
                            "url": "https://docs.rs/async-std",
                            "title": "async-std - Rust",
                        },
                        metadata={},
                    ),
                    Event(
                        id="gmail:d1",
                        timestamp=datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "invoice", "sender": "billing@co.com"},
                        metadata={},
                    ),
                    Event(
                        id="calendar:d1",
                        timestamp=datetime(2026, 7, 1, 14, 0, tzinfo=UTC),
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

            result = await server_module.pulse_digest(day="2026-07-01", ctx=ctx)
            parsed = json.loads(result)

            assert parsed["day"] == "2026-07-01"
            assert parsed["total_events"] == 4
            assert parsed["by_source"] == {
                "browser": 2,
                "gmail": 1,
                "calendar": 1,
            }
            clusters = parsed["clusters"]
            assert "browsing_clusters" in clusters
            assert "calendar_blocks" in clusters
            assert len(clusters["browsing_clusters"]) >= 1
            assert clusters["browsing_clusters"][0]["domain"] == "docs.rs"
            assert len(clusters["calendar_blocks"]) >= 1
            assert clusters["calendar_blocks"][0]["title"] == "standup"

    asyncio.run(_run())


def test_mcp_resources_digest_coverage_and_vault_index(
    tmp_path: Path, monkeypatch
) -> None:
    """Resources expose today's digest, coverage, and vault note index."""
    from pulse.app.config import PulseConfig
    from pulse.mcp import server as server_module

    class FakeDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 7, 1, 15, 0, tzinfo=tz)

    monkeypatch.setattr(server_module, "datetime", FakeDatetime)

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
            timezone="UTC",
        )
        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            await pulse_ctx.events.upsert_events(
                [
                    Event(
                        id="gmail:r1",
                        timestamp=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "hello"},
                        metadata={},
                    ),
                    Event(
                        id="github:r1",
                        timestamp=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                        source="github",
                        event_type="commit",
                        data={"message": "ship it"},
                        metadata={},
                    ),
                ]
            )
            await pulse_ctx.sync_state.save("github", "cursor-xyz")

            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )
            monkeypatch.setattr(server_module.mcp, "get_context", lambda: ctx)

            await server_module.pulse_vault_write(
                path="notes/today.md",
                content="# Today\n",
                ctx=ctx,
            )

            digest = json.loads(await server_module.digest_today_resource())
            assert digest["day"] == "2026-07-01"
            assert digest["total_events"] == 2
            assert digest["by_source"] == {"gmail": 1, "github": 1}
            tool_digest = json.loads(
                await server_module.pulse_digest(day="2026-07-01", ctx=ctx)
            )
            assert digest == tool_digest

            coverage = json.loads(await server_module.coverage_resource())
            tool_coverage = json.loads(await server_module.pulse_coverage(ctx=ctx))
            assert coverage == tool_coverage
            assert coverage["gmail"]["event_count"] == 1
            assert coverage["github"]["last_sync"] == "cursor-xyz"

            index = json.loads(await server_module.vault_index_resource())
            tool_list = json.loads(await server_module.pulse_vault_list(ctx=ctx))
            assert index == tool_list
            assert "notes/today.md" in index

    asyncio.run(_run())

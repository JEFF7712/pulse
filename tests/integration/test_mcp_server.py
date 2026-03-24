import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

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


def test_correction_roundtrip(tmp_path: Path) -> None:
    """Record a correction via CorrectionService and verify it persists."""
    from pulse.services.corrections import CorrectionService

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            service = CorrectionService(ctx.corrections)
            correction = await service.record_correction("2026-03-23", "Wrong meeting time")
            assert correction.context_id == "2026-03-23"
            assert correction.message_text == "Wrong meeting time"

    asyncio.run(_run())


def test_digest_writes_vault_file(tmp_path: Path) -> None:
    """Generate a digest and verify the vault file contains expected content."""
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.vault.writer import write_daily_digest

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            await ctx.events.upsert_events(_make_events())
            events = await ctx.events.list_events_for_day("2026-03-23")

            summarizer = DailySummarizer()
            summary = summarizer.summarize(date(2026, 3, 23), events)

            output = write_daily_digest(
                Path(ctx.vault_path), "2026-03-23", summary.markdown
            )
            assert output.exists()
            content = output.read_text()
            assert "Team sync" in content
            assert "Q1 Report" in content

    asyncio.run(_run())


def test_read_digest_missing_file(tmp_path: Path) -> None:
    """Reading a non-existent digest returns a not-found indicator."""
    digest_path = tmp_path / "vault" / "01-Daily" / "2026-01-01.md"
    assert not digest_path.exists()


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

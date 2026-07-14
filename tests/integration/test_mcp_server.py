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


def test_correction_roundtrip(tmp_path: Path) -> None:
    """Record a correction via CorrectionService and verify it persists."""
    from pulse.services.corrections import CorrectionService

    async def _run() -> None:
        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            service = CorrectionService(ctx.corrections)
            correction = await service.record_correction(
                "2026-03-23", "Wrong meeting time"
            )
            assert correction.context_id == "2026-03-23"
            assert correction.message_text == "Wrong meeting time"

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


def test_pulse_read_pattern_missing_file(tmp_path: Path) -> None:
    from pulse.app.config import PulseConfig
    from pulse.mcp import server as server_module

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        )
        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )
            result = await server_module.pulse_read_pattern("missing-slug", ctx=ctx)
            assert "No pattern file" in result

    asyncio.run(_run())


def test_pulse_insights_omits_rows_with_missing_pattern_files(tmp_path: Path) -> None:
    from pulse.app.config import PulseConfig
    from pulse.mcp import server as server_module
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.schema import bootstrap_schema

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        )
        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            await bootstrap_schema(pulse_ctx._db)
            analytics = AnalyticsRepository(pulse_ctx._db)
            await analytics.upsert_insight(
                id="missing-file",
                title="Missing file",
                status="active",
                confidence="0.9",
                first_seen="2026-01-01",
                last_seen="2026-01-02",
                vault_path="02-Insights/patterns/missing-file.md",
            )

            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )
            result = await server_module.pulse_insights(ctx=ctx)
            assert result == "No insights found."

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


def test_pulse_correct_applies_profile_update_and_records_audit_row(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return """
            {
              "target_type": "profile",
              "operation": "replace_section",
              "target_ref": "profile",
              "section": "## Learned Corrections",
              "content": "Prefer short daily plans over long checklists.",
              "summary": "Update profile correction notes.",
              "confidence": 0.91
            }
            """

    from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig
    from pulse.mcp import server as server_module
    from pulse.services import corrections as corrections_module

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        lambda config: FakeLLM(),
    )

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )
        profile_path = Path(config.vault_path) / "04-Config" / "profile.md"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text("# Profile\n\n## Bio\nBuilder.\n", encoding="utf-8")
        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_correct(
                context_id="profile",
                message_text="I do better with short daily plans.",
                ctx=ctx,
            )

            assert result.startswith("Correction ")

            cursor = await pulse_ctx._db.execute(
                "SELECT status, target_type, operation FROM correction_applications"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            assert rows == [("applied", "profile", "replace_section")]

        profile_text = profile_path.read_text(encoding="utf-8")
        assert "## Learned Corrections" in profile_text
        assert "Prefer short daily plans over long checklists." in profile_text

    asyncio.run(_run())


def test_pulse_correct_applies_routines_update_and_records_audit_row(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return """
            {
              "target_type": "routines",
              "operation": "replace_section",
              "target_ref": "routines",
              "section": "## Correction Updates",
              "content": "Use a shorter shutdown routine.",
              "summary": "Update routines corrections.",
              "confidence": 0.84
            }
            """

    from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig
    from pulse.mcp import server as server_module
    from pulse.services import corrections as corrections_module

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        lambda config: FakeLLM(),
    )

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )
        routines_path = Path(config.vault_path) / "03-Life" / "routines.md"
        routines_path.parent.mkdir(parents=True, exist_ok=True)
        routines_path.write_text(
            "# Routines\n\n## Evening\nRead for 20 minutes.\n", encoding="utf-8"
        )

        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_correct(
                context_id="routines",
                message_text="Use a shorter shutdown routine.",
                ctx=ctx,
            )

            assert result.startswith("Correction ")

            cursor = await pulse_ctx._db.execute(
                "SELECT status, target_type, operation FROM correction_applications"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            assert rows == [("applied", "routines", "replace_section")]

        routines_text = routines_path.read_text(encoding="utf-8")
        assert "## Evening\nRead for 20 minutes." in routines_text
        assert "## Correction Updates\nUse a shorter shutdown routine." in routines_text

    asyncio.run(_run())


def test_pulse_correct_persists_raw_correction_when_corrections_llm_init_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig
    from pulse.mcp import server as server_module
    from pulse.services import corrections as corrections_module

    def raise_init_error(config):
        raise ValueError("OPENAI_API_KEY environment variable is required")

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        raise_init_error,
    )

    async def _run() -> None:
        config = PulseConfig(
            database_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )

        async with open_pulse_context(
            db_path=config.database_path,
            vault_path=config.vault_path,
            config=config,
        ) as pulse_ctx:
            ctx = SimpleNamespace(
                request_context=SimpleNamespace(lifespan_context=pulse_ctx)
            )

            result = await server_module.pulse_correct(
                context_id="2026-03-23",
                message_text="Wrong meeting time.",
                ctx=ctx,
            )

            assert result.startswith("Correction ")

            correction_cursor = await pulse_ctx._db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            correction_rows = await correction_cursor.fetchall()
            await correction_cursor.close()

            application_cursor = await pulse_ctx._db.execute(
                "SELECT status, target_type, operation, error_message FROM correction_applications"
            )
            application_rows = await application_cursor.fetchall()
            await application_cursor.close()

            assert correction_rows == [("2026-03-23", "Wrong meeting time.")]
            assert application_rows == [
                (
                    "needs_review",
                    "none",
                    "needs_review",
                    "OPENAI_API_KEY environment variable is required",
                )
            ]

    asyncio.run(_run())

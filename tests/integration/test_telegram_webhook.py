import asyncio

from fastapi.testclient import TestClient

from pulse.app.config import LLMConfig, LLMRoleConfig, Settings
from pulse.app.dependencies import get_settings
from pulse.app.main import create_app


def test_telegram_webhook_records_reply_correction(tmp_path) -> None:
    db_path = tmp_path / "telegram-webhook.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_path=str(db_path)
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "Please use the updated project name.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Morning briefing for 2026-03-22\n\nContext: ctx-123",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_rows() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch_rows()) == [
        ("ctx-123", "Please use the updated project name."),
    ]


def test_telegram_webhook_applies_digest_correction_and_records_audit_row(
    tmp_path, monkeypatch
) -> None:
    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return """
            {
              "target_type": "digest",
              "operation": "append_note",
              "target_ref": "2026-03-22",
              "section": "Corrections",
              "content": "The walk happened after lunch.",
              "summary": "Append a correction to the daily digest.",
              "confidence": 0.96
            }
            """

    from pulse.services import corrections as corrections_module

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        lambda config: FakeLLM(),
    )

    db_path = tmp_path / "telegram-webhook.db"
    vault_path = tmp_path / "vault"
    digest_path = vault_path / "01-Daily" / "2026-03-22.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        "# Daily Digest\n\n## Summary\nMorning walk.\n", encoding="utf-8"
    )

    app = create_app(
        settings=Settings(
            database_path=str(db_path),
            vault_path=str(vault_path),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "The walk happened after lunch, not in the morning.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Morning briefing for 2026-03-22\n\nContext: 2026-03-22",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_rows() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)

            correction_cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            correction_rows = await correction_cursor.fetchall()
            await correction_cursor.close()

            application_cursor = await db.execute(
                "SELECT status, target_type, operation FROM correction_applications"
            )
            application_rows = await application_cursor.fetchall()
            await application_cursor.close()

        return (
            [(row[0], row[1]) for row in correction_rows],
            [(row[0], row[1], row[2]) for row in application_rows],
        )

    corrections, applications = asyncio.run(fetch_rows())
    assert corrections == [
        ("2026-03-22", "The walk happened after lunch, not in the morning."),
    ]
    assert applications == [("applied", "digest", "append_note")]
    assert "## Corrections" in digest_path.read_text(encoding="utf-8")
    assert "- The walk happened after lunch." in digest_path.read_text(encoding="utf-8")


def test_telegram_webhook_applies_pattern_correction_and_records_audit_row(
    tmp_path, monkeypatch
) -> None:
    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return """
            {
              "target_type": "pattern",
              "operation": "update_pattern_notes",
              "target_ref": "focus-sessions",
              "section": "User Notes",
              "content": "This pattern usually appears after back-to-back meetings.",
              "summary": "Update pattern notes with the correction.",
              "confidence": 0.92
            }
            """

    from pulse.services import corrections as corrections_module

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        lambda config: FakeLLM(),
    )

    db_path = tmp_path / "telegram-webhook.db"
    vault_path = tmp_path / "vault"
    pattern_path = vault_path / "02-Insights" / "patterns" / "focus-sessions.md"
    pattern_path.parent.mkdir(parents=True, exist_ok=True)
    pattern_path.write_text(
        "# Pattern: Focus sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nDeep work improves in quiet mornings.\n\n## Evidence Log\n- 2026-03-20: 2 h focus block\n\n## Trend\nStable.\n\n## User Notes\nKeep this note.\n",
        encoding="utf-8",
    )

    app = create_app(
        settings=Settings(
            database_path=str(db_path),
            vault_path=str(vault_path),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "This pattern usually appears after back-to-back meetings.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Discovery note\n\nContext: pattern:focus-sessions",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_rows() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)

            correction_cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            correction_rows = await correction_cursor.fetchall()
            await correction_cursor.close()

            application_cursor = await db.execute(
                "SELECT status, target_type, operation FROM correction_applications"
            )
            application_rows = await application_cursor.fetchall()
            await application_cursor.close()

        return (
            [(row[0], row[1]) for row in correction_rows],
            [(row[0], row[1], row[2]) for row in application_rows],
        )

    corrections, applications = asyncio.run(fetch_rows())
    assert corrections == [
        (
            "pattern:focus-sessions",
            "This pattern usually appears after back-to-back meetings.",
        ),
    ]
    assert applications == [("applied", "pattern", "update_pattern_notes")]
    pattern_text = pattern_path.read_text(encoding="utf-8")
    assert (
        "## User Notes\nThis pattern usually appears after back-to-back meetings."
        in pattern_text
    )
    assert "## Observation\nDeep work improves in quiet mornings." in pattern_text


def test_telegram_webhook_persists_raw_correction_when_corrections_llm_init_fails(
    tmp_path, monkeypatch
) -> None:
    from pulse.services import corrections as corrections_module

    def raise_init_error(config):
        raise ValueError("OPENAI_API_KEY environment variable is required")

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        raise_init_error,
    )

    db_path = tmp_path / "telegram-webhook.db"
    vault_path = tmp_path / "vault"

    app = create_app(
        settings=Settings(
            database_path=str(db_path),
            vault_path=str(vault_path),
            llm=LLMConfig(
                corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini")
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "The walk happened after lunch, not in the morning.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Morning briefing for 2026-03-22\n\nContext: 2026-03-22",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_rows() -> tuple[
        list[tuple[str, str]], list[tuple[str, str, str, str | None]]
    ]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)

            correction_cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections"
            )
            correction_rows = await correction_cursor.fetchall()
            await correction_cursor.close()

            application_cursor = await db.execute(
                "SELECT status, target_type, operation, error_message FROM correction_applications"
            )
            application_rows = await application_cursor.fetchall()
            await application_cursor.close()

        return (
            [(row[0], row[1]) for row in correction_rows],
            [(row[0], row[1], row[2], row[3]) for row in application_rows],
        )

    corrections, applications = asyncio.run(fetch_rows())
    assert corrections == [
        ("2026-03-22", "The walk happened after lunch, not in the morning."),
    ]
    assert applications == [
        (
            "needs_review",
            "none",
            "needs_review",
            "OPENAI_API_KEY environment variable is required",
        )
    ]

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from pulse.app.config import LLMConfig, LLMRoleConfig, Settings
from pulse.app.main import create_app


def test_backend_first_vertical_slice_records_pattern_correction_reply(tmp_path, monkeypatch) -> None:
    class FakeLLM:
        async def complete(self, prompt, *, system_prompt=None, model=None):
            return """
            {
              "target_type": "pattern",
              "operation": "update_pattern_notes",
              "target_ref": "e2e-slice",
              "section": "User Notes",
              "content": "Prefer roadmap wording in summaries.",
              "summary": "Align notes with user preference.",
              "confidence": 0.9
            }
            """

    from pulse.services import corrections as corrections_module

    monkeypatch.setattr(
        corrections_module,
        "create_corrections_provider_from_config",
        lambda config: FakeLLM(),
    )

    db_path = tmp_path / "pulse.db"
    vault_path = tmp_path / "vault"
    pattern_path = (
        Path(vault_path) / "02-Insights" / "patterns" / "e2e-slice.md"
    )
    pattern_path.parent.mkdir(parents=True, exist_ok=True)
    pattern_path.write_text(
        "# Pattern: E2E slice\n\n**Status:** active\n**Confidence:** 0.5\n"
        "**First seen:** 2026-03-22\n**Last updated:** 2026-03-22\n\n"
        "## Observation\nEmail tone matters.\n\n## Evidence Log\n\n## Trend\n\n"
        "## User Notes\n_Notes._\n",
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
                "text": "The email should mention the roadmap, not the project update.",
                "reply_to_message": {
                    "message_id": 100,
                    "text": "Pulse insight\n\nContext: pattern:e2e-slice",
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async def fetch_corrections() -> list[tuple[str, str]]:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            cursor = await db.execute(
                "SELECT context_id, message_text FROM corrections ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [(row[0], row[1]) for row in rows]

    assert asyncio.run(fetch_corrections()) == [
        (
            "pattern:e2e-slice",
            "The email should mention the roadmap, not the project update.",
        )
    ]
    text = pattern_path.read_text(encoding="utf-8")
    assert "Prefer roadmap wording in summaries." in text

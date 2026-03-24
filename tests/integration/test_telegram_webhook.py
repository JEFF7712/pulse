import asyncio

from fastapi.testclient import TestClient

from pulse.app.config import Settings
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

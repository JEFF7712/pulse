from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.app.main import create_app


def test_telegram_webhook_accepts_plain_message(tmp_path) -> None:
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
                "text": "Hello Pulse",
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_telegram_webhook_rejects_missing_message() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={"update_id": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing message payload."


def test_telegram_webhook_rejects_blank_text() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {"message_id": 200, "text": "   "},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Missing message text."

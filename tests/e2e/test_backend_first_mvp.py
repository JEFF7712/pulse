from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.main import create_app


def test_backend_first_vertical_slice_accepts_telegram_message(tmp_path) -> None:
    db_path = tmp_path / "pulse.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    app = create_app(
        settings=Settings(
            database_path=str(db_path),
            vault_path=str(vault_path),
        )
    )
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    response = client.post(
        "/webhooks/telegram",
        json={
            "update_id": 1,
            "message": {
                "message_id": 200,
                "text": "Hello from the backend-first slice.",
            },
        },
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

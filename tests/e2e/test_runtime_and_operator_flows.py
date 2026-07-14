from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.main import create_app


def test_runtime_routes_are_available_with_temp_settings(tmp_path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                database_path=str(tmp_path / "pulse.db"),
                vault_path=str(tmp_path / "vault"),
                timezone="UTC",
            )
        )
    )

    health_response = client.get("/health")
    home_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert home_response.status_code == 200
    assert "text/html" in home_response.headers["content-type"]
    assert "Pulse" in home_response.text

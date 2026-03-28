import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulse.app.config import ConnectorConfig, PulseConfig


def _build_test_app(tmp_path: Path, companion_token: str = "test-token") -> FastAPI:
    from pulse.app.api import build_api_router
    from pulse.app.auth import build_require_companion_token

    settings = PulseConfig(
        database_path=str(tmp_path / "test.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token=companion_token,
    )

    app = FastAPI()
    auth_dep = build_require_companion_token(lambda: settings)
    router = build_api_router(lambda: settings, auth_dep)
    app.include_router(router)
    return app


def test_get_digest_returns_markdown(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-27.md").write_text(
        "# Daily Digest\n\n- Met with Sam.", encoding="utf-8"
    )

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert "Met with Sam" in response.json()["markdown"]


def test_get_digest_returns_404_for_missing_date(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 404


def test_get_latest_digest_returns_most_recent(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-26.md").write_text("# March 26", encoding="utf-8")
    (vault / "2026-03-27.md").write_text("# March 27", encoding="utf-8")

    response = client.get(
        "/api/digests/latest",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert "March 27" in response.json()["markdown"]


def test_post_correction_records_and_returns_id(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/corrections",
        headers={"X-Pulse-Token": "test-token"},
        json={
            "context_id": "2026-03-27",
            "message_text": "The deadline is Friday.",
        },
    )
    assert response.status_code == 202
    assert "correction_id" in response.json()


def test_post_device_token_stores_token(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/device-token",
        headers={"X-Pulse-Token": "test-token"},
        json={"token": "fcm-device-abc", "platform": "ios"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "registered"

    async def check_db():
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "test.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)
            tokens = await repo.list_active()
            return tokens

    tokens = asyncio.run(check_db())
    assert len(tokens) == 1
    assert tokens[0]["token"] == "fcm-device-abc"


def test_api_rejects_unauthenticated_request(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get("/api/digests/2026-03-27")
    assert response.status_code == 401


def test_companion_webhook_and_api_wired_in_full_app(tmp_path):
    from pulse.app.config import PulseConfig, ConnectorConfig
    from pulse.app.main import create_app
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry

    settings = PulseConfig(
        database_path=str(tmp_path / "full.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token="integration-token",
        connectors={"companion": ConnectorConfig(enabled=True)},
    )

    registry = ConnectorRegistry()
    register_all(registry, settings)

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    # Companion webhook should be wired
    response = client.post(
        "/webhooks/companion",
        json={
            "events": [
                {
                    "type": "location.enter",
                    "timestamp": "2026-03-27T09:00:00Z",
                    "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["events_received"] == 1

    # API digest route should be wired
    vault = tmp_path / "vault" / "01-Daily"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "2026-03-27.md").write_text("# Test Digest", encoding="utf-8")

    response = client.get(
        "/api/digests/2026-03-27",
        headers={"X-Pulse-Token": "integration-token"},
    )
    assert response.status_code == 200

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


def test_get_insights_empty_list(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(
        "/api/insights",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_insight_returns_markdown(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    vault = tmp_path / "vault"
    patterns = vault / "02-Insights" / "patterns"
    patterns.mkdir(parents=True)
    (patterns / "alpha.md").write_text("# Alpha\n\nBody.\n", encoding="utf-8")

    async def seed():
        async with connect_db(tmp_path / "test.db") as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            await analytics.upsert_insight(
                id="alpha",
                title="Alpha pattern",
                status="active",
                confidence=0.9,
                first_seen="2026-01-01",
                last_seen="2026-01-02",
                vault_path="02-Insights/patterns/alpha.md",
            )

    asyncio.run(seed())

    app = _build_test_app(tmp_path)
    client = TestClient(app)

    lst = client.get("/api/insights", headers={"X-Pulse-Token": "test-token"})
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) == 1
    assert rows[0]["id"] == "alpha"

    one = client.get(
        "/api/insights/alpha",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert one.status_code == 200
    data = one.json()
    assert data["id"] == "alpha"
    assert data["title"] == "Alpha pattern"
    assert "# Alpha" in data["markdown"]


def test_get_insight_unknown_returns_404(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)
    response = client.get(
        "/api/insights/missing",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 404


def test_get_insights_omits_rows_with_missing_pattern_files(tmp_path):
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    async def seed():
        async with connect_db(tmp_path / "test.db") as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            await analytics.upsert_insight(
                id="missing-file",
                title="Missing file",
                status="active",
                confidence=0.9,
                first_seen="2026-01-01",
                last_seen="2026-01-02",
                vault_path="02-Insights/patterns/missing-file.md",
            )

    asyncio.run(seed())

    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(
        "/api/insights",
        headers={"X-Pulse-Token": "test-token"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_post_correction_records_and_returns_id(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/corrections",
        headers={"X-Pulse-Token": "test-token"},
        json={
            "context_id": "pattern:test-slug",
            "message_text": "The deadline is Friday.",
        },
    )
    assert response.status_code == 202
    assert "correction_id" in response.json()


def test_post_correction_accepts_message_alias(tmp_path):
    app = _build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/corrections",
        headers={"X-Pulse-Token": "test-token"},
        json={
            "context_id": "pattern:test-slug",
            "message": "The deadline is Friday.",
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

    response = client.post(
        "/api/corrections",
        json={"context_id": "profile", "message_text": "x"},
    )
    assert response.status_code == 401


def test_mounted_api_accepts_bearer_token_with_settings_override(tmp_path):
    from pulse.app.api import build_api_router
    from pulse.app.auth import build_require_companion_token
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    base_settings = PulseConfig(
        database_path=str(tmp_path / "base.db"),
        vault_path=str(tmp_path / "base-vault"),
        companion_token="base-token",
    )
    override_settings = PulseConfig(
        database_path=str(tmp_path / "override.db"),
        vault_path=str(tmp_path / "override-vault"),
        companion_token="override-token",
    )

    def get_test_settings() -> PulseConfig:
        return base_settings

    async def seed() -> None:
        async with connect_db(base_settings.database_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            await analytics.upsert_insight(
                id="base-only",
                title="Base insight",
                status="active",
                confidence=0.7,
                first_seen="2026-01-01",
                last_seen="2026-01-02",
                vault_path="02-Insights/patterns/base-only.md",
            )

    asyncio.run(seed())

    app = FastAPI()
    auth_dep = build_require_companion_token(get_test_settings)
    app.include_router(build_api_router(get_test_settings, auth_dep))
    app.dependency_overrides[get_test_settings] = lambda: override_settings

    client = TestClient(app)
    response = client.get(
        "/api/insights",
        headers={"Authorization": "Bearer override-token"},
    )

    assert response.status_code == 200
    assert response.json() == []


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
    asyncio.run(registry.build_active_connectors(settings))

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    # Companion webhook should be wired
    response = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
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

    # Insights API should be wired
    response = client.get(
        "/api/insights",
        headers={"X-Pulse-Token": "integration-token"},
    )
    assert response.status_code == 200
    assert response.json() == []

    # Corrections API should be wired
    response = client.post(
        "/api/corrections",
        headers={"X-Pulse-Token": "integration-token"},
        json={
            "context_id": "profile",
            "message_text": "Test correction",
        },
    )
    assert response.status_code == 202


def test_companion_webhook_requires_token_in_full_app(tmp_path):
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
    asyncio.run(registry.build_active_connectors(settings))

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    response = client.post(
        "/webhooks/companion",
        json={"events": []},
    )

    assert response.status_code == 401


def test_companion_webhook_accepts_bearer_token_in_full_app(tmp_path):
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
    asyncio.run(registry.build_active_connectors(settings))

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    response = client.post(
        "/webhooks/companion",
        headers={"Authorization": "Bearer integration-token"},
        json={"events": []},
    )

    assert response.status_code == 200
    assert response.json()["events_received"] == 0


def test_companion_webhook_not_mounted_when_connector_disabled(tmp_path):
    from pulse.app.main import create_app
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry

    settings = PulseConfig(
        database_path=str(tmp_path / "full.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token="integration-token",
        connectors={"companion": ConnectorConfig(enabled=False)},
    )

    registry = ConnectorRegistry()
    register_all(registry, settings)
    asyncio.run(registry.build_active_connectors(settings))

    app = create_app(settings=settings, registry=registry)
    client = TestClient(app)

    response = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
        json={"events": []},
    )

    assert response.status_code == 404


def test_companion_webhook_is_mounted_before_building_active_connectors(tmp_path):
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

    unauthenticated = client.post("/webhooks/companion", json={"events": []})
    authenticated = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
        json={"events": []},
    )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["events_received"] == 0


def test_companion_webhook_returns_400_for_naive_timestamp(tmp_path):
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

    response = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
        json={
            "events": [
                {
                    "type": "location.enter",
                    "timestamp": "2026-03-27T09:00:00",
                    "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                }
            ]
        },
    )

    assert response.status_code == 400
    assert "timezone-aware" in response.json()["detail"]


def test_companion_webhook_respects_dependency_overrides_when_app_built_without_settings(
    tmp_path,
):
    from pulse.app.config import PulseConfig, ConnectorConfig
    from pulse.app.dependencies import get_settings
    from pulse.app.main import create_app
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    register_all(registry, PulseConfig())

    app = create_app(registry=registry)
    client = TestClient(app)

    app.dependency_overrides[get_settings] = lambda: PulseConfig(
        database_path=str(tmp_path / "enabled.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token="integration-token",
        connectors={"companion": ConnectorConfig(enabled=True)},
    )

    unauthenticated = client.post("/webhooks/companion", json={"events": []})
    authenticated = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
        json={"events": []},
    )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200

    app.dependency_overrides[get_settings] = lambda: PulseConfig(
        database_path=str(tmp_path / "disabled.db"),
        vault_path=str(tmp_path / "vault"),
        companion_token="integration-token",
        connectors={"companion": ConnectorConfig(enabled=False)},
    )

    disabled = client.post(
        "/webhooks/companion",
        headers={"X-Pulse-Token": "integration-token"},
        json={"events": []},
    )

    assert disabled.status_code == 404

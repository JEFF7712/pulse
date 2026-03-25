import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import PushConnector
from pulse.domain.events import Event


class FakePushConnector(PushConnector):
    def get_source_name(self):
        return "test_push"

    def get_webhook_path(self):
        return "/webhooks/test_push"

    async def handle_webhook(self, payload):
        return [
            Event(
                id=f"test_push:{payload['id']}",
                timestamp=datetime.now(UTC),
                source="test_push",
                event_type="test.event",
                data=payload,
            )
        ]


def test_push_connector_webhook_receives_and_stores_events(tmp_path):
    from pulse.app.main import create_app

    config = PulseConfig(
        database_path=str(tmp_path / "test.db"),
        connectors={"test_push": ConnectorConfig(enabled=True)},
    )

    registry = ConnectorRegistry()
    registry.register_push("test_push", lambda: FakePushConnector())
    asyncio.run(registry.build_active_connectors(config))

    app = create_app(settings=config, registry=registry)
    client = TestClient(app)

    response = client.post("/webhooks/test_push", json={"id": "evt-1", "data": "hello"})
    assert response.status_code == 200
    assert response.json()["events_received"] == 1

import asyncio

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector, PushConnector


class ValidConnector(Connector):
    async def pull(self, since=None):
        return []

    def get_source_name(self):
        return "valid"


class InvalidConnector(Connector):
    async def pull(self, since=None):
        return []

    def get_source_name(self):
        return "invalid"

    async def validate_config(self):
        return False


class ValidPush(PushConnector):
    def get_source_name(self):
        return "valid_push"

    def get_webhook_path(self):
        return "/webhooks/valid"

    async def handle_webhook(self, payload):
        return []


def test_registry_starts_with_mix_of_valid_invalid_and_disabled():
    async def exercise():
        registry = ConnectorRegistry()
        registry.register_pull("valid", lambda: ValidConnector())
        registry.register_pull("invalid", lambda: InvalidConnector())
        registry.register_push("valid_push", lambda: ValidPush())

        config = PulseConfig(
            connectors={
                "valid": ConnectorConfig(enabled=True),
                "invalid": ConnectorConfig(enabled=True),
                "valid_push": ConnectorConfig(enabled=True),
                "disabled": ConnectorConfig(enabled=False),
            }
        )

        await registry.build_active_connectors(config)

        assert len(registry.get_pull_connectors()) == 1
        assert registry.get_pull_connectors()[0][0].get_source_name() == "valid"
        assert len(registry.get_push_connectors()) == 1

    asyncio.run(exercise())

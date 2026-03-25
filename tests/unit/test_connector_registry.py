import asyncio
from datetime import timedelta
from collections.abc import Callable

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.domain.connectors import Connector, PushConnector
from pulse.domain.events import Event


class FakePullConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake_pull"
    def get_default_interval(self):
        return timedelta(minutes=5)

class FakeInvalidConnector(Connector):
    async def pull(self, since=None):
        return []
    def get_source_name(self):
        return "fake_invalid"
    async def validate_config(self):
        return False

class FakePushConnector(PushConnector):
    def get_source_name(self):
        return "fake_push"
    def get_webhook_path(self):
        return "/webhooks/fake"
    async def handle_webhook(self, payload):
        return []


def test_registry_registers_and_builds_pull_connectors():
    from pulse.connectors.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    registry.register_pull("fake_pull", lambda: FakePullConnector())
    config = PulseConfig(connectors={
        "fake_pull": ConnectorConfig(enabled=True, poll_interval="5m"),
    })
    asyncio.run(registry.build_active_connectors(config))
    pull = registry.get_pull_connectors()
    assert len(pull) == 1
    connector, cc = pull[0]
    assert connector.get_source_name() == "fake_pull"
    assert cc.poll_interval == "5m"


def test_registry_skips_disabled_connectors():
    from pulse.connectors.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    registry.register_pull("fake_pull", lambda: FakePullConnector())
    config = PulseConfig(connectors={
        "fake_pull": ConnectorConfig(enabled=False),
    })
    asyncio.run(registry.build_active_connectors(config))
    assert registry.get_pull_connectors() == []


def test_registry_skips_connectors_that_fail_validation():
    from pulse.connectors.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    registry.register_pull("fake_invalid", lambda: FakeInvalidConnector())
    config = PulseConfig(connectors={
        "fake_invalid": ConnectorConfig(enabled=True),
    })
    asyncio.run(registry.build_active_connectors(config))
    assert registry.get_pull_connectors() == []


def test_registry_registers_push_connectors():
    from pulse.connectors.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    registry.register_push("fake_push", lambda: FakePushConnector())
    config = PulseConfig(connectors={
        "fake_push": ConnectorConfig(enabled=True),
    })
    asyncio.run(registry.build_active_connectors(config))
    push = registry.get_push_connectors()
    assert len(push) == 1
    connector, cc = push[0]
    assert connector.get_source_name() == "fake_push"
    assert connector.get_webhook_path() == "/webhooks/fake"


def test_registry_ignores_config_entries_without_registered_class():
    from pulse.connectors.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    config = PulseConfig(connectors={
        "nonexistent": ConnectorConfig(enabled=True),
    })
    asyncio.run(registry.build_active_connectors(config))
    assert registry.get_pull_connectors() == []
    assert registry.get_push_connectors() == []

from datetime import timedelta


def test_connector_provides_default_interval():
    import asyncio
    from pulse.domain.connectors import Connector
    from pulse.domain.events import Event
    from datetime import datetime

    class StubConnector(Connector):
        async def pull(self, since=None):
            return []
        def get_source_name(self):
            return "stub"

    c = StubConnector()
    assert c.get_default_interval() == timedelta(minutes=15)


def test_connector_validate_config_returns_true_by_default():
    import asyncio
    from pulse.domain.connectors import Connector

    class StubConnector(Connector):
        async def pull(self, since=None):
            return []
        def get_source_name(self):
            return "stub"

    c = StubConnector()
    assert asyncio.run(c.validate_config()) is True


def test_push_connector_requires_source_name_webhook_path_and_handle():
    import asyncio
    from pulse.domain.connectors import PushConnector

    class StubPush(PushConnector):
        def get_source_name(self):
            return "webhook_test"
        def get_webhook_path(self):
            return "/webhooks/test"
        async def handle_webhook(self, payload):
            return []

    p = StubPush()
    assert p.get_source_name() == "webhook_test"
    assert p.get_webhook_path() == "/webhooks/test"
    assert asyncio.run(p.handle_webhook({})) == []
    assert asyncio.run(p.validate_config()) is True

from datetime import UTC, datetime


def test_event_captures_required_fields_and_defaults_metadata():
    from pulse.domain.events import Event

    timestamp = datetime(2026, 3, 22, 12, 0, tzinfo=UTC)
    payload = {"message": "hello"}

    event = Event(
        id="evt-1",
        timestamp=timestamp,
        source="telegram",
        event_type="message.created",
        data=payload,
    )

    assert event.id == "evt-1"
    assert event.timestamp is timestamp
    assert event.source == "telegram"
    assert event.event_type == "message.created"
    assert event.data is payload
    assert event.metadata == {}


def test_connector_defines_pull_and_source_name_contract():
    from pulse.domain.connectors import Connector
    from pulse.domain.events import Event

    timestamp = datetime(2026, 3, 22, 12, 0, tzinfo=UTC)

    class FakeConnector(Connector):
        async def pull(self, since: datetime | None = None) -> list[Event]:
            return [
                Event(
                    id="evt-2",
                    timestamp=timestamp,
                    source="fake",
                    event_type="sync.completed",
                    data={"since": since},
                )
            ]

        def get_source_name(self) -> str:
            return "fake"

    connector = FakeConnector()
    events = __import__("asyncio").run(connector.pull(timestamp))

    assert connector.get_source_name() == "fake"
    assert len(events) == 1
    assert events[0].source == "fake"
    assert events[0].data == {"since": timestamp}

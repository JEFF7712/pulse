from datetime import UTC, datetime


def test_gmail_connector_normalizes_messages():
    from pulse.connectors.gmail import GmailConnector

    class FakeGmailClient:
        async def list_messages(self, since=None):
            assert since == datetime(2026, 3, 20, 0, 0, tzinfo=UTC)
            return [
                {
                    "id": "msg-123",
                    "internalDate": "1761042600000",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Welcome"},
                            {"name": "From", "value": "sender@example.com"},
                        ]
                    },
                },
                {
                    "id": "msg-456",
                    "internalDate": "1761046200000",
                    "payload": {"headers": []},
                },
            ]

    connector = GmailConnector(client=FakeGmailClient())

    events = __import__("asyncio").run(
        connector.pull(datetime(2026, 3, 20, 0, 0, tzinfo=UTC))
    )

    assert [event.id for event in events] == ["gmail:msg-123", "gmail:msg-456"]
    assert [event.source for event in events] == ["gmail", "gmail"]
    assert [event.event_type for event in events] == [
        "email.received",
        "email.received",
    ]
    assert [event.timestamp for event in events] == [
        datetime(2025, 10, 21, 10, 30, tzinfo=UTC),
        datetime(2025, 10, 21, 11, 30, tzinfo=UTC),
    ]
    assert [event.data for event in events] == [
        {"subject": "Welcome", "sender": "sender@example.com"},
        {"subject": "", "sender": ""},
    ]

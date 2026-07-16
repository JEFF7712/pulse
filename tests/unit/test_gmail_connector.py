from datetime import UTC, datetime


def _make_fake_service(messages):
    """Mimics: service.users().messages().list().execute() / .get().execute()"""

    class FakeGetRequest:
        def __init__(self, msg):
            self._msg = msg

        def execute(self):
            return self._msg

    class FakeListRequest:
        def __init__(self, stubs):
            self._stubs = stubs

        def execute(self):
            return {"messages": self._stubs}

    class FakeMessages:
        def list(self, **kwargs):
            return FakeListRequest([{"id": m["id"]} for m in messages])

        def get(self, userId, id, **kwargs):
            for m in messages:
                if m["id"] == id:
                    return FakeGetRequest(m)
            raise KeyError(id)

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    return FakeService()


def test_gmail_connector_normalizes_messages():
    from pulse.connectors.gmail import GmailConnector

    raw_messages = [
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

    connector = GmailConnector(client=_make_fake_service(raw_messages))

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
        {"subject": "Welcome", "sender": "sender@example.com", "category": "primary"},
        {"subject": "", "sender": "", "category": "primary"},
    ]


def test_gmail_connector_captures_category_from_labels():
    from pulse.connectors.gmail import GmailConnector

    raw = [
        {
            "id": "promo",
            "internalDate": "1761042600000",
            "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"],
            "payload": {"headers": [{"name": "From", "value": "sale@shop.com"}]},
        },
        {
            "id": "personal",
            "internalDate": "1761046200000",
            "labelIds": ["INBOX", "CATEGORY_PERSONAL"],
            "payload": {"headers": [{"name": "From", "value": "friend@x.com"}]},
        },
    ]
    connector = GmailConnector(client=_make_fake_service(raw))
    events = __import__("asyncio").run(connector.pull(None))
    cats = {e.id: e.data["category"] for e in events}
    assert cats == {"gmail:promo": "promotions", "gmail:personal": "primary"}

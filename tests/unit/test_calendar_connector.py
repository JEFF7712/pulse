from datetime import UTC, datetime


def test_google_calendar_connector_normalizes_events():
    from pulse.connectors.calendar import GoogleCalendarConnector

    class FakeCalendarClient:
        async def list_events(self, since=None):
            assert since == datetime(2026, 3, 20, 0, 0, tzinfo=UTC)
            return [
                {
                    "id": "abc123",
                    "summary": "Team sync",
                    "start": {"dateTime": "2026-03-21T09:30:00+00:00"},
                },
                {
                    "id": "def456",
                    "start": {"dateTime": "2026-03-21T11:00:00+00:00"},
                },
            ]

    connector = GoogleCalendarConnector(
        client=FakeCalendarClient(),
    )

    events = __import__("asyncio").run(
        connector.pull(datetime(2026, 3, 20, 0, 0, tzinfo=UTC))
    )

    assert [event.id for event in events] == [
        "calendar:abc123",
        "calendar:def456",
    ]
    assert [event.source for event in events] == ["calendar", "calendar"]
    assert [event.event_type for event in events] == [
        "calendar.event",
        "calendar.event",
    ]
    assert [event.timestamp for event in events] == [
        datetime(2026, 3, 21, 9, 30, tzinfo=UTC),
        datetime(2026, 3, 21, 11, 0, tzinfo=UTC),
    ]
    assert [event.data["title"] for event in events] == ["Team sync", "Untitled event"]


def test_google_calendar_connector_supports_all_day_events():
    from pulse.connectors.calendar import GoogleCalendarConnector

    class FakeCalendarClient:
        async def list_events(self, since=None):
            assert since is None
            return [
                {
                    "id": "day-1",
                    "summary": "Offsite",
                    "start": {"date": "2026-03-22"},
                }
            ]

    connector = GoogleCalendarConnector(client=FakeCalendarClient())

    events = __import__("asyncio").run(connector.pull())

    assert len(events) == 1
    assert events[0].id == "calendar:day-1"
    assert events[0].timestamp == datetime(2026, 3, 22, 0, 0, tzinfo=UTC)
    assert events[0].data["title"] == "Offsite"


def test_google_auth_placeholder_raises_not_implemented_error():
    from pulse.connectors.google_auth import build_google_credentials

    try:
        build_google_credentials()
    except NotImplementedError as exc:
        assert str(exc) == "Google auth is not implemented yet."
    else:
        raise AssertionError("Expected NotImplementedError")

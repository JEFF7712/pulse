from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError


def _make_fake_service(items):
    """Mimics: service.events().list(...).execute()"""
    class FakeListRequest:
        def execute(self):
            return {"items": items}

    class FakeEvents:
        def list(self, **kwargs):
            self.last_kwargs = kwargs
            return FakeListRequest()

    class FakeService:
        def __init__(self):
            self._events = FakeEvents()

        def events(self):
            return self._events

    return FakeService()


def test_google_calendar_connector_normalizes_events():
    from pulse.connectors.calendar import GoogleCalendarConnector

    items = [
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

    connector = GoogleCalendarConnector(client=_make_fake_service(items))

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

    items = [
        {
            "id": "day-1",
            "summary": "Offsite",
            "start": {"date": "2026-03-22"},
        }
    ]

    connector = GoogleCalendarConnector(client=_make_fake_service(items))

    events = __import__("asyncio").run(connector.pull())

    assert len(events) == 1
    assert events[0].id == "calendar:day-1"
    assert events[0].timestamp == datetime(2026, 3, 22, 0, 0, tzinfo=UTC)
    assert events[0].data["title"] == "Offsite"


def test_google_calendar_uses_updated_min_not_time_min():
    """Verify that pull uses updatedMin (not timeMin) to avoid cursor drift from future events."""
    from pulse.connectors.calendar import GoogleCalendarConnector

    items = [
        {
            "id": "future-1",
            "summary": "Recurring 2055",
            "start": {"dateTime": "2055-11-10T00:00:00+00:00"},
        },
    ]

    service = _make_fake_service(items)
    connector = GoogleCalendarConnector(client=service)

    since = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    events = __import__("asyncio").run(connector.pull(since=since))

    # Should use updatedMin, not timeMin
    kwargs = service._events.last_kwargs
    assert "updatedMin" in kwargs
    assert "timeMin" not in kwargs
    assert kwargs["orderBy"] == "updated"


def test_get_sync_timestamp_returns_pull_time_not_event_time():
    """The sync cursor should be the pull timestamp, not max event timestamp."""
    from pulse.connectors.calendar import GoogleCalendarConnector

    items = [
        {
            "id": "future-2",
            "summary": "Far future event",
            "start": {"dateTime": "2055-11-10T00:00:00+00:00"},
        },
    ]

    connector = GoogleCalendarConnector(client=_make_fake_service(items))

    before = datetime.now(UTC)
    __import__("asyncio").run(connector.pull())
    after = datetime.now(UTC)

    sync_ts = connector.get_sync_timestamp()
    # Sync timestamp should be around "now", not 2055
    assert before <= sync_ts <= after


def test_google_calendar_resync_when_updated_min_too_long_ago():
    """410 updatedMinTooLongAgo triggers a bounded timeMin list (no updatedMin)."""
    from pulse.connectors.calendar import GoogleCalendarConnector

    resp = Mock()
    resp.status = 410
    stale_err = HttpError(
        resp,
        b'{"error":{"errors":[{"reason":"updatedMinTooLongAgo","message":"too far"}]}}',
    )

    resync_items = [
        {
            "id": "resync-1",
            "summary": "Recovered",
            "start": {"dateTime": "2026-03-01T10:00:00+00:00"},
        },
    ]

    class FakeListRequest:
        def __init__(self, fn):
            self._fn = fn

        def execute(self):
            return self._fn()

    class FakeEvents:
        def __init__(self, parent):
            self.parent = parent

        def list(self, **kwargs):
            self.parent.kwargs_history.append(kwargs)
            n = len(self.parent.kwargs_history)
            if n == 1:

                def _raise():
                    raise stale_err

                return FakeListRequest(_raise)

            def _ok():
                return {"items": resync_items, "nextPageToken": None}

            return FakeListRequest(_ok)

    class FakeService:
        def __init__(self):
            self.kwargs_history: list = []
            self._events = FakeEvents(self)

        def events(self):
            return self._events

    service = FakeService()
    connector = GoogleCalendarConnector(client=service)
    since = datetime(2025, 1, 1, tzinfo=UTC)
    events = __import__("asyncio").run(connector.pull(since=since))

    assert len(events) == 1
    assert events[0].id == "calendar:resync-1"
    assert len(service.kwargs_history) == 2
    assert "updatedMin" in service.kwargs_history[0]
    assert service.kwargs_history[1].get("timeMin")
    assert service.kwargs_history[1]["orderBy"] == "startTime"
    assert "updatedMin" not in service.kwargs_history[1]


def test_google_calendar_non_410_http_error_propagates():
    from pulse.connectors.calendar import GoogleCalendarConnector

    resp = Mock()
    resp.status = 403
    forbidden = HttpError(resp, b'{"error":{"errors":[{"reason":"forbidden"}]}}')

    class FakeListRequest:
        def execute(self):
            raise forbidden

    class FakeEvents:
        def list(self, **kwargs):
            return FakeListRequest()

    class FakeService:
        def events(self):
            return FakeEvents()

    connector = GoogleCalendarConnector(client=FakeService())
    with pytest.raises(HttpError):
        __import__("asyncio").run(
            connector.pull(since=datetime(2026, 3, 1, tzinfo=UTC))
        )

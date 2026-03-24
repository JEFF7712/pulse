from datetime import datetime, UTC
from unittest.mock import AsyncMock

import pytest

from pulse.connectors.calendar import GoogleCalendarClient


@pytest.mark.asyncio
async def test_calendar_client_lists_events():
    mock_http = AsyncMock()
    mock_http.get.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "items": [
                {
                    "id": "evt-1",
                    "summary": "Standup",
                    "start": {"dateTime": "2026-03-22T09:00:00Z"},
                }
            ],
        },
        raise_for_status=lambda: None,
    )

    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = "access-tok"

    client = GoogleCalendarClient(oauth=mock_oauth, http_client=mock_http)
    events = await client.list_events(since=datetime(2026, 3, 22, tzinfo=UTC))

    assert len(events) == 1
    assert events[0]["id"] == "evt-1"
    mock_http.get.assert_called_once()


@pytest.mark.asyncio
async def test_calendar_client_returns_empty_when_no_token():
    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = None

    client = GoogleCalendarClient(oauth=mock_oauth, http_client=AsyncMock())
    events = await client.list_events()
    assert events == []

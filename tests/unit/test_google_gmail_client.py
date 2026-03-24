from unittest.mock import AsyncMock

import pytest

from pulse.connectors.gmail import GoogleGmailClient


@pytest.mark.asyncio
async def test_gmail_client_lists_messages():
    mock_list_resp = AsyncMock(
        status_code=200,
        json=lambda: {"messages": [{"id": "msg-1"}]},
        raise_for_status=lambda: None,
    )
    mock_detail_resp = AsyncMock(
        status_code=200,
        json=lambda: {
            "id": "msg-1",
            "internalDate": "1774173600000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Hello"},
                    {"name": "From", "value": "test@example.com"},
                ]
            },
        },
        raise_for_status=lambda: None,
    )

    mock_http = AsyncMock()
    mock_http.get.side_effect = [mock_list_resp, mock_detail_resp]

    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = "access-tok"

    client = GoogleGmailClient(oauth=mock_oauth, http_client=mock_http)
    messages = await client.list_messages()

    assert len(messages) == 1
    assert messages[0]["id"] == "msg-1"


@pytest.mark.asyncio
async def test_gmail_client_returns_empty_when_no_token():
    mock_oauth = AsyncMock()
    mock_oauth.get_access_token.return_value = None

    client = GoogleGmailClient(oauth=mock_oauth, http_client=AsyncMock())
    messages = await client.list_messages()
    assert messages == []

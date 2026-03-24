from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock

import pytest

from pulse.connectors.google_auth import GoogleOAuth, build_authorization_url


def test_build_authorization_url_includes_state_and_scopes():
    url, state = build_authorization_url(
        client_id="test-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )
    assert "test-client-id" in url
    assert "calendar.readonly" in url
    assert "gmail.readonly" in url
    assert state  # non-empty random string
    assert f"state={state}" in url


@pytest.mark.asyncio
async def test_exchange_code_stores_tokens():
    mock_http = AsyncMock()
    mock_http.post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly",
        },
        raise_for_status=lambda: None,
    )

    mock_repo = AsyncMock()

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=mock_http,
    )

    await oauth.exchange_code("auth-code-123")

    mock_http.post.assert_called_once()
    mock_repo.save.assert_called_once()
    call_kwargs = mock_repo.save.call_args
    assert call_kwargs.kwargs["access_token"] == "access-new"
    assert call_kwargs.kwargs["refresh_token"] == "refresh-new"


@pytest.mark.asyncio
async def test_get_access_token_refreshes_when_expired():
    expired = datetime.now(UTC) - timedelta(minutes=5)
    mock_repo = AsyncMock()
    mock_repo.load.return_value = {
        "access_token": "old-access",
        "refresh_token": "refresh-tok",
        "expires_at": expired.isoformat(),
        "scopes": "calendar.readonly",
    }

    mock_http = AsyncMock()
    mock_http.post.return_value = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "new-access",
            "expires_in": 3600,
        },
        raise_for_status=lambda: None,
    )

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=mock_http,
    )

    token = await oauth.get_access_token()
    assert token == "new-access"
    mock_http.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_access_token_returns_cached_when_valid():
    future = datetime.now(UTC) + timedelta(hours=1)
    mock_repo = AsyncMock()
    mock_repo.load.return_value = {
        "access_token": "still-valid",
        "refresh_token": "refresh-tok",
        "expires_at": future.isoformat(),
        "scopes": "calendar.readonly",
    }

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=AsyncMock(),
    )

    token = await oauth.get_access_token()
    assert token == "still-valid"


@pytest.mark.asyncio
async def test_get_access_token_returns_none_when_no_tokens():
    mock_repo = AsyncMock()
    mock_repo.load.return_value = None

    oauth = GoogleOAuth(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8000/auth/google/callback",
        token_repo=mock_repo,
        http_client=AsyncMock(),
    )

    token = await oauth.get_access_token()
    assert token is None

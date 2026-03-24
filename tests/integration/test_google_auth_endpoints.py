import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pulse.app.config import Settings
from pulse.app.main import create_app


def test_auth_google_redirects_to_google():
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
    )
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]
    assert "test-cid" in response.headers["location"]


def test_auth_google_returns_503_when_not_configured():
    settings = Settings()  # no google_client_id
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google")
    assert response.status_code == 503


def test_auth_google_callback_rejects_missing_state():
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
    )
    client = TestClient(create_app(settings=settings))
    response = client.get("/auth/google/callback?code=abc&state=wrong")
    assert response.status_code == 400


def test_auth_google_callback_happy_path(tmp_path):
    settings = Settings(
        google_client_id="test-cid",
        google_client_secret="test-csec",
        google_redirect_uri="http://localhost:8000/auth/google/callback",
        database_path=str(tmp_path / "pulse.db"),
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    # Step 1: initiate OAuth to capture the state token
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    state_match = re.search(r"state=([^&]+)", location)
    assert state_match is not None
    state = state_match.group(1)

    # Step 2: mock the token exchange HTTP call
    mock_response = AsyncMock(
        status_code=200,
        json=lambda: {
            "access_token": "access-ok",
            "refresh_token": "refresh-ok",
            "expires_in": 3600,
            "scope": "calendar.readonly gmail.readonly",
        },
        raise_for_status=lambda: None,
    )
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        response = client.get(f"/auth/google/callback?code=authcode123&state={state}")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}

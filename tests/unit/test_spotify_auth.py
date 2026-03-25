import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pulse.connectors.oauth import OAuthManager
from pulse.connectors.spotify_auth import SpotifyAuthManager


def test_spotify_auth_is_oauth_manager_subclass():
    assert issubclass(SpotifyAuthManager, OAuthManager)


def test_get_auth_url_contains_required_params():
    mgr = SpotifyAuthManager(
        client_id="test_id", client_secret="test_secret",
        token_path=Path("/tmp/sp.json"),
    )
    url = mgr._get_auth_url(
        scopes=["user-read-recently-played", "user-library-read"],
        state="abc123",
    )
    assert "https://accounts.spotify.com/authorize" in url
    assert "client_id=test_id" in url
    assert "state=abc123" in url
    assert "user-read-recently-played" in url
    assert "redirect_uri=" in url


def test_is_token_expired_returns_false_for_fresh_token():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok", "expires_at": time.time() + 3600}
    assert mgr._is_token_expired(token_data) is False


def test_is_token_expired_returns_true_for_expired_token():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok", "expires_at": time.time() - 100}
    assert mgr._is_token_expired(token_data) is True


def test_is_token_expired_returns_true_when_no_expires_at():
    mgr = SpotifyAuthManager(
        client_id="id", client_secret="secret",
        token_path=Path("/tmp/sp.json"),
    )
    token_data = {"access_token": "tok"}
    assert mgr._is_token_expired(token_data) is True


def test_exchange_code_calls_token_endpoint(tmp_path):
    import httpx

    mgr = SpotifyAuthManager(
        client_id="cid", client_secret="csec",
        token_path=tmp_path / "tokens.json",
    )

    mock_response = httpx.Response(
        200,
        json={
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
        request=httpx.Request("POST", "https://accounts.spotify.com/api/token"),
    )

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = mgr._exchange_code("auth_code_123")

    assert result["access_token"] == "new_access"
    assert result["refresh_token"] == "new_refresh"
    assert "expires_at" in result
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["data"]["code"] == "auth_code_123"
    assert call_kwargs.kwargs["data"]["grant_type"] == "authorization_code"


def test_refresh_access_token_calls_token_endpoint(tmp_path):
    import httpx

    mgr = SpotifyAuthManager(
        client_id="cid", client_secret="csec",
        token_path=tmp_path / "tokens.json",
    )

    mock_response = httpx.Response(
        200,
        json={
            "access_token": "refreshed_access",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
        request=httpx.Request("POST", "https://accounts.spotify.com/api/token"),
    )

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = mgr._refresh_access_token({
            "access_token": "old",
            "refresh_token": "my_refresh",
        })

    assert result["access_token"] == "refreshed_access"
    assert result["refresh_token"] == "my_refresh"  # preserved from original
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["data"]["grant_type"] == "refresh_token"
    assert call_kwargs.kwargs["data"]["refresh_token"] == "my_refresh"

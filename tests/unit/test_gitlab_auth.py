"""Unit tests for GitLab OAuth manager."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import httpx

from pulse.connectors.gitlab_auth import GitLabAuthManager
from pulse.connectors.oauth import OAuthManager


def test_gitlab_auth_subclass():
    assert issubclass(GitLabAuthManager, OAuthManager)


def test_gitlab_auth_url_contains_params():
    mgr = GitLabAuthManager(
        client_id="cid",
        client_secret="sec",
        token_path=Path("/tmp/x.json"),
        base_url="https://gitlab.example.com",
    )
    url = mgr._get_auth_url(["read_api"], state="st")
    assert "gitlab.example.com/oauth/authorize" in url
    assert "client_id=cid" in url
    assert "state=st" in url


def test_gitlab_exchange_code(tmp_path):
    mgr = GitLabAuthManager(
        client_id="cid",
        client_secret="csec",
        token_path=tmp_path / "t.json",
        base_url="https://gitlab.com",
    )
    mock_response = httpx.Response(
        200,
        json={
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 7200,
            "token_type": "Bearer",
        },
        request=httpx.Request("POST", "https://gitlab.com/oauth/token"),
    )
    with patch("httpx.post", return_value=mock_response):
        out = mgr._exchange_code("code123")
    assert out["access_token"] == "a"
    assert "expires_at" in out


def test_gitlab_refresh_token(tmp_path):
    mgr = GitLabAuthManager(
        client_id="cid",
        client_secret="csec",
        token_path=tmp_path / "t.json",
    )
    mock_response = httpx.Response(
        200,
        json={"access_token": "new", "expires_in": 7200},
        request=httpx.Request("POST", "https://gitlab.com/oauth/token"),
    )
    with patch("httpx.post", return_value=mock_response):
        out = mgr._refresh_access_token(
            {"refresh_token": "oldr", "access_token": "x"}
        )
    assert out["access_token"] == "new"
    assert out["refresh_token"] == "oldr"


def test_gitlab_token_expiry(tmp_path):
    mgr = GitLabAuthManager(
        client_id="c", client_secret="s", token_path=tmp_path / "t.json",
    )
    assert mgr._is_token_expired({"expires_at": time.time() - 50}) is True
    assert mgr._is_token_expired({"expires_at": time.time() + 7200}) is False

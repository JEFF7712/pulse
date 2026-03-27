"""Unit tests for GitHub OAuth manager."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx

from pulse.connectors.github_auth import GitHubAuthManager
from pulse.connectors.oauth import OAuthManager


def test_github_auth_subclass():
    assert issubclass(GitHubAuthManager, OAuthManager)


def test_github_auth_url():
    mgr = GitHubAuthManager("cid", "sec", Path("/tmp/gh.json"))
    url = mgr._get_auth_url(["read:user", "repo"], state="abc")
    assert "github.com/login/oauth/authorize" in url
    assert "state=abc" in url
    assert "redirect_uri=" in url


def test_github_exchange_code(tmp_path):
    mgr = GitHubAuthManager("cid", "csec", tmp_path / "gh.json")
    mock_response = httpx.Response(
        200,
        json={"access_token": "gh_token", "token_type": "bearer"},
        request=httpx.Request("POST", "https://github.com/login/oauth/access_token"),
    )
    with patch("httpx.post", return_value=mock_response):
        out = mgr._exchange_code("code")
    assert out["access_token"] == "gh_token"


def test_github_token_never_expires_for_refresh_logic(tmp_path):
    mgr = GitHubAuthManager("c", "s", tmp_path / "x.json")
    assert mgr._is_token_expired({"access_token": "x"}) is False

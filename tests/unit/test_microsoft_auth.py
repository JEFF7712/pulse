import time
from pathlib import Path
from unittest.mock import patch

import httpx

from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.connectors.oauth import OAuthManager


def test_microsoft_auth_is_oauth_manager_subclass():
    assert issubclass(MicrosoftAuthManager, OAuthManager)


def test_get_auth_url_contains_params():
    mgr = MicrosoftAuthManager(
        client_id="cid",
        client_secret="sec",
        token_path=Path("/tmp/ms.json"),
        tenant_id="common",
    )
    url = mgr._get_auth_url(
        scopes=["offline_access", "https://graph.microsoft.com/Mail.Read"],
        state="xyz",
    )
    assert "login.microsoftonline.com" in url
    assert "client_id=cid" in url
    assert "state=xyz" in url
    assert "Mail.Read" in url


def test_get_required_scopes_dedupes():
    mgr = MicrosoftAuthManager(
        client_id="c", client_secret="s", token_path=Path("/tmp/x.json"),
    )
    s = mgr.get_required_scopes(["microsoft_mail", "microsoft_calendar"])
    assert "offline_access" in s
    assert s.count("offline_access") == 1


def test_exchange_code(tmp_path):
    mgr = MicrosoftAuthManager(
        client_id="cid",
        client_secret="csec",
        token_path=tmp_path / "t.json",
        tenant_id="common",
    )
    mock_response = httpx.Response(
        200,
        json={
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
        },
        request=httpx.Request("POST", "https://login.microsoftonline.com/common/oauth2/v2.0/token"),
    )
    with patch("httpx.post", return_value=mock_response):
        out = mgr._exchange_code("code123")
    assert out["access_token"] == "a"
    assert "expires_at" in out


def test_token_expiry(tmp_path):
    mgr = MicrosoftAuthManager(
        client_id="c", client_secret="s", token_path=tmp_path / "t.json",
    )
    assert mgr._is_token_expired({"expires_at": time.time() - 10}) is True
    assert mgr._is_token_expired({"expires_at": time.time() + 3600}) is False

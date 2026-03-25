import json
from pathlib import Path


def test_google_auth_manager_is_oauth_manager_subclass():
    from pulse.connectors.google_auth import GoogleAuthManager
    from pulse.connectors.oauth import OAuthManager
    assert issubclass(GoogleAuthManager, OAuthManager)


def test_get_required_scopes_unions_enabled_connectors():
    from pulse.connectors.google_auth import GoogleAuthManager
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=Path("/tmp/tokens.json")
    )
    scopes = mgr.get_required_scopes(["gmail", "youtube"])
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/youtube.readonly" in scopes
    assert "https://www.googleapis.com/auth/calendar.readonly" not in scopes


def test_get_required_scopes_returns_empty_for_no_connectors():
    from pulse.connectors.google_auth import GoogleAuthManager
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=Path("/tmp/tokens.json")
    )
    assert mgr.get_required_scopes([]) == []


def test_is_authorized_returns_false_when_no_token_file(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=tmp_path / "missing.json"
    )
    assert mgr.is_authorized() is False


def test_is_authorized_returns_true_when_valid_token_exists(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager
    token_path = tmp_path / "tokens.json"
    token_path.write_text(json.dumps({
        "token": "access_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "id",
        "client_secret": "secret",
    }))
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=token_path
    )
    assert mgr.is_authorized() is True


def test_is_authorized_returns_false_for_invalid_json(tmp_path):
    from pulse.connectors.google_auth import GoogleAuthManager
    token_path = tmp_path / "tokens.json"
    token_path.write_text("not json")
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=token_path
    )
    assert mgr.is_authorized() is False

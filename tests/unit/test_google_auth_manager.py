import json
import webbrowser
from pathlib import Path
from unittest.mock import MagicMock, patch


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


def test_authorize_retries_without_browser_on_webbrowser_error(tmp_path, monkeypatch):
    monkeypatch.delenv("PULSE_OAUTH_NO_BROWSER", raising=False)
    monkeypatch.delenv("PULSE_GOOGLE_OAUTH_PORT", raising=False)
    monkeypatch.setenv("PULSE_GOOGLE_OAUTH_FALLBACK_PORT", "8765")

    from pulse.connectors.google_auth import GoogleAuthManager

    fake_creds = MagicMock()
    fake_creds.token = "t"
    fake_creds.refresh_token = "r"
    fake_creds.token_uri = "https://oauth2.googleapis.com/token"
    fake_creds.client_id = "id"
    fake_creds.client_secret = "secret"

    flows = []

    def fake_from_client_config(config, scopes):
        flow = MagicMock()

        def run_local_server(*, port, open_browser, authorization_prompt_message):
            flows.append((port, open_browser))
            if open_browser:
                raise webbrowser.Error("no browser")
            return fake_creds

        flow.run_local_server.side_effect = run_local_server
        return flow

    token_path = tmp_path / "google_tokens.json"
    mgr = GoogleAuthManager(
        client_id="id", client_secret="secret", token_path=token_path
    )

    with patch(
        "pulse.connectors.google_auth.InstalledAppFlow.from_client_config",
        side_effect=fake_from_client_config,
    ):
        mgr.authorize(["https://www.googleapis.com/auth/gmail.readonly"])

    assert flows == [(0, True), (8765, False)]
    assert token_path.exists()

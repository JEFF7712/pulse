import json
from pathlib import Path

from pulse.connectors.oauth import OAuthManager


class FakeOAuthManager(OAuthManager):
    def _get_auth_url(self, scopes, state):
        return f"https://fake.com/auth?state={state}"

    def _exchange_code(self, code):
        return {"access_token": "new_token", "refresh_token": "new_refresh"}

    def _refresh_access_token(self, token_data):
        return {**token_data, "access_token": "refreshed_token"}

    def _is_token_expired(self, token_data):
        return token_data.get("expired", False)


def test_is_authorized_returns_false_when_no_file(tmp_path):
    mgr = FakeOAuthManager(token_path=tmp_path / "missing.json")
    assert mgr.is_authorized() is False


def test_save_and_load_tokens(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok", "refresh_token": "ref"})

    loaded = mgr.load_tokens()
    assert loaded["access_token"] == "tok"
    assert loaded["refresh_token"] == "ref"


def test_is_authorized_returns_true_after_save(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok"})
    assert mgr.is_authorized() is True


def test_load_tokens_returns_none_for_invalid_json(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text("not json")
    mgr = FakeOAuthManager(token_path=token_path)
    assert mgr.load_tokens() is None


def test_get_valid_token_returns_access_token(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "my_token", "expired": False})
    assert mgr.get_valid_token() == "my_token"


def test_get_valid_token_refreshes_when_expired(tmp_path):
    token_path = tmp_path / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "old", "refresh_token": "ref", "expired": True})
    assert mgr.get_valid_token() == "refreshed_token"
    # Verify refreshed token was persisted
    loaded = mgr.load_tokens()
    assert loaded["access_token"] == "refreshed_token"


def test_get_valid_token_raises_when_not_authorized(tmp_path):
    import pytest
    mgr = FakeOAuthManager(token_path=tmp_path / "missing.json")
    with pytest.raises(RuntimeError):
        mgr.get_valid_token()


def test_save_tokens_creates_parent_dirs(tmp_path):
    token_path = tmp_path / "nested" / "dir" / "tokens.json"
    mgr = FakeOAuthManager(token_path=token_path)
    mgr.save_tokens({"access_token": "tok"})
    assert token_path.exists()

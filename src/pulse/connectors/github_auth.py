"""GitHub OAuth (no refresh token — access tokens do not expire until revoked)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

GITHUB_AUTH_PORT = 8891
GITHUB_REDIRECT_URI = "http://localhost:8891/callback"
GITHUB_SCOPES = ["read:user", "repo"]
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubAuthManager(OAuthManager):
    def __init__(self, client_id: str, client_secret: str, token_path: Path) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": GITHUB_REDIRECT_URI,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            GITHUB_TOKEN_URL,
            headers={
                "Accept": "application/json",
            },
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
        )
        response.raise_for_status()
        data = response.json()
        if "access_token" not in data:
            raise RuntimeError(data.get("error_description", "GitHub token exchange failed"))
        # GitHub does not return refresh_token for this flow
        data["expires_at"] = None
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        return token_data

    def _is_token_expired(self, token_data: dict) -> bool:
        return False

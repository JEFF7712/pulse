"""GitLab OAuth2 (refresh supported)."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

GITLAB_AUTH_PORT = 8892
GITLAB_REDIRECT_URI = "http://localhost:8892/callback"
GITLAB_SCOPES = ["read_api", "read_user"]


class GitLabAuthManager(OAuthManager):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path,
        base_url: str = "https://gitlab.com",
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")

    def _authorize_endpoint(self) -> str:
        return f"{self._base_url}/oauth/authorize"

    def _token_endpoint(self) -> str:
        return f"{self._base_url}/oauth/token"

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": GITLAB_REDIRECT_URI,
            "response_type": "code",
            "state": state,
            "scope": " ".join(scopes),
        }
        return f"{self._authorize_endpoint()}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            self._token_endpoint(),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GITLAB_REDIRECT_URI,
            },
        )
        response.raise_for_status()
        data = response.json()
        expires_in = int(data.get("expires_in", 7200))
        data["expires_at"] = time.time() + expires_in
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        response = httpx.post(
            self._token_endpoint(),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
            },
        )
        response.raise_for_status()
        refreshed = response.json()
        expires_in = int(refreshed.get("expires_in", 7200))
        refreshed["expires_at"] = time.time() + expires_in
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = token_data["refresh_token"]
        return refreshed

    def _is_token_expired(self, token_data: dict) -> bool:
        expires_at = token_data.get("expires_at")
        if expires_at is None:
            return False
        return time.time() > (float(expires_at) - 120)

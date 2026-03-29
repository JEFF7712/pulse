"""Oura Cloud API OAuth2 (sleep / readiness via ``daily`` scope)."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

OURA_AUTH_PORT = 8894
OURA_REDIRECT_URI = f"http://localhost:{OURA_AUTH_PORT}/callback"
OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"
# `daily` covers sleep, readiness, and daily activity; `workout` adds session rows.
OURA_SCOPES = ["daily", "workout"]


class OuraAuthManager(OAuthManager):
    def __init__(self, client_id: str, client_secret: str, token_path: Path) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": OURA_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{OURA_AUTHORIZE_URL}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            OURA_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OURA_REDIRECT_URI,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        expires_in = int(data.get("expires_in", 3600))
        data["expires_at"] = time.time() + expires_in
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        response = httpx.post(
            OURA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        refreshed = response.json()
        expires_in = int(refreshed.get("expires_in", 3600))
        refreshed["expires_at"] = time.time() + expires_in
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = token_data["refresh_token"]
        return refreshed

    def _is_token_expired(self, token_data: dict) -> bool:
        expires_at = token_data.get("expires_at")
        if expires_at is None:
            return True
        return time.time() > (float(expires_at) - 120)

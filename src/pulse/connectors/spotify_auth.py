import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

SPOTIFY_SCOPES = [
    "user-read-recently-played",
    "user-library-read",
    "user-top-read",
]

REDIRECT_URI = "http://localhost:8888/callback"


class SpotifyAuthManager(OAuthManager):
    AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        data = response.json()
        data["expires_at"] = time.time() + data.get("expires_in", 3600)
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        response = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
            },
            auth=(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        refreshed = response.json()
        refreshed["expires_at"] = time.time() + refreshed.get("expires_in", 3600)
        # Spotify may not return a new refresh_token — preserve the old one
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = token_data["refresh_token"]
        return refreshed

    def _is_token_expired(self, token_data: dict) -> bool:
        expires_at = token_data.get("expires_at")
        if expires_at is None:
            return True
        # Refresh 2 minutes early to avoid edge cases
        return time.time() > (expires_at - 120)

"""Microsoft Identity Platform OAuth2 for Microsoft Graph (delegated)."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from pulse.connectors.oauth import OAuthManager

# Scopes use Graph resource URI form (v2 endpoint).
SCOPE_PREFIX = "https://graph.microsoft.com/"

SCOPES_BY_CONNECTOR: dict[str, list[str]] = {
    "microsoft_mail": [f"{SCOPE_PREFIX}Mail.Read"],
    "microsoft_calendar": [f"{SCOPE_PREFIX}Calendars.Read"],
}

# Public client redirect is not used — confidential client with localhost redirect.
MICROSOFT_REDIRECT_URI = "http://localhost:8890/callback"
MICROSOFT_AUTH_PORT = 8890


class MicrosoftAuthManager(OAuthManager):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path,
        tenant_id: str = "common",
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id or "common"

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    def _token_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        )

    def _authorize_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/authorize"
        )

    def get_required_scopes(self, active_connectors: list[str]) -> list[str]:
        scopes: list[str] = ["offline_access"]
        for name in active_connectors:
            scopes.extend(SCOPES_BY_CONNECTOR.get(name, []))
        # Dedupe preserving order
        seen: set[str] = set()
        out: list[str] = []
        for s in scopes:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": MICROSOFT_REDIRECT_URI,
            "response_mode": "query",
            "scope": " ".join(scopes),
            "state": state,
        }
        return f"{self._authorize_url()}?{urlencode(params)}"

    def _exchange_code(self, code: str) -> dict:
        response = httpx.post(
            self._token_url(),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": MICROSOFT_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()
        expires_in = int(data.get("expires_in", 3600))
        data["expires_at"] = time.time() + expires_in
        return data

    def _refresh_access_token(self, token_data: dict) -> dict:
        response = httpx.post(
            self._token_url(),
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
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

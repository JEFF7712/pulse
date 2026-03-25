import json
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES_BY_CONNECTOR: dict[str, list[str]] = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "youtube": ["https://www.googleapis.com/auth/youtube.readonly"],
}


class GoogleAuthManager:
    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_path = token_path

    def get_required_scopes(self, active_connectors: list[str]) -> list[str]:
        scopes: list[str] = []
        for name in active_connectors:
            scopes.extend(SCOPES_BY_CONNECTOR.get(name, []))
        return scopes

    def is_authorized(self) -> bool:
        if not self._token_path.exists():
            return False
        try:
            creds = self._load_credentials()
            return creds is not None
        except Exception:
            return False

    def get_credentials(self) -> Credentials:
        creds = self._load_credentials()
        if creds is None:
            raise RuntimeError(
                "Not authorized. Run 'pulse auth google' first."
            )
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            self._save_credentials(creds)
        return creds

    def authorize(self, scopes: list[str]) -> None:
        client_config = {
            "installed": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        creds = flow.run_local_server(port=0)
        self._save_credentials(creds)
        logger.info("Google authorization complete. Tokens saved to %s", self._token_path)

    def _load_credentials(self) -> Credentials | None:
        try:
            data = json.loads(self._token_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", self._client_id),
            client_secret=data.get("client_secret", self._client_secret),
        )

    def _save_credentials(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
        }
        self._token_path.write_text(json.dumps(data))

import json
import logging
import os
import sys
import webbrowser
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from pulse.connectors.oauth import OAuthManager
from pulse.domain.connectors import ConnectorAuthError

logger = logging.getLogger(__name__)

SCOPES_BY_CONNECTOR: dict[str, list[str]] = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "youtube": ["https://www.googleapis.com/auth/youtube.readonly"],
}


class GoogleAuthManager(OAuthManager):
    def __init__(
        self, client_id: str, client_secret: str, token_path: Path
    ) -> None:
        super().__init__(token_path)
        self._client_id = client_id
        self._client_secret = client_secret

    def get_required_scopes(self, active_connectors: list[str]) -> list[str]:
        scopes: list[str] = []
        for name in active_connectors:
            scopes.extend(SCOPES_BY_CONNECTOR.get(name, []))
        return scopes

    # --- OAuthManager abstract methods (used by base class, but Google
    #     overrides get_valid_token so these are only called if someone
    #     uses the base class path directly) ---

    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        # Not used — Google auth uses InstalledAppFlow.run_local_server
        raise NotImplementedError("Use authorize() for Google OAuth")

    def _exchange_code(self, code: str) -> dict:
        raise NotImplementedError("Use authorize() for Google OAuth")

    def _refresh_access_token(self, token_data: dict) -> dict:
        raise NotImplementedError("Google refresh is handled in get_credentials()")

    def _is_token_expired(self, token_data: dict) -> bool:
        # Not used — Google credential expiry is checked via Credentials object
        return False

    # --- Google-specific API (preserved for backward compatibility) ---

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
            raise ConnectorAuthError(
                "Not authorized. Run `pulse configure` → Connectors and open a Google-backed source (Gmail, Calendar, YouTube)."
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
        prompt = (
            "Open this URL in your browser to authorize Google "
            "(Gmail, Calendar, YouTube):\n{url}\n"
        )

        def run_local(open_browser: bool, port: int):
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            return flow.run_local_server(
                port=port,
                open_browser=open_browser,
                authorization_prompt_message=prompt,
            )

        configured = int(os.environ.get("PULSE_GOOGLE_OAUTH_PORT", "0") or "0")
        fallback = int(os.environ.get("PULSE_GOOGLE_OAUTH_FALLBACK_PORT", "8765") or "8765")
        no_browser = os.environ.get("PULSE_OAUTH_NO_BROWSER", "").lower() in (
            "1",
            "true",
            "yes",
        )

        creds = None
        if no_browser:
            port = configured or fallback
            if configured == 0:
                print(
                    "\nPULSE_OAUTH_NO_BROWSER is set. OAuth callback listens on "
                    f"localhost:{port} on this machine.\n"
                    "From your laptop, forward that port, then open the printed URL:\n"
                    f"  ssh -L {port}:localhost:{port} user@this-host\n",
                    file=sys.stderr,
                )
            creds = run_local(open_browser=False, port=port)
        else:
            try:
                creds = run_local(open_browser=True, port=configured)
            except webbrowser.Error:
                port = configured or fallback
                print(
                    "\nNo graphical browser found here. Open the printed URL in a "
                    "browser on your computer.\n"
                    "If you connected via SSH, forward this port first (use the same "
                    f"number in both places), then open the link:\n"
                    f"  ssh -L {port}:localhost:{port} user@this-host\n",
                    file=sys.stderr,
                )
                creds = run_local(open_browser=False, port=port)

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

import json
from abc import ABC, abstractmethod
from pathlib import Path

from pulse.domain.connectors import ConnectorAuthError


class OAuthManager(ABC):
    def __init__(self, token_path: Path) -> None:
        self._token_path = token_path

    @abstractmethod
    def _get_auth_url(self, scopes: list[str], state: str) -> str:
        """Build the authorization URL for the provider."""

    @abstractmethod
    def _exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens. Returns token dict."""

    @abstractmethod
    def _refresh_access_token(self, token_data: dict) -> dict:
        """Refresh an expired access token. Returns updated token dict."""

    @abstractmethod
    def _is_token_expired(self, token_data: dict) -> bool:
        """Check if the stored access token has expired."""

    def is_authorized(self) -> bool:
        if not self._token_path.exists():
            return False
        return self.load_tokens() is not None

    def load_tokens(self) -> dict | None:
        try:
            return json.loads(self._token_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save_tokens(self, token_data: dict) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(token_data))

    def get_valid_token(self) -> str:
        token_data = self.load_tokens()
        if token_data is None:
            raise ConnectorAuthError("Not authorized.")
        if self._is_token_expired(token_data):
            token_data = self._refresh_access_token(token_data)
            self.save_tokens(token_data)
        return token_data["access_token"]

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/gmail.readonly"
)


def build_authorization_url(
    client_id: str, redirect_uri: str
) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH_URL}?{params}", state


class GoogleOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_repo,
        http_client,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_repo = token_repo
        self._http_client = http_client

    async def exchange_code(self, code: str) -> None:
        response = await self._http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": self._redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()

        expires_at = datetime.now(UTC) + timedelta(seconds=data["expires_in"])
        await self._token_repo.save(
            provider="google",
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=expires_at,
            scopes=data.get("scope", SCOPES),
        )

    async def get_access_token(self) -> str | None:
        token_data = await self._token_repo.load("google")
        if token_data is None:
            return None

        expires_at = datetime.fromisoformat(token_data["expires_at"])
        if expires_at > datetime.now(UTC) + timedelta(minutes=2):
            return token_data["access_token"]

        return await self._refresh(token_data["refresh_token"])

    async def _refresh(self, refresh_token: str) -> str:
        response = await self._http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()

        expires_at = datetime.now(UTC) + timedelta(seconds=data["expires_in"])
        await self._token_repo.save(
            provider="google",
            access_token=data["access_token"],
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=data.get("scope", SCOPES),
        )
        return data["access_token"]

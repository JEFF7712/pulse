import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

GMAIL_LIST_URL = "https://www.googleapis.com/gmail/v1/users/me/messages"
GMAIL_MESSAGE_URL = "https://www.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
logger = logging.getLogger(__name__)


class GoogleGmailClient:
    def __init__(self, oauth, http_client) -> None:
        self._oauth = oauth
        self._http = http_client

    async def list_messages(self, since: datetime | None = None) -> list[dict]:
        token = await self._oauth.get_access_token()
        if token is None:
            logger.warning("No Google OAuth token available; skipping gmail pull.")
            return []

        headers = {"Authorization": f"Bearer {token}"}
        params: dict[str, str] = {"maxResults": "100"}
        if since is not None:
            epoch = int(since.timestamp())
            params["q"] = f"after:{epoch}"

        response = await self._http.get(GMAIL_LIST_URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        message_stubs = data.get("messages", [])
        if not message_stubs:
            return []

        results = []
        for stub in message_stubs:
            detail_resp = await self._http.get(
                GMAIL_MESSAGE_URL.format(msg_id=stub["id"]),
                params={"format": "metadata", "metadataHeaders": "Subject,From"},
                headers=headers,
            )
            detail_resp.raise_for_status()
            results.append(detail_resp.json())

        return results


class GmailConnector(Connector):
    def __init__(self, client: Any, sync_state_repo=None) -> None:
        self._client = client
        self._sync_state_repo = sync_state_repo

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_messages(since=since)
        events = [self._to_event(row) for row in rows]
        if events and self._sync_state_repo is not None:
            latest = max(e.timestamp for e in events)
            await self._sync_state_repo.save("gmail", latest.isoformat())
        return events

    def get_source_name(self) -> str:
        return "gmail"

    def _to_event(self, row: dict[str, Any]) -> Event:
        headers = self._headers_by_name(row.get("payload", {}).get("headers", []))
        return Event(
            id=f"gmail:{row['id']}",
            timestamp=datetime.fromtimestamp(int(row["internalDate"]) / 1000, tz=UTC),
            source="gmail",
            event_type="email.received",
            data={
                "subject": headers.get("subject", ""),
                "sender": headers.get("from", ""),
            },
        )

    def _headers_by_name(self, headers: list[dict[str, str]]) -> dict[str, str]:
        return {
            header["name"].lower(): header.get("value", "")
            for header in headers
            if "name" in header
        }

    @classmethod
    async def from_settings(cls, settings, db: aiosqlite.Connection, http_client=None) -> "GmailConnector":
        from pulse.connectors.google_auth import GoogleOAuth
        from pulse.store.oauth import OAuthTokenRepository
        from pulse.store.sync_state import SyncStateRepository
        import httpx

        token_repo = OAuthTokenRepository(db)
        if http_client is None:
            http_client = httpx.AsyncClient()
        oauth = GoogleOAuth(
            client_id=settings.google_client_id or "",
            client_secret=settings.google_client_secret or "",
            redirect_uri=settings.google_redirect_uri,
            token_repo=token_repo,
            http_client=http_client,
        )
        client = GoogleGmailClient(oauth=oauth, http_client=http_client)
        sync_repo = SyncStateRepository(db)
        return cls(client=client, sync_state_repo=sync_repo)

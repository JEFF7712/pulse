import logging
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    def __init__(self, oauth, http_client) -> None:
        self._oauth = oauth
        self._http = http_client

    async def list_events(self, since: datetime | None = None) -> list[dict]:
        token = await self._oauth.get_access_token()
        if token is None:
            logger.warning("No Google OAuth token available; skipping calendar pull.")
            return []

        params: dict[str, str] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        if since is not None:
            params["timeMin"] = since.isoformat()

        all_items: list[dict] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            response = await self._http.get(
                CALENDAR_EVENTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            data = response.json()
            all_items.extend(data.get("items", []))

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return all_items


class GoogleCalendarConnector(Connector):
    def __init__(self, client: Any, sync_state_repo=None) -> None:
        self._client = client
        self._sync_state_repo = sync_state_repo

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_events(since=since)
        events = [self._to_event(row) for row in rows]
        if events and self._sync_state_repo is not None:
            latest = max(e.timestamp for e in events)
            await self._sync_state_repo.save("calendar", latest.isoformat())
        return events

    def get_source_name(self) -> str:
        return "calendar"

    def _to_event(self, row: dict[str, Any]) -> Event:
        start = row["start"]
        timestamp = self._parse_start(start)
        title = row.get("summary") or "Untitled event"
        return Event(
            id=f"calendar:{row['id']}",
            timestamp=timestamp,
            source="calendar",
            event_type="calendar.event",
            data={"title": title},
        )

    def _parse_start(self, start: dict[str, str]) -> datetime:
        if "dateTime" in start:
            return datetime.fromisoformat(start["dateTime"])

        return datetime.fromisoformat(start["date"]).replace(tzinfo=UTC)

    @classmethod
    async def from_settings(cls, settings, db: aiosqlite.Connection, http_client=None) -> "GoogleCalendarConnector":
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
        client = GoogleCalendarClient(oauth=oauth, http_client=http_client)
        sync_repo = SyncStateRepository(db)
        return cls(client=client, sync_state_repo=sync_repo)

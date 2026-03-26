from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GoogleCalendarConnector(Connector):
    def __init__(self, auth_manager: GoogleAuthManager | None = None, client: Any = None) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        service = self._get_client()

        # Use updatedMin for incremental sync (tracks when events were
        # created/modified, not when they occur). This avoids the cursor
        # jumping to far-future recurring events.
        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": 250,
            "singleEvents": True,
            "orderBy": "updated",
        }
        if since is not None:
            kwargs["updatedMin"] = since.isoformat()
        else:
            # Default: events updated in the last 30 days
            kwargs["updatedMin"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()

        results = service.events().list(**kwargs).execute()
        items = results.get("items", [])

        events = [self._to_event(item) for item in items]
        # Store the pull timestamp as the cursor (not max event start time)
        self._last_pull_time = datetime.now(UTC)
        return events

    def get_sync_timestamp(self) -> datetime:
        """Return the time of the last pull, for use as the sync cursor."""
        return getattr(self, "_last_pull_time", datetime.now(UTC))

    def get_source_name(self) -> str:
        return "calendar"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        if self._client is not None:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._auth_manager is None:
            raise RuntimeError("No auth_manager or client provided")
        creds = self._auth_manager.get_credentials()
        from googleapiclient.discovery import build
        return build("calendar", "v3", credentials=creds)

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

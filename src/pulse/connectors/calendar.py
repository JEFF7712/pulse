import json
from datetime import UTC, datetime, timedelta
from typing import Any

from googleapiclient.errors import HttpError

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

# Google Calendar v3 rejects updatedMin more than roughly a few weeks in the past (410
# updatedMinTooLongAgo). Stay under that window for default / incremental pulls.
_CALENDAR_UPDATED_MIN_WINDOW = timedelta(days=21)
# When the cursor is too stale, refetch by event start time (bounded) without updatedMin.
_CALENDAR_RESYNC_START_LOOKBACK = timedelta(days=365)
# `singleEvents=True` expands recurring series into one instance per occurrence. Without
# an upper bound a yearly event materialises decades of rows, which buries the real
# calendar and pins `last_event` far in the future. Cap how far ahead we materialise.
_CALENDAR_FUTURE_HORIZON = timedelta(days=180)
_CALENDAR_RESYNC_PAGE_SIZE = 2500
_CALENDAR_RESYNC_MAX_EVENTS = 10_000


def _is_updated_min_too_long_ago(exc: HttpError) -> bool:
    if exc.resp.status != 410:
        return False
    try:
        data = json.loads(exc.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return False
    for err in data.get("error", {}).get("errors", []):
        if err.get("reason") == "updatedMinTooLongAgo":
            return True
    return False


class GoogleCalendarConnector(Connector):
    def __init__(
        self, auth_manager: GoogleAuthManager | None = None, client: Any = None
    ) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        service = self._get_client()

        items = self._list_events(service, since)

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

    def _list_events(
        self, service: Any, since: datetime | None
    ) -> list[dict[str, Any]]:
        """List raw event dicts; on stale updatedMin, fall back to a start-time bounded resync."""
        now = datetime.now(UTC)
        kwargs: dict[str, Any] = {
            "calendarId": "primary",
            "maxResults": 250,
            "singleEvents": True,
            "orderBy": "updated",
            "timeMax": (now + _CALENDAR_FUTURE_HORIZON).isoformat(),
        }
        if since is not None:
            su = since.astimezone(UTC) if since.tzinfo else since.replace(tzinfo=UTC)
            kwargs["updatedMin"] = su.isoformat()
        else:
            kwargs["updatedMin"] = (now - _CALENDAR_UPDATED_MIN_WINDOW).isoformat()

        try:
            results = service.events().list(**kwargs).execute()
            return results.get("items", [])
        except HttpError as exc:
            if not _is_updated_min_too_long_ago(exc):
                raise
            return self._list_events_resync(service, now)

    def _list_events_resync(self, service: Any, now: datetime) -> list[dict[str, Any]]:
        """Full list by event start time after 410 updatedMinTooLongAgo (paginated)."""
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        time_min = (now - _CALENDAR_RESYNC_START_LOOKBACK).isoformat()
        time_max = (now + _CALENDAR_FUTURE_HORIZON).isoformat()
        while True:
            results = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=_CALENDAR_RESYNC_PAGE_SIZE,
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            items.extend(results.get("items", []))
            page_token = results.get("nextPageToken")
            if not page_token or len(items) >= _CALENDAR_RESYNC_MAX_EVENTS:
                break
        return items

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

"""Microsoft Graph calendar → Pulse events (calendar.event)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _parse_graph_datetime(dt: str) -> datetime:
    """Graph returns dateTime + timeZone; treat as UTC if ends with Z or offset."""
    if not dt:
        return datetime.now(UTC)
    if dt.endswith("Z"):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(dt)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return datetime.now(UTC)


class MicrosoftCalendarConnector(Connector):
    def __init__(
        self,
        auth_manager: MicrosoftAuthManager | None = None,
        http_client: httpx.AsyncClient | None = None,
        calendar_id: str | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._http = http_client
        self._calendar_id = calendar_id or "primary"

    def get_source_name(self) -> str:
        return "microsoft_calendar"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _auth_headers(self) -> dict[str, str]:
        assert self._auth_manager is not None
        token = self._auth_manager.get_valid_token()
        return {"Authorization": f"Bearer {token}"}

    def _events_url(self) -> str:
        """Default calendar uses /me/events; named calendars use /me/calendars/{id}/events."""
        cid = self._calendar_id
        if not cid or cid == "primary":
            return f"{GRAPH_BASE}/me/events"
        return f"{GRAPH_BASE}/me/calendars/{cid}/events"

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        try:
            params: dict[str, str] = {
                "$top": "250",
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,lastModifiedDateTime",
            }
            if since is not None:
                su = since.astimezone(UTC) if since.tzinfo else since.replace(tzinfo=UTC)
                params["$filter"] = (
                    f"lastModifiedDateTime ge {su.strftime('%Y-%m-%dT%H:%M:%S.0000000Z')}"
                )

            path = self._events_url()
            resp = await client.get(path, params=params, headers=self._auth_headers())
            resp.raise_for_status()
            data = resp.json()
            events: list[Event] = []
            for row in data.get("value", []):
                events.append(self._to_event(row))
            return events
        finally:
            if owns:
                await client.aclose()

    def _to_event(self, row: dict[str, Any]) -> Event:
        start = row.get("start") or {}
        dt = start.get("dateTime", "")
        timestamp = _parse_graph_datetime(dt)
        title = row.get("subject") or "Untitled event"
        return Event(
            id=f"m365cal:{row['id']}",
            timestamp=timestamp,
            source="microsoft_calendar",
            event_type="calendar.event",
            data={"title": title},
        )

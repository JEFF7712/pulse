from datetime import UTC, datetime
from typing import Any

from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GoogleCalendarConnector(Connector):
    def __init__(self, client: Any) -> None:
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_events(since=since)
        return [self._to_event(row) for row in rows]

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

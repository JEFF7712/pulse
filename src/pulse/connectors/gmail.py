from datetime import UTC, datetime
from typing import Any

from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GmailConnector(Connector):
    def __init__(self, client: Any) -> None:
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        rows = await self._client.list_messages(since=since)
        return [self._to_event(row) for row in rows]

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

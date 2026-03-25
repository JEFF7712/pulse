from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class GmailConnector(Connector):
    def __init__(self, auth_manager: GoogleAuthManager | None = None, client: Any = None) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._get_client()
        rows = await client.list_messages(since=since)
        return [self._to_event(row) for row in rows]

    def get_source_name(self) -> str:
        return "gmail"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

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
        return build("gmail", "v1", credentials=creds)

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

from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

# Gmail's own inbox categories, mapped to a compact tag. "promotions"/"social"/
# "updates"/"forums" are bulk/low-signal; "primary" is real correspondence.
_GMAIL_CATEGORY_LABELS = {
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
    "CATEGORY_PERSONAL": "primary",
}


def _category_from_labels(label_ids: list[str]) -> str:
    for label in label_ids:
        mapped = _GMAIL_CATEGORY_LABELS.get(label)
        if mapped is not None:
            return mapped
    return "primary"


class GmailConnector(Connector):
    def __init__(
        self, auth_manager: GoogleAuthManager | None = None, client: Any = None
    ) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        service = self._get_client()

        query = ""
        if since is not None:
            # Gmail uses epoch seconds for after: filter
            epoch = int(since.timestamp())
            query = f"after:{epoch}"

        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=100)
            .execute()
        )
        message_ids = results.get("messages", [])

        events = []
        for msg_stub in message_ids:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_stub["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From"],
                )
                .execute()
            )
            events.append(self._to_event(msg))

        return events

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
                "category": _category_from_labels(row.get("labelIds", [])),
            },
        )

    def _headers_by_name(self, headers: list[dict[str, str]]) -> dict[str, str]:
        return {
            header["name"].lower(): header.get("value", "")
            for header in headers
            if "name" in header
        }

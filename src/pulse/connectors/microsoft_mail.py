"""Microsoft Graph mail → Pulse events (email.received)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import formataddr
from typing import Any

import httpx

from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _format_sender(from_obj: dict[str, Any] | None) -> str:
    if not from_obj:
        return ""
    ea = from_obj.get("emailAddress") or {}
    name = (ea.get("name") or "").strip()
    addr = (ea.get("address") or "").strip()
    if name and addr:
        return formataddr((name, addr))
    return addr or name


class MicrosoftMailConnector(Connector):
    def __init__(
        self,
        auth_manager: MicrosoftAuthManager | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._http = http_client

    def get_source_name(self) -> str:
        return "microsoft_mail"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _auth_headers(self) -> dict[str, str]:
        assert self._auth_manager is not None
        token = self._auth_manager.get_valid_token()
        return {"Authorization": f"Bearer {token}"}

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        try:
            params: dict[str, str] = {
                "$top": "100",
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime",
            }
            if since is not None:
                su = since.astimezone(UTC) if since.tzinfo else since.replace(tzinfo=UTC)
                # OData datetime literal
                params["$filter"] = f"receivedDateTime ge {su.strftime('%Y-%m-%dT%H:%M:%SZ')}"

            resp = await client.get(
                f"{GRAPH_BASE}/me/messages",
                params=params,
                headers=self._auth_headers(),
            )
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
        rid = row["id"]
        raw_time = row.get("receivedDateTime", "")
        ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        sender = _format_sender(row.get("from"))
        subject = row.get("subject") or ""
        return Event(
            id=f"m365mail:{rid}",
            timestamp=ts,
            source="microsoft_mail",
            event_type="email.received",
            data={
                "subject": subject,
                "sender": sender,
                "from": sender,
            },
        )

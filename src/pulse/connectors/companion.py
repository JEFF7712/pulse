"""Companion app push connector — ingests location and health events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pulse.domain.connectors import PushConnector
from pulse.domain.events import Event

_ALLOWED_EVENT_TYPES = {
    "location.enter",
    "location.exit",
    "health.steps",
    "health.sleep",
}


class CompanionPayloadError(ValueError):
    pass


class CompanionConnector(PushConnector):
    def get_source_name(self) -> str:
        return "companion"

    def get_webhook_path(self) -> str:
        return "/webhooks/companion"

    async def handle_webhook(self, payload: dict[str, Any]) -> list[Event]:
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return []

        events: list[Event] = []
        for raw in raw_events:
            event = self._parse_event(raw)
            if event is not None:
                events.append(event)
        return events

    def _parse_event(self, raw: dict[str, Any]) -> Event | None:
        if not isinstance(raw, dict):
            return None

        event_type = raw.get("type", "")
        if event_type not in _ALLOWED_EVENT_TYPES:
            return None

        timestamp_str = raw.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            raise CompanionPayloadError(
                "Companion timestamps must be ISO 8601 and timezone-aware"
            )
        if timestamp.tzinfo is None:
            raise CompanionPayloadError(
                "Companion timestamps must be ISO 8601 and timezone-aware"
            )
        timestamp = timestamp.astimezone(UTC)

        data = raw.get("data", {})

        return Event(
            id=f"companion:{uuid4()}",
            timestamp=timestamp,
            source="companion",
            event_type=event_type,
            data=data,
            metadata={},
        )

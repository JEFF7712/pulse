"""Unit tests for Microsoft Graph calendar connector."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.connectors.microsoft_calendar import GRAPH_BASE, MicrosoftCalendarConnector


def _auth(tmp_path: Path) -> MicrosoftAuthManager:
    p = tmp_path / "ms.json"
    mgr = MicrosoftAuthManager("id", "sec", p, tenant_id="common")
    mgr.save_tokens(
        {
            "access_token": "tok",
            "refresh_token": "r",
            "expires_at": __import__("time").time() + 3600,
        }
    )
    return mgr


def test_microsoft_calendar_primary_uses_me_events(tmp_path):
    payload = {
        "value": [
            {
                "id": "evt-1",
                "subject": "Sync",
                "start": {"dateTime": "2026-03-26T10:00:00Z", "timeZone": "UTC"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        assert "/me/events" in u
        assert "calendars" not in u
        return httpx.Response(200, json=payload)

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = MicrosoftCalendarConnector(
            auth_manager=_auth(tmp_path),
            http_client=client,
            calendar_id="primary",
        )
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert len(events) == 1
    assert events[0].id == "m365cal:evt-1"
    assert events[0].event_type == "calendar.event"
    assert events[0].data["title"] == "Sync"


def test_microsoft_calendar_named_calendar_url(tmp_path):
    called_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_urls.append(str(request.url))
        return httpx.Response(200, json={"value": []})

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = MicrosoftCalendarConnector(
            auth_manager=_auth(tmp_path),
            http_client=client,
            calendar_id="cal-uuid-123",
        )
        await conn.pull(since=None)
        await client.aclose()

    asyncio.run(run())
    assert any("/me/calendars/cal-uuid-123/events" in u for u in called_urls)

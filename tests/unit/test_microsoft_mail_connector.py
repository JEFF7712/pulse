"""Unit tests for Microsoft Graph mail connector."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.connectors.microsoft_mail import GRAPH_BASE, MicrosoftMailConnector


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


def test_microsoft_mail_pull_maps_messages(tmp_path):
    payload = {
        "value": [
            {
                "id": "msg-1",
                "subject": "Hello",
                "receivedDateTime": "2026-03-26T14:00:00Z",
                "from": {
                    "emailAddress": {"name": "Alice", "address": "alice@example.com"},
                },
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).startswith(f"{GRAPH_BASE}/me/messages")
        assert "messages" in str(request.url)
        return httpx.Response(200, json=payload)

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = MicrosoftMailConnector(auth_manager=_auth(tmp_path), http_client=client)
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert len(events) == 1
    assert events[0].id == "m365mail:msg-1"
    assert events[0].event_type == "email.received"
    assert events[0].data["subject"] == "Hello"
    assert "alice@example.com" in events[0].data["sender"]


def test_microsoft_mail_includes_filter_when_since(tmp_path):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"value": []})

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = MicrosoftMailConnector(auth_manager=_auth(tmp_path), http_client=client)
        since = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        await conn.pull(since=since)
        await client.aclose()

    asyncio.run(run())
    assert captured
    q = str(captured[0].url)
    assert "$filter" in q or "receivedDateTime" in q

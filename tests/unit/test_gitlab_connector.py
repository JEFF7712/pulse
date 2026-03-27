"""Unit tests for GitLab events connector."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from pulse.connectors.gitlab import GitLabConnector
from pulse.connectors.gitlab_auth import GitLabAuthManager


def test_gitlab_pull_maps_events_with_pat(tmp_path):
    sample = [
        {
            "id": 101,
            "action_name": "pushed to",
            "created_at": "2026-03-26T16:00:00.000Z",
            "project_id": 55,
            "target_title": "Fix login",
            "target_url": "https://gitlab.com/acme/app/-/merge_requests/1",
        }
    ]

    async def run():
        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="glpat-secret",
            http_client=client,
        )
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert len(events) == 1
    assert events[0].source == "gitlab"
    assert events[0].data["title"] == "Fix login"


def test_gitlab_oauth_uses_bearer(tmp_path):
    auth = GitLabAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gl.json",
        base_url="https://gitlab.com",
    )
    auth.save_tokens(
        {
            "access_token": "oauth-tok",
            "refresh_token": "r",
            "expires_at": __import__("time").time() + 3600,
        }
    )

    headers_captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        headers_captured.update(dict(request.headers))
        return httpx.Response(200, json=[])

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            auth_manager=auth,
            http_client=client,
        )
        await conn.pull(since=None)
        await client.aclose()

    asyncio.run(run())
    assert headers_captured.get("authorization", "").startswith("Bearer oauth-tok")


def test_gitlab_respects_since(tmp_path):
    sample = [
        {
            "id": 1,
            "action_name": "opened",
            "created_at": "2019-01-01T00:00:00.000Z",
            "project_id": 1,
            "target_title": "Old",
            "target_url": "https://gitlab.com/x",
        }
    ]

    async def run():
        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="t",
            http_client=client,
        )
        since = datetime(2026, 1, 1, tzinfo=UTC)
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    assert asyncio.run(run()) == []

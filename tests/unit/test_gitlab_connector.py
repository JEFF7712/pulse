"""Unit tests for GitLab events connector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from pulse.connectors.gitlab import GitLabConnector, _MAX_EVENTS
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
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=sample))
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
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=sample))
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


def test_gitlab_pull_paginates_until_reaching_since(tmp_path):
    requested_pages: list[int] = []
    request_sorts: list[str] = []
    since = datetime(2026, 3, 26, 10, 30, tzinfo=UTC)
    first_page = [
        {
            "id": i,
            "action_name": "pushed to",
            "created_at": f"2026-03-26T11:{i:02d}:00.000Z",
            "project_id": i,
            "target_title": f"Change {i}",
            "target_url": f"https://gitlab.com/acme/repo/-/commit/{i}",
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        {
            "id": 100,
            "action_name": "opened merge request",
            "created_at": "2026-03-26T10:45:00.000Z",
            "project_id": 100,
            "target_title": "MR 100",
            "target_url": "https://gitlab.com/acme/repo/-/merge_requests/100",
        },
        {
            "id": 101,
            "action_name": "commented on",
            "created_at": "2026-03-26T10:30:00.000Z",
            "project_id": 101,
            "target_title": "Old comment",
            "target_url": "https://gitlab.com/acme/repo/-/issues/101",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(int(request.url.params.get("page", "1")))
        request_sorts.append(str(request.url.params.get("sort", "")))
        page = requested_pages[-1]
        if page == 1:
            return httpx.Response(200, json=first_page)
        if page == 2:
            return httpx.Response(200, json=second_page)
        raise AssertionError(f"unexpected page request: {page}")

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="t",
            http_client=client,
        )
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert request_sorts == ["desc", "desc"]
    assert len(events) == _MAX_EVENTS + 1
    assert events[-1].id == "gitlab:100"
    assert all(event.timestamp > since for event in events)


def test_gitlab_pull_deduplicates_overlapping_pages(tmp_path):
    requested_pages: list[int] = []
    first_page = [
        {
            "id": i,
            "action_name": "pushed to",
            "created_at": f"2026-03-26T11:{i:02d}:00.000Z",
            "project_id": i,
            "target_title": f"Change {i}",
            "target_url": f"https://gitlab.com/acme/repo/-/commit/{i}",
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        first_page[-1],
        {
            "id": 100,
            "action_name": "opened merge request",
            "created_at": "2026-03-26T09:45:00.000Z",
            "project_id": 100,
            "target_title": "MR 100",
            "target_url": "https://gitlab.com/acme/repo/-/merge_requests/100",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(int(request.url.params.get("page", "1")))
        if requested_pages[-1] == 1:
            return httpx.Response(200, json=first_page)
        if requested_pages[-1] == 2:
            return httpx.Response(200, json=second_page)
        raise AssertionError(f"unexpected page request: {requested_pages[-1]}")

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="t",
            http_client=client,
        )
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert len(events) == _MAX_EVENTS + 1
    assert [event.id for event in events].count(f"gitlab:{_MAX_EVENTS - 1}") == 1


def test_gitlab_pull_handles_page_shift_from_newer_events(tmp_path):
    requested_pages: list[int] = []
    since = datetime(2026, 3, 26, 10, 30, tzinfo=UTC)
    first_page = [
        {
            "id": i,
            "action_name": "pushed to",
            "created_at": f"2026-03-26T11:{i:02d}:00.000Z",
            "project_id": i,
            "target_title": f"Change {i}",
            "target_url": f"https://gitlab.com/acme/repo/-/commit/{i}",
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        first_page[-2],
        first_page[-1],
        {
            "id": 100,
            "action_name": "opened merge request",
            "created_at": "2026-03-26T10:45:00.000Z",
            "project_id": 100,
            "target_title": "MR 100",
            "target_url": "https://gitlab.com/acme/repo/-/merge_requests/100",
        },
        {
            "id": 101,
            "action_name": "commented on",
            "created_at": "2026-03-26T10:30:00.000Z",
            "project_id": 101,
            "target_title": "Old comment",
            "target_url": "https://gitlab.com/acme/repo/-/issues/101",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(int(request.url.params.get("page", "1")))
        if requested_pages[-1] == 1:
            return httpx.Response(200, json=first_page)
        if requested_pages[-1] == 2:
            return httpx.Response(200, json=second_page)
        raise AssertionError(f"unexpected page request: {requested_pages[-1]}")

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="t",
            http_client=client,
        )
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert len(events) == _MAX_EVENTS + 1
    assert {event.id for event in events} == {
        *(f"gitlab:{i}" for i in range(_MAX_EVENTS)),
        "gitlab:100",
    }

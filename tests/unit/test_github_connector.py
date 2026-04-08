from datetime import UTC, datetime
import httpx

from pulse.connectors.github import GitHubConnector, _MAX_EVENTS
from pulse.connectors.github_auth import GitHubAuthManager


def test_github_maps_push_event(tmp_path):
    auth = GitHubAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gh.json",
    )
    auth.save_tokens({"access_token": "tok", "expires_at": None})

    sample = [
        {
            "id": "1",
            "type": "PushEvent",
            "created_at": "2026-03-26T15:00:00Z",
            "repo": {"name": "acme/app"},
            "payload": {"ref": "refs/heads/main", "commits": [{"id": "a"}]},
        }
    ]

    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=sample))
        client = httpx.AsyncClient(transport=transport)
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    import asyncio

    events = asyncio.run(run())
    assert len(events) == 1
    assert events[0].event_type == "dev.push"
    assert events[0].data["repo"] == "acme/app"


def test_github_respects_since_filter(tmp_path):
    auth = GitHubAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gh.json",
    )
    auth.save_tokens({"access_token": "tok", "expires_at": None})

    sample = [
        {
            "id": "1",
            "type": "WatchEvent",
            "created_at": "2020-01-01T00:00:00Z",
            "repo": {"name": "acme/old"},
            "payload": {},
        }
    ]

    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=sample))
        client = httpx.AsyncClient(transport=transport)
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        since = datetime(2026, 1, 1, tzinfo=UTC)
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    import asyncio

    assert asyncio.run(run()) == []


def test_github_pull_paginates_until_reaching_since(tmp_path):
    auth = GitHubAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gh.json",
    )
    auth.save_tokens({"access_token": "tok", "expires_at": None})

    since = datetime(2026, 3, 26, 10, 30, tzinfo=UTC)
    requested_pages: list[int] = []
    first_page = [
        {
            "id": str(i),
            "type": "WatchEvent",
            "created_at": f"2026-03-26T11:{i:02d}:00Z",
            "repo": {"name": f"acme/repo-{i}"},
            "payload": {},
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        {
            "id": "100",
            "type": "PullRequestEvent",
            "created_at": "2026-03-26T10:45:00Z",
            "repo": {"name": "acme/repo-100"},
            "payload": {
                "pull_request": {
                    "title": "Feature work",
                    "html_url": "https://github.com/acme/repo-100/pull/1",
                }
            },
        },
        {
            "id": "101",
            "type": "WatchEvent",
            "created_at": "2026-03-26T10:30:00Z",
            "repo": {"name": "acme/repo-101"},
            "payload": {},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(int(request.url.params.get("page", "1")))
        page = requested_pages[-1]
        if page == 1:
            return httpx.Response(200, json=first_page)
        if page == 2:
            return httpx.Response(200, json=second_page)
        raise AssertionError(f"unexpected page request: {page}")

    async def run():
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    import asyncio

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert len(events) == _MAX_EVENTS + 1
    assert events[-1].id == "github:100"
    assert all(event.timestamp > since for event in events)


def test_github_pull_deduplicates_overlapping_pages(tmp_path):
    auth = GitHubAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gh.json",
    )
    auth.save_tokens({"access_token": "tok", "expires_at": None})

    requested_pages: list[int] = []
    first_page = [
        {
            "id": str(i),
            "type": "WatchEvent",
            "created_at": f"2026-03-26T11:{i:02d}:00Z",
            "repo": {"name": f"acme/repo-{i}"},
            "payload": {},
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        first_page[-1],
        {
            "id": "100",
            "type": "PullRequestEvent",
            "created_at": "2026-03-26T09:45:00Z",
            "repo": {"name": "acme/repo-100"},
            "payload": {
                "pull_request": {
                    "title": "Feature work",
                    "html_url": "https://github.com/acme/repo-100/pull/1",
                }
            },
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
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        events = await conn.pull(since=None)
        await client.aclose()
        return events

    import asyncio

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert len(events) == _MAX_EVENTS + 1
    assert [event.id for event in events].count(f"github:{_MAX_EVENTS - 1}") == 1


def test_github_pull_handles_page_shift_from_newer_events(tmp_path):
    auth = GitHubAuthManager(
        client_id="c",
        client_secret="s",
        token_path=tmp_path / "gh.json",
    )
    auth.save_tokens({"access_token": "tok", "expires_at": None})

    since = datetime(2026, 3, 26, 10, 30, tzinfo=UTC)
    requested_pages: list[int] = []
    first_page = [
        {
            "id": str(i),
            "type": "WatchEvent",
            "created_at": f"2026-03-26T11:{i:02d}:00Z",
            "repo": {"name": f"acme/repo-{i}"},
            "payload": {},
        }
        for i in range(_MAX_EVENTS)
    ]
    second_page = [
        first_page[-2],
        first_page[-1],
        {
            "id": "100",
            "type": "PullRequestEvent",
            "created_at": "2026-03-26T10:45:00Z",
            "repo": {"name": "acme/repo-100"},
            "payload": {
                "pull_request": {
                    "title": "Feature work",
                    "html_url": "https://github.com/acme/repo-100/pull/1",
                }
            },
        },
        {
            "id": "101",
            "type": "WatchEvent",
            "created_at": "2026-03-26T10:30:00Z",
            "repo": {"name": "acme/repo-101"},
            "payload": {},
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
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    import asyncio

    events = asyncio.run(run())
    assert requested_pages == [1, 2]
    assert len(events) == _MAX_EVENTS + 1
    assert {event.id for event in events} == {
        *(f"github:{i}" for i in range(_MAX_EVENTS)),
        "github:100",
    }

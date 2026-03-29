from datetime import UTC, datetime, timedelta

import httpx

from pulse.connectors.linear import LINEAR_GQL, LinearConnector


def _issue_node(
    iid: str,
    *,
    identifier: str = "ENG-1",
    title: str = "Fix thing",
    hours_ago: float = 2,
) -> dict:
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "id": iid,
        "identifier": identifier,
        "title": title,
        "url": "https://linear.app/acme/issue/ENG-1",
        "updatedAt": ts,
        "state": {"name": "In Progress"},
        "team": {"key": "ENG", "name": "Engineering"},
    }


def test_linear_pull_emits_dev_event() -> None:
    body = {
        "data": {
            "issues": {
                "nodes": [_issue_node("issue-uuid-1")],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(LINEAR_GQL)
        assert request.headers.get("Authorization") == "lin_api_test"
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def run():
        c = LinearConnector(api_key="lin_api_test", http_client=client)
        events = await c.pull(since=None)
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "dev.linear.issue"
        assert e.source == "linear"
        assert e.id == "linear:issue-uuid-1"
        assert e.data["identifier"] == "ENG-1"
        assert e.data["issue_title"] == "Fix thing"
        assert e.data["title"].startswith("ENG-1:")
        assert e.data["provider"] == "linear"
        assert e.data["repo"] == "ENG/ENG-1"

    import asyncio

    asyncio.run(run())


def test_linear_since_skips_not_newer() -> None:
    since = datetime.now(UTC) - timedelta(hours=5)
    # updated 10h ago -> older than cursor -> ts <= since -> skip
    old_ts = (datetime.now(UTC) - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    node = {
        "id": "x",
        "identifier": "A-1",
        "title": "T",
        "url": "https://linear.app/x",
        "updatedAt": old_ts,
        "state": {"name": "Todo"},
        "team": {"key": "A", "name": "A"},
    }
    body = {"data": {"issues": {"nodes": [node], "pageInfo": {"hasNextPage": False}}}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        c = LinearConnector(api_key="k", http_client=client)
        events = await c.pull(since=since)
        assert events == []

    import asyncio

    asyncio.run(run())


def test_linear_stop_paging_when_older_than_lookback() -> None:
    recent = _issue_node("new", hours_ago=1)
    old_ts = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    stale = {
        "id": "old",
        "identifier": "ENG-99",
        "title": "Stale",
        "url": "https://linear.app/x",
        "updatedAt": old_ts,
        "state": {"name": "Done"},
        "team": {"key": "ENG", "name": "E"},
    }
    body = {"data": {"issues": {"nodes": [recent, stale], "pageInfo": {"hasNextPage": False}}}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run():
        c = LinearConnector(api_key="k", http_client=client)
        events = await c.pull(since=None)
        assert len(events) == 1
        assert events[0].id == "linear:new"

    import asyncio

    asyncio.run(run())


def test_linear_validate_and_empty_key() -> None:
    import asyncio

    async def run():
        assert await LinearConnector(api_key=None).validate_config() is False
        assert await LinearConnector(api_key="  ").validate_config() is False
        assert await LinearConnector(api_key="abc").validate_config() is True
        assert await LinearConnector(api_key=None).pull() == []

    asyncio.run(run())

from datetime import UTC, datetime, timedelta

import httpx

from pulse.connectors.notion import NotionConnector


def test_notion_search_emits_page_edited() -> None:
    edited = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    search_body = {
        "results": [
            {
                "object": "page",
                "id": "251c6113-521c-4fdb-bb86-7b64fb6e9b91",
                "last_edited_time": edited,
                "archived": False,
                "url": "https://www.notion.so/Test-251c6113521c4fdbbb867b64fb6e9b91",
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [{"plain_text": "Quarterly plan", "text": {"content": "Quarterly plan"}}],
                    }
                },
            }
        ],
        "has_more": False,
        "next_cursor": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("notion-version")
        assert request.headers.get("authorization") == "Bearer secret_test"
        if request.method == "POST" and request.url.path.endswith("/search"):
            return httpx.Response(200, json=search_body)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def run():
        c = NotionConnector(token="secret_test", http_client=client)
        events = await c.pull(since=None)
        assert len(events) == 1
        e = events[0]
        assert e.event_type == "notion.page_edited"
        assert e.data["title"] == "Quarterly plan"
        assert e.data["via"] == "search"
        assert (datetime.now(UTC) - e.timestamp).total_seconds() < 86400

    import asyncio

    asyncio.run(run())


def test_notion_database_query_when_configured() -> None:
    db_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    edited = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    row = {
        "object": "page",
        "id": "351c6113-521c-4fdb-bb86-7b64fb6e9b92",
        "last_edited_time": edited,
        "archived": False,
        "properties": {
            "Task": {
                "type": "title",
                "title": [{"plain_text": "Fix bug", "text": {"content": "Fix bug"}}],
            }
        },
    }
    query_body = {"results": [row], "has_more": False, "next_cursor": None}
    search_body = {"results": [], "has_more": False, "next_cursor": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=search_body)
        if f"/databases/{db_id}/query" in str(request.url):
            return httpx.Response(200, json=query_body)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def run():
        c = NotionConnector(
            token="secret_test",
            database_ids=[db_id],
            http_client=client,
        )
        events = await c.pull(since=None)
        assert len(events) == 1
        assert events[0].data["title"] == "Fix bug"
        assert events[0].data["via"] == "database"

    import asyncio

    asyncio.run(run())


def test_notion_validate_without_token() -> None:
    import asyncio

    async def run():
        c = NotionConnector(token=None)
        assert await c.validate_config() is False

    asyncio.run(run())

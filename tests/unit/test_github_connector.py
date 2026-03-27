from datetime import UTC, datetime
import httpx

from pulse.connectors.github import GitHubConnector
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
        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
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
        client_id="c", client_secret="s", token_path=tmp_path / "gh.json",
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
        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
        client = httpx.AsyncClient(transport=transport)
        conn = GitHubConnector(auth_manager=auth, http_client=client)
        since = datetime(2026, 1, 1, tzinfo=UTC)
        events = await conn.pull(since=since)
        await client.aclose()
        return events

    import asyncio

    assert asyncio.run(run()) == []

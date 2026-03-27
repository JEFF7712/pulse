"""Integration-style pull + DB persistence for GitHub connector."""
from __future__ import annotations

import asyncio

import httpx

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.github import GitHubConnector
from pulse.connectors.github_auth import GitHubAuthManager
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def test_github_pull_cycle_stores_dev_events(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"
        auth = GitHubAuthManager("id", "sec", tmp_path / "gh.json")
        auth.save_tokens({"access_token": "tok", "expires_at": None})

        sample = [
            {
                "id": "999",
                "type": "IssuesEvent",
                "created_at": "2026-03-26T11:00:00Z",
                "repo": {"name": "acme/app"},
                "payload": {
                    "action": "opened",
                    "issue": {
                        "title": "Bug",
                        "html_url": "https://github.com/acme/app/issues/1",
                    },
                },
            }
        ]

        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
        client = httpx.AsyncClient(transport=transport)
        connector = GitHubConnector(auth_manager=auth, http_client=client)

        registry = ConnectorRegistry()
        registry.register_pull("github", lambda: connector)
        config = PulseConfig(
            database_path=str(db_path),
            github_client_id="id",
            github_client_secret="sec",
            connectors={"github": ConnectorConfig(enabled=True, poll_interval="30m")},
        )
        await registry.build_active_connectors(config)

        events = await connector.pull(since=None)
        await client.aclose()

        assert len(events) == 1
        assert events[0].event_type == "dev.issue"

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(events)
            sync = SyncStateRepository(db)
            await sync.save("github", events[0].timestamp.isoformat())

            stored = await repo.list_events_for_day("2026-03-26")
            assert len(stored) == 1
            assert stored[0].source == "github"

    asyncio.run(exercise())

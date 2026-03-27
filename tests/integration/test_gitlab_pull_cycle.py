"""Integration-style pull + DB persistence for GitLab connector (PAT)."""
from __future__ import annotations

import asyncio

import httpx

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.gitlab import GitLabConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def test_gitlab_pull_cycle_stores_events(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"
        sample = [
            {
                "id": 42,
                "action_name": "opened merge request",
                "created_at": "2026-03-26T18:00:00.000Z",
                "project_id": 7,
                "target_title": "Add feature",
                "target_url": "https://gitlab.com/acme/app/-/merge_requests/2",
            }
        ]

        transport = httpx.MockTransport(
            lambda r: httpx.Response(200, json=sample)
        )
        client = httpx.AsyncClient(transport=transport)
        connector = GitLabConnector(
            base_url="https://gitlab.com",
            personal_token="glpat-test",
            http_client=client,
        )

        registry = ConnectorRegistry()
        registry.register_pull("gitlab", lambda: connector)
        config = PulseConfig(
            database_path=str(db_path),
            gitlab_token="glpat-test",
            connectors={"gitlab": ConnectorConfig(enabled=True, poll_interval="30m")},
        )
        await registry.build_active_connectors(config)

        events = await connector.pull(since=None)
        await client.aclose()

        assert len(events) == 1

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(events)
            sync = SyncStateRepository(db)
            await sync.save("gitlab", events[0].timestamp.isoformat())

            stored = await repo.list_events_for_day("2026-03-26")
            assert len(stored) == 1
            assert "gitlab:42" == stored[0].id

    asyncio.run(exercise())

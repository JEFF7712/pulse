"""Integration-style pull + DB persistence for Microsoft mail connector."""
from __future__ import annotations

import asyncio

import httpx

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.microsoft_auth import MicrosoftAuthManager
from pulse.connectors.microsoft_mail import MicrosoftMailConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def test_microsoft_mail_pull_cycle_stores_events(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"
        tok = tmp_path / "ms.json"
        auth = MicrosoftAuthManager("id", "sec", tok, tenant_id="common")
        auth.save_tokens(
            {
                "access_token": "t",
                "refresh_token": "r",
                "expires_at": __import__("time").time() + 3600,
            }
        )

        payload = {
            "value": [
                {
                    "id": "m1",
                    "subject": "Ping",
                    "receivedDateTime": "2026-03-26T12:00:00Z",
                    "from": {
                        "emailAddress": {"name": "Bot", "address": "bot@x.com"},
                    },
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        connector = MicrosoftMailConnector(auth_manager=auth, http_client=client)

        registry = ConnectorRegistry()
        registry.register_pull("microsoft_mail", lambda: connector)
        config = PulseConfig(
            database_path=str(db_path),
            microsoft_client_id="id",
            microsoft_client_secret="sec",
            connectors={
                "microsoft_mail": ConnectorConfig(enabled=True, poll_interval="15m"),
            },
        )
        await registry.build_active_connectors(config)
        pull = registry.get_pull_connectors()
        assert len(pull) == 1

        events = await connector.pull()
        await client.aclose()

        assert len(events) == 1
        assert events[0].event_type == "email.received"

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(events)
            sync = SyncStateRepository(db)
            await sync.save("microsoft_mail", events[0].timestamp.isoformat())

            stored = await repo.list_events_for_day("2026-03-26")
            assert len(stored) == 1
            assert stored[0].id == "m365mail:m1"

    asyncio.run(exercise())

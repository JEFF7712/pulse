"""Integration-style Plaid pull + DB persistence (Plaid SDK mocked)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.plaid_connector import PlaidConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def test_plaid_pull_cycle_stores_finance_events(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"
        token_path = tmp_path / "plaid_tokens.json"
        token_path.write_text(json.dumps({"access_token": "access-sandbox-xyz"}))

        class SyncResp:
            def to_dict(self):
                return {
                    "added": [
                        {
                            "transaction_id": "t-db",
                            "date": "2026-03-27",
                            "amount": 4.0,
                            "name": "Snack",
                            "pending": False,
                            "account_id": "a1",
                        }
                    ],
                    "next_cursor": "c-final",
                    "has_more": False,
                }

        class FakeApi:
            def transactions_sync(self, req):
                return SyncResp()

        class FakeClient:
            def close(self):
                pass

        config = PulseConfig(
            database_path=str(db_path),
            plaid_client_id="cid",
            plaid_secret="sec",
            plaid_env="sandbox",
            connectors={"plaid": ConnectorConfig(enabled=True, poll_interval="6h")},
        )
        connector = PlaidConnector(config, token_path, omit_amounts_in_summary=False)

        registry = ConnectorRegistry()
        registry.register_pull("plaid", lambda: connector)
        await registry.build_active_connectors(config)

        with patch(
            "pulse.connectors.plaid_connector.make_plaid_client",
            return_value=(FakeApi(), FakeClient()),
        ):
            events = await connector.pull(since=None)

        assert len(events) == 1
        assert events[0].event_type == "finance.transaction"

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(events)
            sync = SyncStateRepository(db)
            await sync.save("plaid", events[0].timestamp.isoformat())

            stored = await repo.list_events_for_day("2026-03-27")
            assert len(stored) == 1
            assert stored[0].id == "plaid:t-db"

        blob = json.loads(token_path.read_text())
        assert blob["transactions_cursor"] == "c-final"

    asyncio.run(exercise())

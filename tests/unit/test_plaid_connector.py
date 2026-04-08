"""Unit tests for Plaid transaction connector (SDK mocked)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from pulse.app.config import PulseConfig
from pulse.connectors.plaid_connector import PlaidConnector


def test_plaid_pull_empty_without_access_token(tmp_path):
    token_path = tmp_path / "plaid_tokens.json"
    token_path.write_text(json.dumps({}))
    config = PulseConfig(plaid_client_id="id", plaid_secret="sec", plaid_env="sandbox")
    conn = PlaidConnector(config, token_path)
    events = asyncio.run(conn.pull())
    assert events == []


def test_plaid_pull_maps_transactions_and_persists_cursor(tmp_path):
    token_path = tmp_path / "plaid_tokens.json"
    token_path.write_text(json.dumps({"access_token": "access-sandbox-abc"}))
    config = PulseConfig(plaid_client_id="cid", plaid_secret="secret", plaid_env="sandbox")

    class SyncResp:
        def to_dict(self):
            return {
                "added": [
                    {
                        "transaction_id": "txn-1",
                        "date": "2026-03-26",
                        "amount": 9.99,
                        "merchant_name": "Cafe",
                        "name": "Cafe",
                        "pending": False,
                        "account_id": "acc-1",
                        "category": ["Food and Drink", "Restaurants"],
                    }
                ],
                "next_cursor": "cursor-next",
                "has_more": False,
            }

    class FakeApi:
        def transactions_sync(self, req):
            return SyncResp()

    class FakeApiClient:
        closed = False

        def close(self):
            self.closed = True

    fake_client = FakeApiClient()

    conn = PlaidConnector(config, token_path, omit_amounts_in_summary=True)

    with patch(
        "pulse.connectors.plaid_connector.make_plaid_client",
        return_value=(FakeApi(), fake_client),
    ):
        events = asyncio.run(conn.pull(since=None))

    assert len(events) == 1
    e = events[0]
    assert e.event_type == "finance.transaction"
    assert e.id == "plaid:txn-1"
    assert e.data["amount"] == 9.99
    assert e.data["omit_amount_in_summary"] is True
    assert "Food" in e.data["category"]

    blob = json.loads(token_path.read_text())
    assert blob["transactions_cursor"] == "cursor-next"
    assert fake_client.closed is True


def test_plaid_validate_config_requires_token_file_access(tmp_path):
    config = PulseConfig(plaid_client_id="c", plaid_secret="s")
    conn = PlaidConnector(config, tmp_path / "missing.json")
    assert asyncio.run(conn.validate_config()) is False

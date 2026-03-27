"""Plaid transactions → finance.transaction events."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pulse.app.config import PulseConfig
from pulse.connectors.plaid_client import make_plaid_client
from pulse.domain.connectors import Connector
from pulse.domain.events import Event
from plaid.model.transactions_sync_request import TransactionsSyncRequest


def _load_token_blob(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_token_blob(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _tx_timestamp_from_dict(row: dict[str, Any]) -> datetime:
    dt = row.get("datetime") or row.get("authorized_datetime")
    if dt:
        s = str(dt)
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    d = row.get("date") or row.get("authorized_date")
    if d:
        return datetime.fromisoformat(str(d)).replace(tzinfo=UTC) + timedelta(hours=12)
    return datetime.now(UTC)


class PlaidConnector(Connector):
    def __init__(
        self,
        config: PulseConfig,
        token_path: Path,
        omit_amounts_in_digest: bool = False,
    ) -> None:
        self._config = config
        self._token_path = token_path
        self._omit_amounts = omit_amounts_in_digest

    def get_source_name(self) -> str:
        return "plaid"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=6)

    async def validate_config(self) -> bool:
        if not self._config.plaid_client_id or not self._config.plaid_secret:
            return False
        blob = _load_token_blob(self._token_path)
        return bool(blob.get("access_token"))

    async def pull(self, since: datetime | None = None) -> list[Event]:
        blob = _load_token_blob(self._token_path)
        access_token = blob.get("access_token")
        if not access_token:
            return []

        cursor = blob.get("transactions_cursor")

        def _sync_once() -> tuple[list[dict[str, Any]], str | None]:
            plaid_api, api_client = make_plaid_client(self._config)
            try:
                added_all: list[dict[str, Any]] = []
                next_cursor: str | None = cursor
                while True:
                    req_kwargs: dict[str, Any] = {"access_token": access_token}
                    if next_cursor:
                        req_kwargs["cursor"] = next_cursor
                    req = TransactionsSyncRequest(**req_kwargs)
                    raw = plaid_api.transactions_sync(req)
                    resp = raw.to_dict()
                    added = list(resp.get("added") or [])
                    added_all.extend(added)
                    next_cursor = resp.get("next_cursor")
                    has_more = bool(resp.get("has_more"))
                    if not has_more:
                        break
                return added_all, next_cursor
            finally:
                api_client.close()

        added_all, next_cursor = await asyncio.to_thread(_sync_once)

        if next_cursor is not None:
            blob["transactions_cursor"] = next_cursor
            _save_token_blob(self._token_path, blob)

        events: list[Event] = []
        for row in added_all:
            tid = row.get("transaction_id") or str(hash(str(row)))
            ts = _tx_timestamp_from_dict(row)
            if since is not None and ts <= since.astimezone(UTC):
                continue
            amount = float(row.get("amount") or 0)
            name = str(row.get("merchant_name") or row.get("name") or "Transaction")
            cat = row.get("category")
            cat_s = ", ".join(str(c) for c in cat) if isinstance(cat, list) else ""
            events.append(
                Event(
                    id=f"plaid:{tid}",
                    timestamp=ts,
                    source="plaid",
                    event_type="finance.transaction",
                    data={
                        "name": name,
                        "merchant_name": name,
                        "amount": amount,
                        "category": cat_s,
                        "pending": bool(row.get("pending")),
                        "account_id": str(row.get("account_id") or ""),
                        "omit_amount_in_digest": self._omit_amounts,
                    },
                )
            )
        return events

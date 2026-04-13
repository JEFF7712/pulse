"""Notion workspace search (and optional database queries) → Pulse notion.* events."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulse.domain.connectors import Connector, ConnectorAuthError
from pulse.domain.events import Event

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
# Stable version; avoids newer trash/archive response shape differences.
NOTION_VERSION = "2022-06-28"
_MAX_SEARCH_PAGES = 40
_MAX_DB_QUERY_PAGES = 20
_DEFAULT_LOOKBACK = timedelta(days=14)


def _uuid_compact(page_id: str) -> str:
    return page_id.replace("-", "")


def _rich_text_plain(items: object) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("plain_text"):
            parts.append(str(item["plain_text"]))
            continue
        text = item.get("text")
        if isinstance(text, dict) and text.get("content"):
            parts.append(str(text["content"]))
    return "".join(parts).strip()


def _page_title_from_properties(properties: object) -> str:
    if not isinstance(properties, dict):
        return ""
    for pv in properties.values():
        if not isinstance(pv, dict):
            continue
        t = pv.get("type")
        if t == "title":
            return _rich_text_plain(pv.get("title")) or ""
    return ""


def _item_title(obj: dict[str, Any]) -> str:
    kind = obj.get("object")
    if kind == "database":
        return _rich_text_plain(obj.get("title")) or "Untitled database"
    if kind == "page":
        return _page_title_from_properties(obj.get("properties")) or "Untitled"
    return str(kind or "Notion item")


def _item_url(obj: dict[str, Any]) -> str:
    u = obj.get("url")
    if isinstance(u, str) and u.strip():
        return u.strip()
    pid = obj.get("id")
    if isinstance(pid, str) and pid:
        compact = _uuid_compact(pid)
        return f"https://www.notion.so/{compact}"
    return ""


def _parse_notion_datetime(raw: object) -> datetime | None:
    if not raw:
        return None
    s = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:
        return None


def _is_trashed(obj: dict[str, Any]) -> bool:
    return bool(obj.get("archived") or obj.get("in_trash"))


class NotionConnector(Connector):
    def __init__(
        self,
        token: str | None,
        database_ids: list[str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = (token or "").strip() or None
        self._database_ids = [d.strip() for d in (database_ids or []) if d.strip()]
        self._http = http_client

    def get_source_name(self) -> str:
        return "notion"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=45)

    async def validate_config(self) -> bool:
        return self._token is not None

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            raise RuntimeError("Configure Notion token")
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def pull(self, since: datetime | None = None) -> list[Event]:
        if not self._token:
            return []

        sync_cursor = since.astimezone(UTC) if since is not None else None
        lookback = datetime.now(UTC) - _DEFAULT_LOOKBACK

        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        events: list[Event] = []
        seen_ids: set[str] = set()

        try:
            await self._search_workspace(
                client, sync_cursor, lookback, events, seen_ids
            )
            for db_id in self._database_ids:
                await self._query_database(
                    client, db_id, sync_cursor, lookback, events, seen_ids
                )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning("Notion API unauthorized — check PULSE_NOTION_TOKEN")
                raise ConnectorAuthError(
                    "Notion API unauthorized — check PULSE_NOTION_TOKEN"
                ) from e
            logger.warning("Notion API error: %s", e)
            return []
        except Exception:
            logger.exception("Notion pull failed")
            return []
        finally:
            if owns:
                await client.aclose()

        return events

    async def _search_workspace(
        self,
        client: httpx.AsyncClient,
        sync_cursor: datetime | None,
        lookback: datetime,
        events: list[Event],
        seen_ids: set[str],
    ) -> None:
        next_cursor: str | None = None
        for _ in range(_MAX_SEARCH_PAGES):
            body: dict[str, Any] = {
                "page_size": 100,
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }
            if next_cursor:
                body["start_cursor"] = next_cursor

            resp = await client.post(
                f"{NOTION_API}/search",
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results") or []:
                if not isinstance(item, dict):
                    continue
                if _is_trashed(item):
                    continue
                edited = _parse_notion_datetime(item.get("last_edited_time"))
                if edited is None:
                    continue
                if sync_cursor is not None:
                    if edited <= sync_cursor:
                        return
                elif edited < lookback:
                    return
                ev = self._event_from_notion_object(item, via="search", edited=edited)
                if ev is None:
                    continue
                if ev.id in seen_ids:
                    continue
                seen_ids.add(ev.id)
                events.append(ev)

            if not data.get("has_more"):
                break
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break

    async def _query_database(
        self,
        client: httpx.AsyncClient,
        database_id: str,
        sync_cursor: datetime | None,
        lookback: datetime,
        events: list[Event],
        seen_ids: set[str],
    ) -> None:
        # Normalize UUID: allow with or without dashes
        db_clean = _normalize_uuid(database_id)
        if not db_clean:
            return
        next_cursor: str | None = None
        for _ in range(_MAX_DB_QUERY_PAGES):
            body: dict[str, Any] = {
                "page_size": 100,
                "sorts": [
                    {"timestamp": "last_edited_time", "direction": "descending"},
                ],
            }
            if next_cursor:
                body["start_cursor"] = next_cursor

            resp = await client.post(
                f"{NOTION_API}/databases/{db_clean}/query",
                json=body,
                headers=self._headers(),
            )
            if resp.status_code == 404:
                logger.warning(
                    "Notion database not found or not shared: %s", database_id
                )
                return
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results") or []:
                if not isinstance(item, dict):
                    continue
                if _is_trashed(item):
                    continue
                edited = _parse_notion_datetime(item.get("last_edited_time"))
                if edited is None:
                    continue
                if sync_cursor is not None:
                    if edited <= sync_cursor:
                        return
                elif edited < lookback:
                    return
                ev = self._event_from_notion_object(
                    item,
                    via="database",
                    database_id=db_clean,
                    edited=edited,
                )
                if ev is None:
                    continue
                if ev.id in seen_ids:
                    continue
                seen_ids.add(ev.id)
                events.append(ev)

            if not data.get("has_more"):
                break
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break

    def _event_from_notion_object(
        self,
        obj: dict[str, Any],
        *,
        via: str,
        database_id: str | None = None,
        edited: datetime,
    ) -> Event | None:
        pid = obj.get("id")
        if not isinstance(pid, str) or not pid:
            return None

        title = _item_title(obj)
        url = _item_url(obj)
        kind = str(obj.get("object") or "page")
        parent = obj.get("parent") if isinstance(obj.get("parent"), dict) else {}
        parent_type = str(parent.get("type") or "")

        meta_db = database_id if via == "database" else None
        if meta_db is None and parent_type == "database_id":
            meta_db = str(parent.get("database_id") or "")

        return Event(
            id=f"notion:{_uuid_compact(pid)}",
            timestamp=edited,
            source="notion",
            event_type="notion.page_edited",
            data={
                "title": title,
                "url": url,
                "object_type": kind,
                "via": via,
                "parent_type": parent_type,
                "database_id": meta_db or "",
            },
            metadata={},
        )


def _normalize_uuid(raw: str) -> str:
    s = raw.strip()
    if re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        s,
    ):
        return s
    if re.fullmatch(r"[0-9a-fA-F]{32}", s):
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"
    return s

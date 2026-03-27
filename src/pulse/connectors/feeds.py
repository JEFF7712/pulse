"""RSS and Atom feed pull connector (no API keys; URLs in pulse.toml)."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from time import mktime
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

logger = logging.getLogger(__name__)

USER_AGENT = "Pulse/0.1 (RSS/Atom feed connector)"


def _entry_timestamp(entry: Any) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    return datetime.fromtimestamp(mktime(t), tz=UTC)


def events_from_feedparser_dict(
    parsed: Any,
    feed_url: str,
    since: datetime | None,
) -> list[Event]:
    """Turn a feedparser result into Pulse events (testable without HTTP)."""
    events: list[Event] = []
    feed_title = ""
    if getattr(parsed, "feed", None):
        feed_title = (parsed.feed.get("title") or "").strip()
    if not feed_title:
        feed_title = urlparse(feed_url).netloc or feed_url

    for entry in getattr(parsed, "entries", []) or []:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        ts = _entry_timestamp(entry)
        if ts is None:
            continue
        if since is not None and ts <= since:
            continue
        rid = entry.get("id") or link or title
        digest = hashlib.sha256(f"{feed_url}\0{rid}".encode()).hexdigest()[:16]
        events.append(
            Event(
                id=f"feeds:{digest}",
                timestamp=ts,
                source="feeds",
                event_type="feed.item",
                data={
                    "title": title,
                    "link": link,
                    "feed_url": feed_url,
                    "feed_title": feed_title,
                },
            )
        )
    return events


class FeedConnector(Connector):
    def __init__(self, urls: list[str] | None = None) -> None:
        self._urls = [u.strip() for u in (urls or []) if u and str(u).strip()]

    def get_source_name(self) -> str:
        return "feeds"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=1)

    async def validate_config(self) -> bool:
        return len(self._urls) > 0

    async def pull(self, since: datetime | None = None) -> list[Event]:
        out: list[Event] = []
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        ) as client:
            for feed_url in self._urls:
                try:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                    parsed = feedparser.parse(resp.content)
                    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
                        logger.warning(
                            "Feed parse issue for %s: %s",
                            feed_url,
                            getattr(parsed, "bozo_exception", "unknown"),
                        )
                    out.extend(events_from_feedparser_dict(parsed, feed_url, since))
                except Exception as e:
                    logger.warning("Feed fetch failed for %s: %s", feed_url, e)
        out.sort(key=lambda e: e.timestamp)
        return out

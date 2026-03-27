import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import feedparser

from pulse.connectors.feeds import FeedConnector, events_from_feedparser_dict


_RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Hello World</title>
      <link>https://example.com/hello</link>
      <pubDate>Mon, 15 Jan 2024 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_events_from_feedparser_dict_respects_since() -> None:
    parsed = feedparser.parse(_RSS_SAMPLE)
    since = datetime(2024, 1, 16, tzinfo=UTC)
    assert events_from_feedparser_dict(parsed, "https://example.com/feed.xml", since) == []

    since_early = datetime(2024, 1, 14, tzinfo=UTC)
    events = events_from_feedparser_dict(parsed, "https://example.com/feed.xml", since_early)
    assert len(events) == 1
    assert events[0].source == "feeds"
    assert events[0].event_type == "feed.item"
    assert events[0].data["title"] == "Hello World"
    assert events[0].data["link"] == "https://example.com/hello"
    assert events[0].data["feed_title"] == "Test Feed"


def test_feed_connector_validate_requires_urls() -> None:
    assert asyncio.run(FeedConnector(urls=[]).validate_config()) is False
    assert asyncio.run(FeedConnector(urls=["http://x"]).validate_config()) is True


def test_feed_connector_pull_uses_httpx() -> None:
    mock_resp = MagicMock()
    mock_resp.content = _RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    async def _run() -> None:
        with patch("pulse.connectors.feeds.httpx.AsyncClient", return_value=mock_client):
            c = FeedConnector(urls=["https://example.com/feed.xml"])
            events = await c.pull()
        assert len(events) == 1
        mock_client.get.assert_awaited_once_with("https://example.com/feed.xml")

    asyncio.run(_run())

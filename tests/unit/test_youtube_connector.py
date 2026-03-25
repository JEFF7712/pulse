import asyncio
from datetime import UTC, datetime, timedelta


def test_youtube_connector_source_name():
    from pulse.connectors.youtube import YouTubeConnector
    connector = YouTubeConnector()
    assert connector.get_source_name() == "youtube"


def test_youtube_connector_default_interval():
    from pulse.connectors.youtube import YouTubeConnector
    connector = YouTubeConnector()
    assert connector.get_default_interval() == timedelta(hours=1)


def test_youtube_connector_validate_config_false_without_auth():
    from pulse.connectors.youtube import YouTubeConnector
    connector = YouTubeConnector()
    assert asyncio.run(connector.validate_config()) is False


def test_youtube_connector_parses_activities():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return [{"id": "act-1", "snippet": {"publishedAt": "2026-03-23T10:00:00Z", "title": "Cool Video", "channelTitle": "TestChannel", "type": "upload"}, "contentDetails": {"upload": {"videoId": "vid-123"}}}]
        async def list_liked_videos(self, since=None):
            return []
        async def list_subscriptions(self, since=None):
            return []

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())
    assert len(events) == 1
    assert events[0].id == "youtube:act-1"
    assert events[0].source == "youtube"
    assert events[0].event_type == "media.youtube.activity"
    assert events[0].data["title"] == "Cool Video"
    assert events[0].data["channel"] == "TestChannel"
    assert events[0].data["video_id"] == "vid-123"
    assert events[0].data["activity_type"] == "upload"


def test_youtube_connector_parses_liked_videos():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return []
        async def list_liked_videos(self, since=None):
            return [{"id": "like-1", "snippet": {"publishedAt": "2026-03-23T12:00:00Z", "title": "Liked Video", "videoOwnerChannelTitle": "LikedChannel"}, "contentDetails": {"videoId": "vid-456"}}]
        async def list_subscriptions(self, since=None):
            return []

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())
    assert len(events) == 1
    assert events[0].event_type == "media.youtube.like"
    assert events[0].data["title"] == "Liked Video"
    assert events[0].data["video_id"] == "vid-456"


def test_youtube_connector_parses_subscriptions():
    from pulse.connectors.youtube import YouTubeConnector

    class FakeYouTubeClient:
        async def list_activities(self, since=None):
            return []
        async def list_liked_videos(self, since=None):
            return []
        async def list_subscriptions(self, since=None):
            return [{"id": "sub-1", "snippet": {"publishedAt": "2026-03-22T08:00:00Z", "title": "SubChannel", "resourceId": {"channelId": "UC-123"}}}]

    connector = YouTubeConnector(client=FakeYouTubeClient())
    events = asyncio.run(connector.pull())
    assert len(events) == 1
    assert events[0].event_type == "media.youtube.subscription"
    assert events[0].data["channel_name"] == "SubChannel"
    assert events[0].data["channel_id"] == "UC-123"

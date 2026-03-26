import asyncio
from datetime import UTC, datetime, timedelta


def _make_fake_service(activities=None, liked=None, subscriptions=None):
    """Mimics: service.activities().list().execute(), service.videos().list().execute(), etc."""
    class FakeRequest:
        def __init__(self, items):
            self._items = items
        def execute(self):
            return {"items": self._items}

    class FakeActivities:
        def list(self, **kwargs):
            return FakeRequest(activities or [])

    class FakeVideos:
        def list(self, **kwargs):
            return FakeRequest(liked or [])

    class FakeSubscriptions:
        def list(self, **kwargs):
            return FakeRequest(subscriptions or [])

    class FakeService:
        def activities(self):
            return FakeActivities()
        def videos(self):
            return FakeVideos()
        def subscriptions(self):
            return FakeSubscriptions()

    return FakeService()


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

    service = _make_fake_service(activities=[
        {"id": "act-1", "snippet": {"publishedAt": "2026-03-23T10:00:00Z", "title": "Cool Video", "channelTitle": "TestChannel", "type": "upload"}, "contentDetails": {"upload": {"videoId": "vid-123"}}},
    ])

    connector = YouTubeConnector(client=service)
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

    service = _make_fake_service(liked=[
        {"id": "vid-456", "snippet": {"publishedAt": "2026-03-23T12:00:00Z", "title": "Liked Video", "videoOwnerChannelTitle": "LikedChannel"}},
    ])

    connector = YouTubeConnector(client=service)
    events = asyncio.run(connector.pull())
    assert len(events) == 1
    assert events[0].event_type == "media.youtube.like"
    assert events[0].data["title"] == "Liked Video"
    assert events[0].data["video_id"] == "vid-456"


def test_youtube_connector_parses_subscriptions():
    from pulse.connectors.youtube import YouTubeConnector

    service = _make_fake_service(subscriptions=[
        {"id": "sub-1", "snippet": {"publishedAt": "2026-03-22T08:00:00Z", "title": "SubChannel", "resourceId": {"channelId": "UC-123"}}},
    ])

    connector = YouTubeConnector(client=service)
    events = asyncio.run(connector.pull())
    assert len(events) == 1
    assert events[0].event_type == "media.youtube.subscription"
    assert events[0].data["channel_name"] == "SubChannel"
    assert events[0].data["channel_id"] == "UC-123"

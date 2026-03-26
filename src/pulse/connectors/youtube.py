from datetime import UTC, datetime, timedelta
from typing import Any

from pulse.connectors.google_auth import GoogleAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event


class YouTubeConnector(Connector):
    def __init__(self, auth_manager: GoogleAuthManager | None = None, client: Any = None) -> None:
        self._auth_manager = auth_manager
        self._client = client

    async def pull(self, since: datetime | None = None) -> list[Event]:
        service = self._get_client()
        events: list[Event] = []

        # Activities (uploads, likes, etc.)
        kwargs: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "mine": True,
            "maxResults": 50,
        }
        if since is not None:
            kwargs["publishedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            results = service.activities().list(**kwargs).execute()
            for item in results.get("items", []):
                events.append(self._activity_to_event(item))
        except Exception:
            pass  # activities endpoint can fail if channel has no content

        # Liked videos
        try:
            liked_kwargs: dict[str, Any] = {
                "part": "snippet,contentDetails",
                "myRating": "like",
                "maxResults": 50,
            }
            results = service.videos().list(**liked_kwargs).execute()
            for item in results.get("items", []):
                events.append(self._liked_to_event(item))
        except Exception:
            pass

        # Subscriptions
        try:
            sub_kwargs: dict[str, Any] = {
                "part": "snippet",
                "mine": True,
                "maxResults": 50,
                "order": "relevance",
            }
            results = service.subscriptions().list(**sub_kwargs).execute()
            for item in results.get("items", []):
                events.append(self._subscription_to_event(item))
        except Exception:
            pass

        return events

    def get_source_name(self) -> str:
        return "youtube"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=1)

    async def validate_config(self) -> bool:
        if self._client is not None:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._auth_manager is None:
            raise RuntimeError("No auth_manager or client provided")
        creds = self._auth_manager.get_credentials()
        from googleapiclient.discovery import build
        return build("youtube", "v3", credentials=creds)

    def _activity_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        activity_type = snippet.get("type", "unknown")
        video_id = ""
        if activity_type in content:
            video_id = content[activity_type].get("videoId", "")
        return Event(
            id=f"youtube:{item['id']}",
            timestamp=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
            source="youtube",
            event_type="media.youtube.activity",
            data={"title": snippet.get("title", ""), "channel": snippet.get("channelTitle", ""), "video_id": video_id, "activity_type": activity_type},
        )

    def _liked_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        return Event(
            id=f"youtube:like:{item['id']}",
            timestamp=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
            source="youtube",
            event_type="media.youtube.like",
            data={"title": snippet.get("title", ""), "channel": snippet.get("channelOwnerChannelTitle", ""), "video_id": item["id"]},
        )

    def _subscription_to_event(self, item: dict[str, Any]) -> Event:
        snippet = item.get("snippet", {})
        resource = snippet.get("resourceId", {})
        return Event(
            id=f"youtube:sub:{resource.get('channelId', item['id'])}",
            timestamp=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00")),
            source="youtube",
            event_type="media.youtube.subscription",
            data={"channel_name": snippet.get("title", ""), "channel_id": resource.get("channelId", "")},
        )

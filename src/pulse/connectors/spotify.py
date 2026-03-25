from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from pulse.app.config import ConnectorConfig
from pulse.domain.connectors import Connector
from pulse.domain.events import Event
from pulse.connectors.spotify_auth import SpotifyAuthManager

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SupplementaryPullMixin:
    def get_supplementary_jobs(
        self, config: ConnectorConfig
    ) -> list[tuple[str, timedelta, Callable]]:
        return []


class SpotifyConnector(Connector, SupplementaryPullMixin):
    def __init__(
        self,
        auth_manager: SpotifyAuthManager | None = None,
        http_client: object | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._http = http_client

    def get_source_name(self) -> str:
        return "spotify"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        """Pull recently played tracks."""
        client = self._get_http_client()
        owns_client = self._http is None
        try:
            params: dict = {"limit": 50}
            if since is not None:
                params["after"] = str(int(since.timestamp() * 1000))

            resp = await client.get(
                f"{SPOTIFY_API_BASE}/me/player/recently-played",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            events = []
            for item in data.get("items", []):
                track = item["track"]
                played_at = item["played_at"]
                events.append(Event(
                    id=f"spotify:play:{track['id']}:{played_at}",
                    timestamp=datetime.fromisoformat(played_at.replace("Z", "+00:00")),
                    source="spotify",
                    event_type="media.spotify.play",
                    data={
                        "track_name": track["name"],
                        "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                        "album": track.get("album", {}).get("name", ""),
                        "played_at": played_at,
                        "duration_ms": track.get("duration_ms", 0),
                    },
                ))
            return events
        finally:
            if owns_client:
                await client.aclose()

    async def _pull_supplementary(self) -> list[Event]:
        """Pull saved tracks, top tracks, top artists. Stateless."""
        events: list[Event] = []
        client = self._get_http_client()
        owns_client = self._http is None
        headers = self._auth_headers()
        now = datetime.now(UTC)
        try:
            # Saved tracks (first page only)
            resp = await client.get(
                f"{SPOTIFY_API_BASE}/me/tracks",
                params={"limit": 50},
                headers=headers,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                track = item["track"]
                events.append(Event(
                    id=f"spotify:save:{track['id']}",
                    timestamp=datetime.fromisoformat(
                        item["added_at"].replace("Z", "+00:00")
                    ),
                    source="spotify",
                    event_type="media.spotify.save",
                    data={
                        "track_name": track["name"],
                        "artist": track["artists"][0]["name"] if track["artists"] else "Unknown",
                        "album": track.get("album", {}).get("name", ""),
                        "saved_at": item["added_at"],
                    },
                ))

            # Top tracks (all three time ranges)
            for time_range in ("short_term", "medium_term", "long_term"):
                resp = await client.get(
                    f"{SPOTIFY_API_BASE}/me/top/tracks",
                    params={"limit": 20, "time_range": time_range},
                    headers=headers,
                )
                resp.raise_for_status()
                for rank, item in enumerate(resp.json().get("items", []), 1):
                    if "id" not in item:
                        continue
                    events.append(Event(
                        id=f"spotify:top_track:{item['id']}:{time_range}",
                        timestamp=now,
                        source="spotify",
                        event_type="media.spotify.top_track",
                        data={
                            "track_name": item["name"],
                            "artist": item["artists"][0]["name"] if item["artists"] else "Unknown",
                            "rank": rank,
                            "time_range": time_range,
                            "pulled_at": now.isoformat(),
                        },
                    ))

            # Top artists (all three time ranges)
            for time_range in ("short_term", "medium_term", "long_term"):
                resp = await client.get(
                    f"{SPOTIFY_API_BASE}/me/top/artists",
                    params={"limit": 20, "time_range": time_range},
                    headers=headers,
                )
                resp.raise_for_status()
                for rank, item in enumerate(resp.json().get("items", []), 1):
                    if "id" not in item:
                        continue
                    events.append(Event(
                        id=f"spotify:top_artist:{item['id']}:{time_range}",
                        timestamp=now,
                        source="spotify",
                        event_type="media.spotify.top_artist",
                        data={
                            "artist_name": item["name"],
                            "genres": item.get("genres", []),
                            "rank": rank,
                            "time_range": time_range,
                            "pulled_at": now.isoformat(),
                        },
                    ))

            return events
        finally:
            if owns_client:
                await client.aclose()

    def get_supplementary_jobs(
        self, config: ConnectorConfig
    ) -> list[tuple[str, timedelta, Callable]]:
        from pulse.jobs.scheduler import parse_interval
        interval_str = getattr(config, "supplementary_interval", "6h")
        interval = parse_interval(interval_str)
        return [("supplementary", interval, self._pull_supplementary)]

    def _auth_headers(self) -> dict[str, str]:
        token = self._auth_manager.get_valid_token()
        return {"Authorization": f"Bearer {token}"}

    def _get_http_client(self):
        if self._http is not None:
            return self._http
        return httpx.AsyncClient()

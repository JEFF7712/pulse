import asyncio
from datetime import UTC, datetime, timedelta

from pulse.connectors.spotify import SpotifyConnector


def test_spotify_connector_source_name():
    connector = SpotifyConnector()
    assert connector.get_source_name() == "spotify"


def test_spotify_connector_default_interval():
    connector = SpotifyConnector()
    assert connector.get_default_interval() == timedelta(minutes=30)


def test_spotify_connector_validate_config_false_without_auth():
    connector = SpotifyConnector()
    assert asyncio.run(connector.validate_config()) is False


def test_spotify_connector_parses_recently_played():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        async def get(self, url, **kwargs):
            class Resp:
                def raise_for_status(self): pass
                def json(self):
                    return {
                        "items": [{
                            "track": {
                                "id": "track-1",
                                "name": "Cool Song",
                                "artists": [{"name": "Artist A"}],
                                "album": {"name": "Album X"},
                                "duration_ms": 240000,
                            },
                            "played_at": "2026-03-25T10:30:00Z",
                        }],
                        "cursors": {"after": "1711360200000"},
                    }
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector.pull())

    assert len(events) == 1
    e = events[0]
    assert e.id == "spotify:play:track-1:2026-03-25T10:30:00Z"
    assert e.source == "spotify"
    assert e.event_type == "media.spotify.play"
    assert e.data["track_name"] == "Cool Song"
    assert e.data["artist"] == "Artist A"
    assert e.data["album"] == "Album X"
    assert e.data["duration_ms"] == 240000
    assert e.data["played_at"] == "2026-03-25T10:30:00Z"


def test_spotify_connector_parses_saved_tracks():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        async def get(self, url, **kwargs):
            class Resp:
                def raise_for_status(self): pass
                def json(self):
                    return {
                        "items": [{
                            "added_at": "2026-03-20T08:00:00Z",
                            "track": {
                                "id": "saved-1",
                                "name": "Saved Song",
                                "artists": [{"name": "Artist B"}],
                                "album": {"name": "Album Y"},
                            },
                        }],
                        "next": None,
                    }
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector._pull_supplementary())

    saved = [e for e in events if e.event_type == "media.spotify.save"]
    assert len(saved) == 1
    assert saved[0].data["track_name"] == "Saved Song"
    assert saved[0].id == "spotify:save:saved-1"


def test_spotify_connector_parses_top_tracks():
    class FakeAuth:
        def is_authorized(self):
            return True
        def get_valid_token(self):
            return "fake_token"

    class FakeHTTPClient:
        call_count = 0
        async def get(self, url, **kwargs):
            self.call_count += 1
            class Resp:
                def raise_for_status(self): pass
                def json(resp_self):
                    if "top/tracks" in url:
                        return {
                            "items": [{
                                "id": "top-1",
                                "name": "Top Song",
                                "artists": [{"name": "Artist C"}],
                            }],
                        }
                    elif "top/artists" in url:
                        return {
                            "items": [{
                                "id": "topart-1",
                                "name": "Top Artist",
                                "genres": ["pop", "rock"],
                            }],
                        }
                    # saved tracks returns empty
                    return {"items": [], "next": None}
            return Resp()

    connector = SpotifyConnector(auth_manager=FakeAuth(), http_client=FakeHTTPClient())
    events = asyncio.run(connector._pull_supplementary())

    top_tracks = [e for e in events if e.event_type == "media.spotify.top_track"]
    top_artists = [e for e in events if e.event_type == "media.spotify.top_artist"]
    assert len(top_tracks) >= 1
    assert top_tracks[0].data["track_name"] == "Top Song"
    assert top_tracks[0].data["rank"] == 1
    assert len(top_artists) >= 1
    assert top_artists[0].data["artist_name"] == "Top Artist"
    assert top_artists[0].data["genres"] == ["pop", "rock"]


def test_spotify_connector_has_supplementary_jobs():
    from pulse.app.config import ConnectorConfig
    connector = SpotifyConnector()
    jobs = connector.get_supplementary_jobs(ConnectorConfig(supplementary_interval="6h"))
    assert len(jobs) == 1
    suffix, interval, _ = jobs[0]
    assert suffix == "supplementary"
    assert interval == timedelta(hours=6)

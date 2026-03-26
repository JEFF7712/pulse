import asyncio
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.spotify import SpotifyConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


class FakeAuth:
    def is_authorized(self):
        return True
    def get_valid_token(self):
        return "fake_token"


class FakeHTTPClient:
    async def get(self, url, **kwargs):
        class Resp:
            def raise_for_status(self): pass
            def json(resp_self):
                if "recently-played" in url:
                    return {
                        "items": [{
                            "track": {
                                "id": "track-1",
                                "name": "Test Song",
                                "artists": [{"name": "Test Artist"}],
                                "album": {"name": "Test Album"},
                                "duration_ms": 200000,
                            },
                            "played_at": "2026-03-25T10:30:00Z",
                        }],
                        "cursors": {"after": "1711360200000"},
                    }
                return {"items": [], "next": None}
        return Resp()

    async def aclose(self):
        pass


def test_spotify_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        db_path = tmp_path / "pulse.db"

        connector = SpotifyConnector(
            auth_manager=FakeAuth(),
            http_client=FakeHTTPClient(),
        )
        registry = ConnectorRegistry()
        registry.register_pull("spotify", lambda: connector)

        config = PulseConfig(
            database_path=str(db_path),
            connectors={"spotify": ConnectorConfig(enabled=True, poll_interval="30m")},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]
        assert connector.get_source_name() == "spotify"

        events = await connector.pull()
        assert len(events) == 1
        assert events[0].event_type == "media.spotify.play"
        assert events[0].data["track_name"] == "Test Song"

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(events)

            sync_repo = SyncStateRepository(db)
            await sync_repo.save("spotify", events[-1].timestamp.isoformat())
            state = await sync_repo.load("spotify")
            assert state is not None

            stored = await event_repo.list_events_for_day("2026-03-25")
            assert len(stored) == 1
            assert stored[0].id == "spotify:play:track-1:2026-03-25T10:30:00Z"

    asyncio.run(exercise())

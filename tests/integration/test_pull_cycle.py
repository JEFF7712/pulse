import asyncio
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.connectors import Connector
from pulse.domain.events import Event
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


class FakeConnector(Connector):
    def __init__(self):
        self.pull_count = 0

    async def pull(self, since=None):
        self.pull_count += 1
        return [
            Event(
                id=f"fake:evt-{self.pull_count}",
                timestamp=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
                source="fake",
                event_type="test.event",
                data={"count": self.pull_count},
            )
        ]

    def get_source_name(self):
        return "fake"


def test_full_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        db_path = tmp_path / "test.db"

        registry = ConnectorRegistry()
        registry.register_pull("fake", lambda: FakeConnector())
        config = PulseConfig(
            database_path=str(db_path),
            connectors={"fake": ConnectorConfig(enabled=True)},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            # First pull
            events = await connector.pull()
            await event_repo.upsert_events(events)
            latest = max(e.timestamp for e in events)
            await sync_state.save("fake", latest.isoformat())

            # Verify events stored
            stored = await event_repo.list_events_for_day("2026-03-24")
            assert len(stored) == 1
            assert stored[0].id == "fake:evt-1"

            # Verify sync state
            cursor = await sync_state.load("fake")
            assert cursor is not None

    asyncio.run(exercise())

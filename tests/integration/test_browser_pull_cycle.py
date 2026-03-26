import asyncio
import sqlite3
from datetime import UTC, datetime

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.connectors.browser import BrowserHistoryConnector
from pulse.connectors.registry import ConnectorRegistry
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository


def _create_chrome_fixture(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    conn.execute(
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)"
    )
    chrome_ts = (1774432800 + 11644473600) * 1000000
    conn.execute("INSERT INTO urls VALUES (1, 'https://example.com', 'Example')")
    conn.execute(f"INSERT INTO visits VALUES (1, 1, {chrome_ts})")
    conn.commit()
    conn.close()


def test_browser_pull_cycle_stores_events_and_updates_sync_state(tmp_path):
    async def exercise():
        # Create fixture
        browser_db = tmp_path / "History"
        _create_chrome_fixture(browser_db)

        db_path = tmp_path / "pulse.db"
        registry = ConnectorRegistry()
        registry.register_pull("browser", lambda: BrowserHistoryConnector(
            browser="chrome", db_path=str(browser_db),
        ))
        config = PulseConfig(
            database_path=str(db_path),
            connectors={"browser": ConnectorConfig(enabled=True)},
        )
        await registry.build_active_connectors(config)

        pull_connectors = registry.get_pull_connectors()
        assert len(pull_connectors) == 1
        connector, cc = pull_connectors[0]

        async with connect_db(str(db_path)) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            events = await connector.pull()
            assert len(events) == 1
            await event_repo.upsert_events(events)
            latest = max(e.timestamp for e in events)
            await sync_state.save("browser", latest.isoformat())

            stored = await event_repo.list_events_for_day("2026-03-25")
            assert len(stored) == 1
            assert stored[0].data["url"] == "https://example.com"

            cursor = await sync_state.load("browser")
            assert cursor is not None

    asyncio.run(exercise())

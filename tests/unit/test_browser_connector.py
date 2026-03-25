import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulse.connectors.browser import (
    BrowserHistoryConnector,
    BROWSER_PRESETS,
    normalize_timestamp,
)


def test_browser_connector_source_name():
    connector = BrowserHistoryConnector()
    assert connector.get_source_name() == "browser"


def test_browser_connector_default_interval():
    connector = BrowserHistoryConnector()
    assert connector.get_default_interval() == timedelta(minutes=15)


def test_browser_connector_validate_config_false_when_db_missing(tmp_path):
    connector = BrowserHistoryConnector(db_path=str(tmp_path / "nonexistent.db"))
    assert asyncio.run(connector.validate_config()) is False


def test_browser_connector_validate_config_true_when_db_exists(tmp_path):
    db_path = tmp_path / "History"
    db_path.write_text("")  # empty file is enough for validate_config
    connector = BrowserHistoryConnector(db_path=str(db_path))
    assert asyncio.run(connector.validate_config()) is True


def test_normalize_timestamp_chrome():
    preset = BROWSER_PRESETS["chrome"]
    raw = 13418913600000000
    result = normalize_timestamp(raw, preset["epoch_offset"], preset["timestamp_divisor"])
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 25
    assert result.hour == 12


def test_normalize_timestamp_firefox():
    preset = BROWSER_PRESETS["firefox"]
    raw = 1774440000000000
    result = normalize_timestamp(raw, preset["epoch_offset"], preset["timestamp_divisor"])
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 25
    assert result.hour == 12


def _create_chrome_fixture(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    conn.execute(
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)"
    )
    chrome_ts = 13418913600000000  # 2026-03-25 12:00:00 UTC
    conn.execute("INSERT INTO urls VALUES (1, 'https://example.com', 'Example')")
    conn.execute(f"INSERT INTO visits VALUES (1, 1, {chrome_ts})")
    chrome_ts_old = 13418899200000000  # 2026-03-25 08:00:00 UTC
    conn.execute("INSERT INTO urls VALUES (2, 'https://old.com', 'Old Page')")
    conn.execute(f"INSERT INTO visits VALUES (2, 2, {chrome_ts_old})")
    conn.commit()
    conn.close()


def test_browser_connector_pulls_from_chrome_fixture(tmp_path):
    db_path = tmp_path / "History"
    _create_chrome_fixture(db_path)

    connector = BrowserHistoryConnector(browser="chrome", db_path=str(db_path))
    events = asyncio.run(connector.pull())

    assert len(events) == 2
    urls = {e.data["url"] for e in events}
    assert "https://example.com" in urls
    assert "https://old.com" in urls
    assert all(e.event_type == "browsing.visit" for e in events)
    assert all(e.source == "browser" for e in events)


def test_browser_connector_pulls_since_cursor(tmp_path):
    db_path = tmp_path / "History"
    _create_chrome_fixture(db_path)

    connector = BrowserHistoryConnector(browser="chrome", db_path=str(db_path))
    since = datetime(2026, 3, 25, 9, 0, 0, tzinfo=UTC)
    events = asyncio.run(connector.pull(since=since))

    assert len(events) == 1
    assert events[0].data["url"] == "https://example.com"


def test_browser_presets_have_required_keys():
    for name, preset in BROWSER_PRESETS.items():
        assert "url_table" in preset, f"{name} missing url_table"
        assert "visit_table" in preset, f"{name} missing visit_table"
        assert "epoch_offset" in preset, f"{name} missing epoch_offset"
        assert "timestamp_divisor" in preset, f"{name} missing timestamp_divisor"

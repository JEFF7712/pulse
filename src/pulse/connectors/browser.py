import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

BROWSER_PRESETS: dict[str, dict] = {
    "chrome": {
        "linux": "~/.config/google-chrome/Default/History",
        "darwin": "~/Library/Application Support/Google/Chrome/Default/History",
        "win32": "~/AppData/Local/Google/Chrome/User Data/Default/History",
        "url_table": "urls",
        "visit_table": "visits",
        "url_column": "url",
        "title_column": "title",
        "visit_time_column": "visit_time",
        "url_id_column": "id",
        "visit_url_column": "url",
        "epoch_offset": 11_644_473_600,
        "timestamp_divisor": 1_000_000,
    },
    "firefox": {
        "linux": "~/.mozilla/firefox/*.default*/places.sqlite",
        "darwin": "~/Library/Application Support/Firefox/Profiles/*.default*/places.sqlite",
        "win32": "~/AppData/Roaming/Mozilla/Firefox/Profiles/*.default*/places.sqlite",
        "url_table": "moz_places",
        "visit_table": "moz_historyvisits",
        "url_column": "url",
        "title_column": "title",
        "visit_time_column": "visit_date",
        "url_id_column": "id",
        "visit_url_column": "place_id",
        "epoch_offset": 0,
        "timestamp_divisor": 1_000_000,
    },
}


def normalize_timestamp(
    raw_value: int, epoch_offset: int, timestamp_divisor: int
) -> datetime:
    """Convert browser-specific timestamp to UTC datetime.

    Formula: unix_ts = (raw_value / timestamp_divisor) - epoch_offset
    """
    unix_ts = (raw_value / timestamp_divisor) - epoch_offset
    return datetime.fromtimestamp(unix_ts, tz=UTC)


class BrowserHistoryConnector(Connector):
    def __init__(
        self, browser: str = "chrome", db_path: str | None = None
    ) -> None:
        self._browser = browser
        self._db_path = db_path

    def get_source_name(self) -> str:
        return "browser"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=15)

    async def validate_config(self) -> bool:
        path = self._resolve_db_path()
        return path is not None and path.exists()

    async def pull(self, since: datetime | None = None) -> list[Event]:
        db_path = self._resolve_db_path()
        if db_path is None or not db_path.exists():
            return []

        preset = BROWSER_PRESETS.get(self._browser, BROWSER_PRESETS["chrome"])
        fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            shutil.copy2(db_path, tmp_path)
            return self._query_visits(tmp_path, preset, since)
        finally:
            os.unlink(tmp_path)

    def _query_visits(
        self, db_path: str, preset: dict, since: datetime | None
    ) -> list[Event]:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            url_table = preset["url_table"]
            visit_table = preset["visit_table"]
            time_col = preset["visit_time_column"]
            url_id_col = preset["url_id_column"]
            visit_url_col = preset["visit_url_column"]
            url_col = preset["url_column"]
            title_col = preset["title_column"]

            query = (
                f"SELECT u.{url_col}, u.{title_col}, v.{time_col} "
                f"FROM {visit_table} v "
                f"JOIN {url_table} u ON u.{url_id_col} = v.{visit_url_col} "
            )
            params: list = []

            if since is not None:
                raw_since = int(
                    (since.timestamp() + preset["epoch_offset"])
                    * preset["timestamp_divisor"]
                )
                query += f"WHERE v.{time_col} > ? "
                params.append(raw_since)

            query += f"ORDER BY v.{time_col}"

            rows = conn.execute(query, params).fetchall()

            events = []
            for url, title, raw_time in rows:
                visit_time = normalize_timestamp(
                    raw_time, preset["epoch_offset"], preset["timestamp_divisor"]
                )
                events.append(Event(
                    id=f"browser:{self._browser}:{raw_time}:{hashlib.md5(url.encode()).hexdigest()[:8]}",
                    timestamp=visit_time,
                    source="browser",
                    event_type="browsing.visit",
                    data={
                        "url": url,
                        "title": title or "",
                        "visit_time": visit_time.isoformat(),
                        "browser": self._browser,
                    },
                ))
            return events
        finally:
            conn.close()

    def _resolve_db_path(self) -> Path | None:
        if self._db_path:
            return Path(self._db_path).expanduser()
        preset = BROWSER_PRESETS.get(self._browser)
        if not preset:
            return None
        platform_path = preset.get(sys.platform)
        if not platform_path:
            return None
        expanded = Path(platform_path).expanduser()
        if "*" in platform_path:
            matches = list(Path("/").glob(str(expanded).lstrip("/")))
            if not matches:
                return None
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]
        return expanded

"""Read-only ops commands: discover, status, logs, reset, review."""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from pulse.app import cli_ui as ui
from pulse.app.config import DiscoveryConfig, PulseConfig
from pulse.app.config_loader import PulseConfigNotFoundError, load_config
from pulse.domain.notifications import NotificationChannel


def _resolve_current_day(timezone: str) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(timezone)).date()


def discover(args) -> None:
    from pulse.jobs.runners import run_aggregation_job

    config = load_config()
    target = (
        date.fromisoformat(args.date)
        if args.date
        else _resolve_current_day(config.timezone)
    )

    ui.rule("pulse discover")
    ui.say(f"[accent]Aggregating stats[/] for [bold]{target.isoformat()}[/]…")
    result = asyncio.run(
        run_aggregation_job(
            day=target,
            database_path=config.database_path,
            timezone=config.timezone,
        )
    )
    ui.say(f"[bold]{result.status}[/]: {result.detail}")


def status(config_dir: Path | None = None) -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    try:
        config = load_config(config_dir=config_dir, require_files=True)
    except PulseConfigNotFoundError as exc:
        print(str(exc))
        sys.exit(1)

    if not Path(config.database_path).exists():
        ui.error("No database found. Run [cmd]pulse pull[/] first.")
        sys.exit(1)

    async def _show():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)

            cur = await db.execute(
                "SELECT source, event_type, COUNT(*) FROM events "
                "GROUP BY source, event_type ORDER BY COUNT(*) DESC"
            )
            rows = await cur.fetchall()

            cur2 = await db.execute("SELECT COUNT(*) FROM events")
            total = (await cur2.fetchone())[0]

            cur3 = await db.execute("SELECT MIN(timestamp), MAX(timestamp) FROM events")
            mn, mx = await cur3.fetchone()

            cur4 = await db.execute(
                "SELECT source, cursor, updated_at FROM connector_sync_state ORDER BY source"
            )
            sync_rows = await cur4.fetchall()

            ui.rule("pulse status")
            ui.status_tables(
                database=str(config.database_path),
                total=total,
                time_range=f"{mn} → {mx}",
                event_rows=rows,
                sync_rows=sync_rows,
            )

    asyncio.run(_show())


async def _backfill_embeddings(db, embedder) -> int:
    """Embed every event that has no stored embedding yet. Returns the count embedded."""
    from pulse.services.embedding import embed_missing

    return await embed_missing(db, embedder)


def embed(args) -> None:
    from pulse.semantic.factory import load_embedder
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()
    embedder = load_embedder(config)
    if embedder is None:
        ui.error(
            "Semantic search is not available. Enable [semantic] in pulse.toml and "
            "install the extra: [cmd]pip install pulse-agent\\[semantic][/]."
        )
        sys.exit(1)

    if not Path(config.database_path).exists():
        ui.error("No database found. Run [cmd]pulse pull[/] first.")
        sys.exit(1)

    async def _run() -> int:
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            return await _backfill_embeddings(db, embedder)

    ui.rule("pulse embed")
    count = asyncio.run(_run())
    ui.success(f"Embedded {count} event(s).")


def logs(args) -> None:
    import json as json_mod
    from datetime import UTC, datetime

    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

    if not Path(config.database_path).exists():
        ui.error("No database found. Run [cmd]pulse pull[/] first.")
        sys.exit(1)

    async def _show():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)

            query = "SELECT timestamp, source, event_type, data FROM events"
            conditions: list[str] = []
            params: list = []

            if args.source:
                conditions.append("source = ?")
                params.append(args.source)

            if not args.all:
                now_iso = datetime.now(UTC).isoformat()
                conditions.append("timestamp <= ?")
                params.append(now_iso)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(args.n)

            cur = await db.execute(query, params)
            rows = await cur.fetchall()

            if not rows:
                ui.muted_line("No events found.")
                return

            ui.rule("pulse logs")
            log_rows: list[tuple[str, str, str, str]] = []
            for ts, source, etype, data_str in reversed(rows):
                data = json_mod.loads(data_str)
                # Pick the most useful field to show
                detail = (
                    data.get("subject")
                    or data.get("title")
                    or data.get("track_name")
                    or data.get("url", "")[:60]
                    or ""
                )
                ts_short = ts[:19] if len(ts) > 19 else ts
                log_rows.append((ts_short, source, etype, detail))
            ui.logs_table(log_rows)

    asyncio.run(_show())


def reset(args) -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

    config = load_config()

    if not Path(config.database_path).exists():
        ui.error("No database found.")
        sys.exit(1)

    source = args.source

    async def _do_reset():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            sync_state = SyncStateRepository(db)

            ui.rule("pulse reset")
            if source is None:
                # Reset all cursors
                cur = await db.execute(
                    "SELECT source, cursor FROM connector_sync_state ORDER BY source"
                )
                rows = await cur.fetchall()
                if not rows:
                    ui.muted_line("No sync cursors found.")
                    return

                ui.say("[accent]Current cursors[/]")
                for s, c in rows:
                    ui.kv_line(str(s), str(c))

                confirm = (
                    input(
                        "\nReset ALL sync cursors? This will re-pull all data. [y/N] "
                    )
                    .strip()
                    .lower()
                )
                if confirm not in ("y", "yes"):
                    ui.warning("Cancelled.")
                    return

                await db.execute("DELETE FROM connector_sync_state")
                await db.commit()
                ui.success(f"All {len(rows)} cursors cleared.")
            else:
                cursor = await sync_state.load(source)
                if not cursor:
                    ui.warning(f"No sync cursor found for '{source}'.")
                    return

                ui.kv_line(f"Cursor ({source})", str(cursor))
                confirm = (
                    input(
                        f"Reset sync cursor for '{source}'? This will re-pull all data. [y/N] "
                    )
                    .strip()
                    .lower()
                )
                if confirm not in ("y", "yes"):
                    ui.warning("Cancelled.")
                    return

                await db.execute(
                    "DELETE FROM connector_sync_state WHERE source = ?",
                    (source,),
                )
                await db.commit()
                ui.success(
                    f"Cursor for '{source}' cleared. Next pull will fetch all data."
                )

    asyncio.run(_do_reset())


async def _run_review(
    config: PulseConfig,
    *,
    channel: NotificationChannel | None,
    runner=None,
) -> tuple[bool, str]:
    """On-demand discovery pass: runs even when the schedule is off.

    Unlike the scheduled job this bypasses the change-surface gate — the user asked
    for a pass explicitly, so run one whether or not the data moved.

    Returns ``(recorded, message)``.
    """
    from pulse.jobs.discovery import run_discovery

    dc = config.discovery if config.discovery is not None else DiscoveryConfig()
    if not dc.command:
        return (
            False,
            "No discovery command configured. Set [discovery].command in pulse.toml.",
        )

    forced = config.model_copy(
        update={"discovery": dc.model_copy(update={"enabled": True})}
    )

    class _CaptureChannel:
        def __init__(self, inner: NotificationChannel | None):
            self._inner = inner
            self.sent: list = []

        def send(self, notification):
            self.sent.append(notification)
            if self._inner is not None:
                return self._inner.send(notification)
            return True

    capture = _CaptureChannel(channel)
    kwargs: dict = {"channel": capture, "force": True}
    if runner is not None:
        kwargs["runner"] = runner

    changes = await run_discovery(forced, **kwargs)
    if capture.sent:
        return True, capture.sent[-1].body
    if not changes.is_empty():
        return True, f"Recorded: {', '.join(changes.all_slugs())}"
    return False, "No new patterns recorded."


def review(args) -> None:
    from pulse.notifications.factory import build_notification_channel

    config = load_config(config_dir=getattr(args, "config_dir", None))
    channel = build_notification_channel(config)
    if channel is None:
        ui.error(
            "No notification channel configured. Set Telegram, ntfy, or another "
            "channel in pulse.toml."
        )
        sys.exit(1)

    ui.rule("pulse review")
    ui.say("[accent]Running discovery pass[/]…")

    delivered, message = asyncio.run(_run_review(config, channel=channel))
    if not delivered and "command" in message.lower():
        ui.error(message)
        sys.exit(1)
    if delivered:
        ui.success(message)
    else:
        ui.muted_line(message)

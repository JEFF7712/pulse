"""`pulse run` (server + scheduler) and `pulse pull` (one-shot connector pulls)."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from pulse.app import cli_ui as ui
from pulse.app.config_loader import load_config

logger = logging.getLogger(__name__)


def quiet_noisy_loggers() -> None:
    """Suppress chatty third-party loggers."""
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("google_auth_httplib2").setLevel(logging.WARNING)


def run_server(args) -> None:
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    quiet_noisy_loggers()

    config = load_config(config_dir=getattr(args, "config_dir", None))
    logger.info(
        "Loaded config: db=%s, vault=%s, tz=%s",
        config.database_path,
        config.vault_path,
        config.timezone,
    )

    # Ensure data directory exists
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

    from pulse.vault.onboarding import ensure_vault_onboarding

    ensure_vault_onboarding(config.vault_path)

    # Bootstrap schema
    async def _bootstrap():
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)

    asyncio.run(_bootstrap())
    logger.info("Database schema ready")

    # Build connector registry
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry

    registry = ConnectorRegistry()
    register_all(registry, config)
    asyncio.run(registry.build_active_connectors(config))

    active_pull = registry.get_pull_connectors()
    active_push = registry.get_push_connectors()
    logger.info(
        "Connectors: %d pull (%s), %d push (%s)",
        len(active_pull),
        ", ".join(c.get_source_name() for c, _ in active_pull),
        len(active_push),
        ", ".join(c.get_source_name() for c, _ in active_push),
    )

    # Build scheduler
    from pulse.jobs.scheduler import build_scheduler

    scheduler = build_scheduler(registry=registry, config=config)

    # Create FastAPI app with lifecycle events
    from pulse.app.main import create_app

    app = create_app(settings=config, registry=registry)

    @app.on_event("startup")
    async def _start_scheduler():
        scheduler.start()
        jobs = scheduler.get_jobs()
        logger.info("Scheduler started with %d jobs:", len(jobs))
        for job in jobs:
            logger.info("  - %s (trigger: %s)", job.id, job.trigger)

    @app.on_event("shutdown")
    async def _stop_scheduler():
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    ui.startup_panel(
        host=args.host,
        port=args.port,
        pull_names=", ".join(c.get_source_name() for c, _ in active_pull) or "none",
        push_names=", ".join(c.get_source_name() for c, _ in active_push) or "none",
        vault=str(config.vault_path),
        database=str(config.database_path),
    )

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def pull(args) -> None:
    from datetime import datetime

    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

    quiet_noisy_loggers()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

    registry = ConnectorRegistry()
    register_all(registry, config)
    asyncio.run(registry.build_active_connectors(config))

    active = registry.get_pull_connectors()
    filter_sources = set(args.sources) if args.sources else None

    if filter_sources:
        active = [(c, cc) for c, cc in active if c.get_source_name() in filter_sources]
        missing = filter_sources - {c.get_source_name() for c, _ in active}
        if missing:
            ui.warning(f"Unknown or inactive connectors: {', '.join(sorted(missing))}")

    if not active:
        ui.error("No active connectors to pull.")
        sys.exit(1)

    async def _run_pulls():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            for connector, _cc in active:
                source = connector.get_source_name()
                ui.inline(f"[bullet]●[/] [bold]{source}[/] … ", end="")
                try:
                    cursor = await sync_state.load(source)
                    since = datetime.fromisoformat(cursor) if cursor else None
                    events = await connector.pull(since=since)
                    if events:
                        new_count = await event_repo.upsert_events(events)
                        if hasattr(connector, "get_sync_timestamp"):
                            ts = connector.get_sync_timestamp()
                        else:
                            ts = max(e.timestamp for e in events)
                        await sync_state.save(source, ts.isoformat())
                        ui.say(
                            f"[ok]{new_count}[/] new, [muted]{len(events) - new_count} updated[/]"
                        )
                    else:
                        ui.say("[muted]0 events[/]")
                except Exception as e:
                    ui.say(f"[err]ERROR:[/] {e}")

    asyncio.run(_run_pulls())

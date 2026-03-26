import argparse
import asyncio
import logging
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import GoogleAuthManager, SCOPES_BY_CONNECTOR
from pulse.connectors.spotify_auth import SpotifyAuthManager, SPOTIFY_SCOPES, REDIRECT_URI

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Start Pulse (API server + scheduler)")
    run_parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    run_parser.add_argument("--log-level", default="info", help="Log level (default: info)")

    pull_parser = subparsers.add_parser("pull", help="Run pull cycle immediately")
    pull_parser.add_argument("sources", nargs="*", help="Connectors to pull (default: all)")

    digest_parser = subparsers.add_parser("digest", help="Run daily digest for a given day")
    digest_parser.add_argument("--date", default=None, help="Date to digest (YYYY-MM-DD, default: today)")

    discover_parser = subparsers.add_parser("discover", help="Run LLM discovery pass")
    discover_parser.add_argument("--cadence", default="daily", choices=["daily", "weekly", "monthly"])
    discover_parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD, default: today)")

    subparsers.add_parser("status", help="Show database stats")
    subparsers.add_parser("test-telegram", help="Send a test message via Telegram")

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="provider")
    auth_subparsers.add_parser("google", help="Authorize Google services")
    auth_subparsers.add_parser("spotify", help="Authorize Spotify")

    args = parser.parse_args()

    if args.command == "run":
        _run(args)
    elif args.command == "pull":
        _pull(args)
    elif args.command == "digest":
        _digest(args)
    elif args.command == "discover":
        _discover(args)
    elif args.command == "status":
        _status()
    elif args.command == "test-telegram":
        _test_telegram()
    elif args.command == "auth" and args.provider == "google":
        _auth_google()
    elif args.command == "auth" and args.provider == "spotify":
        _auth_spotify()
    else:
        parser.print_help()
        sys.exit(1)


def _run(args) -> None:
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    logger.info("Loaded config: db=%s, vault=%s, tz=%s", config.database_path, config.vault_path, config.timezone)

    # Ensure data directory exists
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

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

    print(f"Starting Pulse on {args.host}:{args.port}")
    print(f"  Pull connectors: {', '.join(c.get_source_name() for c, _ in active_pull) or 'none'}")
    print(f"  Push connectors: {', '.join(c.get_source_name() for c, _ in active_push) or 'none'}")
    print(f"  Vault: {config.vault_path}")
    print(f"  Database: {config.database_path}")

    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def _pull(args) -> None:
    from datetime import datetime
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

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
            print(f"Warning: unknown or inactive connectors: {', '.join(sorted(missing))}")

    if not active:
        print("No active connectors to pull.")
        sys.exit(1)

    async def _run_pulls():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            for connector, _cc in active:
                source = connector.get_source_name()
                print(f"Pulling {source}...", end=" ", flush=True)
                try:
                    cursor = await sync_state.load(source)
                    since = datetime.fromisoformat(cursor) if cursor else None
                    events = await connector.pull(since=since)
                    if events:
                        new_count = await event_repo.upsert_events(events)
                        latest = max(e.timestamp for e in events)
                        await sync_state.save(source, latest.isoformat())
                        print(f"{new_count} new, {len(events) - new_count} updated")
                    else:
                        print("0 events")
                except Exception as e:
                    print(f"ERROR: {e}")

    asyncio.run(_run_pulls())


def _digest(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_daily_digest_job, run_aggregation_job

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    print(f"Aggregating stats for {target.isoformat()}...")
    result = asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))
    print(f"  {result.detail}")

    print(f"Generating digest for {target.isoformat()}...")
    result = asyncio.run(run_daily_digest_job(
        day=target,
        database_path=config.database_path,
        vault_path=config.vault_path,
    ))
    print(f"  {result.status}: {result.detail}")


def _discover(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_discovery_job, run_aggregation_job, JobResult
    from pulse.llm.anthropic import AnthropicProvider

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    if not config.anthropic_api_key:
        print("Error: PULSE_ANTHROPIC_API_KEY must be set for discovery.")
        sys.exit(1)

    llm = AnthropicProvider(api_key=config.anthropic_api_key)

    print(f"Aggregating stats for {target.isoformat()}...")
    asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))

    print(f"Running {args.cadence} discovery for {target.isoformat()}...")
    result = asyncio.run(run_discovery_job(
        cadence=args.cadence,
        target_date=target,
        database_path=config.database_path,
        vault_path=config.vault_path,
        llm=llm,
    ))
    print(f"  {result.status}: {result.detail}")


def _status() -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

    if not Path(config.database_path).exists():
        print("No database found. Run 'pulse pull' first.")
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

            cur4 = await db.execute("SELECT source, cursor, updated_at FROM connector_sync_state ORDER BY source")
            sync_rows = await cur4.fetchall()

            print(f"Database: {config.database_path}")
            print(f"Total events: {total}")
            print(f"Time range: {mn} to {mx}")
            print()
            print("Events by source:")
            for source, etype, count in rows:
                print(f"  {source:10} {etype:30} {count:>6}")
            print()
            print("Sync cursors:")
            for source, cursor, updated_at in sync_rows:
                print(f"  {source:10} {cursor[:30]:30} (updated {updated_at})")

    asyncio.run(_show())


def _test_telegram() -> None:
    from pulse.notifications.telegram import TelegramChannel
    from pulse.domain.notifications import Notification

    config = load_config()

    if not config.telegram_bot_token or not config.telegram_chat_id:
        print("Error: PULSE_TELEGRAM_BOT_TOKEN and PULSE_TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    channel = TelegramChannel(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )

    notification = Notification(
        title="Pulse Test",
        body="If you're reading this, Telegram notifications are working!",
        category="test",
        priority="low",
    )

    try:
        channel.send(notification)
        print("Test message sent! Check your Telegram.")
    except Exception as e:
        print(f"Failed to send: {e}")
        sys.exit(1)


def _auth_google() -> None:
    config = load_config()

    if not config.google_client_id or not config.google_client_secret:
        print("Error: PULSE_GOOGLE_CLIENT_ID and PULSE_GOOGLE_CLIENT_SECRET must be set.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "google_tokens.json"
    auth_manager = GoogleAuthManager(
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        token_path=token_path,
    )

    google_connectors = [
        name for name in config.connectors
        if name in SCOPES_BY_CONNECTOR and config.connectors[name].enabled
    ]

    if not google_connectors:
        print("No Google connectors enabled in pulse.toml. Enable gmail, calendar, or youtube.")
        sys.exit(1)

    scopes = auth_manager.get_required_scopes(google_connectors)
    print(f"Authorizing for: {', '.join(google_connectors)}")
    print(f"Scopes: {', '.join(scopes)}")

    auth_manager.authorize(scopes)
    print("Authorization complete!")


def _auth_spotify() -> None:
    config = load_config()

    if not config.spotify_client_id or not config.spotify_client_secret:
        print("Error: PULSE_SPOTIFY_CLIENT_ID and PULSE_SPOTIFY_CLIENT_SECRET must be set.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "spotify_tokens.json"
    auth_manager = SpotifyAuthManager(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        token_path=token_path,
    )

    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(SPOTIFY_SCOPES, state)

    print(f"Opening browser for Spotify authorization...")
    print(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    # Start temporary HTTP server to receive callback
    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            returned_state = query.get("state", [None])[0]
            code = query.get("code", [None])[0]

            if returned_state != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch \xe2\x80\x94 possible CSRF attack.")
                return

            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorization successful! You can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No authorization code received.")

        def log_message(self, format, *args):
            pass  # Suppress request logging

    server = HTTPServer(("localhost", 8888), CallbackHandler)
    server.handle_request()  # Handle single callback request

    if not received_code:
        print("Error: No authorization code received.")
        sys.exit(1)

    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    print("Spotify authorization complete!")

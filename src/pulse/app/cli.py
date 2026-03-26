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

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="provider")
    auth_subparsers.add_parser("google", help="Authorize Google services")
    auth_subparsers.add_parser("spotify", help="Authorize Spotify")

    args = parser.parse_args()

    if args.command == "run":
        _run(args)
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

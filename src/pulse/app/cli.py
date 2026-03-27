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

    subparsers.add_parser("configure", help="Interactive setup for .env, connectors, and auth")
    subparsers.add_parser("init", help="Set up profile and run initial data collection")
    subparsers.add_parser("status", help="Show database stats")
    subparsers.add_parser("insights", help="List discovered patterns")
    subparsers.add_parser("test-telegram", help="Send a test message via Telegram")

    reset_parser = subparsers.add_parser("reset", help="Clear sync cursor to re-pull from scratch")
    reset_parser.add_argument("source", nargs="?", default=None, help="Connector source name (e.g., gmail, browser), or omit for all")

    logs_parser = subparsers.add_parser("logs", help="Show recent events from the database")
    logs_parser.add_argument("--source", default=None, help="Filter by source")
    logs_parser.add_argument("-n", type=int, default=20, help="Number of events (default: 20)")
    logs_parser.add_argument("--all", action="store_true", help="Include future events (excluded by default)")

    cleanup_parser = subparsers.add_parser("cleanup", help="Remove events with timestamps in the future")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

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
    elif args.command == "configure":
        _configure()
    elif args.command == "init":
        _init()
    elif args.command == "status":
        _status()
    elif args.command == "insights":
        _insights()
    elif args.command == "logs":
        _logs(args)
    elif args.command == "reset":
        _reset(args)
    elif args.command == "cleanup":
        _cleanup(args)
    elif args.command == "test-telegram":
        _test_telegram()
    elif args.command == "auth" and args.provider == "google":
        _auth_google()
    elif args.command == "auth" and args.provider == "spotify":
        _auth_spotify()
    else:
        parser.print_help()
        sys.exit(1)


def _quiet_noisy_loggers() -> None:
    """Suppress chatty third-party loggers."""
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("google_auth_httplib2").setLevel(logging.WARNING)


def _run(args) -> None:
    import uvicorn

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _quiet_noisy_loggers()

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

    _quiet_noisy_loggers()
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
                        if hasattr(connector, "get_sync_timestamp"):
                            ts = connector.get_sync_timestamp()
                        else:
                            ts = max(e.timestamp for e in events)
                        await sync_state.save(source, ts.isoformat())
                        print(f"{new_count} new, {len(events) - new_count} updated")
                    else:
                        print("0 events")
                except Exception as e:
                    print(f"ERROR: {e}")

    asyncio.run(_run_pulls())


def _mask(value: str) -> str:
    """Show first 8 chars of a secret, mask the rest."""
    if len(value) > 12:
        return f"{value[:8]}..."
    return value


def _prompt_env_field(key: str, label: str, current: str, is_secret: bool = False) -> str:
    """Prompt for an env field. If it already has a value, ask to keep or change."""
    if current:
        display = _mask(current) if is_secret else current
        answer = input(f"  {label}: {display} — keep? [Y/n] ").strip().lower()
        if answer in ("n", "no"):
            new_val = input(f"  {label}: ").strip()
            return new_val if new_val else current
        return current
    else:
        value = input(f"  {label}: ").strip()
        return value


def _configure() -> None:
    import tomllib

    env_path = Path(".env")
    toml_path = Path("pulse.toml")

    print("=== Pulse Configuration ===\n")

    # Load existing .env
    existing_env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                existing_env[key.strip()] = val.strip()

    # --- Step 1: Core settings ---
    print("--- Step 1: Core Settings ---\n")

    env_values: dict[str, str] = {}
    core_fields = [
        ("PULSE_DATABASE_PATH", "Database path", "data/pulse.db", False),
        ("PULSE_VAULT_PATH", "Obsidian vault path", "Pulse-Vault", False),
        ("PULSE_TIMEZONE", "Timezone (e.g., America/Chicago)", "UTC", False),
    ]
    for key, label, default, is_secret in core_fields:
        current = existing_env.get(key, "") or default
        env_values[key] = _prompt_env_field(key, label, current, is_secret)

    # --- Step 2: Service credentials ---
    print("\n--- Step 2: Service Credentials ---")
    print("Leave blank to skip a service.\n")

    credential_fields = [
        ("PULSE_GOOGLE_CLIENT_ID", "Google Client ID", True),
        ("PULSE_GOOGLE_CLIENT_SECRET", "Google Client Secret", True),
        ("PULSE_SPOTIFY_CLIENT_ID", "Spotify Client ID", True),
        ("PULSE_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", True),
        ("PULSE_ANTHROPIC_API_KEY", "Anthropic API Key", True),
        ("PULSE_TELEGRAM_BOT_TOKEN", "Telegram Bot Token", True),
        ("PULSE_TELEGRAM_CHAT_ID", "Telegram Chat ID", False),
    ]
    for key, label, is_secret in credential_fields:
        current = existing_env.get(key, "")
        env_values[key] = _prompt_env_field(key, label, current, is_secret)

    # Write .env
    env_lines = [f"{key}={val}" for key, val in env_values.items()]
    env_path.write_text("\n".join(env_lines) + "\n")
    print(f"\n  Saved {env_path}")

    # --- Step 3: Connector config (pulse.toml) ---
    print("\n--- Step 3: Connector Configuration ---\n")

    existing_toml: dict = {}
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            existing_toml = tomllib.load(f)

    connectors_config = existing_toml.get("connectors", {})

    connector_defs = [
        ("gmail", "15m", "Gmail (email)"),
        ("calendar", "30m", "Google Calendar"),
        ("youtube", "1h", "YouTube"),
        ("spotify", "30m", "Spotify"),
        ("browser", "15m", "Browser history"),
    ]

    enabled_connectors: list[str] = []
    toml_lines = [
        "# Pulse connector configuration.",
        "# Secrets (API keys, tokens) go in .env, not here.",
        "",
    ]

    for name, default_interval, label in connector_defs:
        existing = connectors_config.get(name, {})
        was_enabled = existing.get("enabled", True) if existing else False
        interval = existing.get("poll_interval", default_interval)

        if existing:
            status = "enabled" if was_enabled else "disabled"
            answer = input(f"  {label}: {status}, poll {interval} — keep? [Y/n] ").strip().lower()
            if answer in ("n", "no"):
                yn = input(f"    Enable {label}? [Y/n] ").strip().lower()
                enabled = yn not in ("n", "no")
                new_interval = input(f"    Poll interval [{interval}]: ").strip()
                if new_interval:
                    interval = new_interval
            else:
                enabled = was_enabled
        else:
            yn = input(f"  Enable {label}? [Y/n] ").strip().lower()
            enabled = yn not in ("n", "no")
            if enabled:
                new_interval = input(f"    Poll interval [{interval}]: ").strip()
                if new_interval:
                    interval = new_interval

        toml_lines.append(f"[connectors.{name}]")
        toml_lines.append(f"enabled = {'true' if enabled else 'false'}")
        toml_lines.append(f'poll_interval = "{interval}"')

        if name == "spotify":
            supp = existing.get("supplementary_interval", "6h")
            toml_lines.append(f'supplementary_interval = "{supp}"')
        if name == "browser":
            browser_type = existing.get("browser", "chrome")
            if existing:
                answer = input(f"    Browser: {browser_type} — keep? [Y/n] ").strip().lower()
                if answer in ("n", "no"):
                    choice = input(f"    Browser type (chrome/firefox): ").strip()
                    browser_type = choice if choice else browser_type
            else:
                choice = input(f"    Browser type [{browser_type}]: ").strip()
                browser_type = choice if choice else browser_type
            toml_lines.append(f'browser = "{browser_type}"')

        toml_lines.append("")
        if enabled:
            enabled_connectors.append(name)

    toml_path.write_text("\n".join(toml_lines))
    print(f"\n  Saved {toml_path}")
    print(f"  Enabled: {', '.join(enabled_connectors) or 'none'}")

    # --- Step 4: OAuth flows ---
    google_connectors = [c for c in enabled_connectors if c in ("gmail", "calendar", "youtube")]
    has_google_creds = env_values.get("PULSE_GOOGLE_CLIENT_ID") and env_values.get("PULSE_GOOGLE_CLIENT_SECRET")
    has_spotify_creds = env_values.get("PULSE_SPOTIFY_CLIENT_ID") and env_values.get("PULSE_SPOTIFY_CLIENT_SECRET")

    # Check if tokens already exist
    data_dir = Path(env_values.get("PULSE_DATABASE_PATH", "data/pulse.db")).parent
    google_tokens = data_dir / "google_tokens.json"
    spotify_tokens = data_dir / "spotify_tokens.json"

    if google_connectors and has_google_creds:
        if google_tokens.exists():
            print(f"\n  Google: already authorized ({google_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_google()
        else:
            print(f"\n--- Google Authorization ---")
            print(f"  Connectors: {', '.join(google_connectors)}")
            answer = input("  Run Google OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_google()

    if "spotify" in enabled_connectors and has_spotify_creds:
        if spotify_tokens.exists():
            print(f"\n  Spotify: already authorized ({spotify_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_spotify()
        else:
            print(f"\n--- Spotify Authorization ---")
            answer = input("  Run Spotify OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_spotify()

    # --- Done ---
    print("\n=== Configuration Complete ===")
    print("Next steps:")
    print("  pulse init     — set up your profile and pull initial data")
    print("  pulse run      — start the server and scheduler")


def _init() -> None:
    from datetime import date, datetime
    from pulse.analysis.vault_memory import VaultMemory
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository
    from pulse.jobs.runners import run_aggregation_job

    _quiet_noisy_loggers()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    vault = VaultMemory(config.vault_path)

    # --- Step 1: User profile ---
    profile_path = Path(config.vault_path) / "04-Config" / "profile.md"
    if profile_path.exists():
        print(f"Profile already exists at {profile_path}")
        overwrite = input("Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("Keeping existing profile.")
        else:
            _collect_profile(vault)
    else:
        _collect_profile(vault)

    # --- Step 2: Initial data pull ---
    print("\n--- Initial Data Pull ---")
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

    registry = ConnectorRegistry()
    register_all(registry, config)
    asyncio.run(registry.build_active_connectors(config))

    active = registry.get_pull_connectors()
    if not active:
        print("No active connectors. Run 'pulse auth' first to set up credentials.")
    else:
        async def _run_pulls():
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                sync_state = SyncStateRepository(db)
                total_new = 0

                for connector, _cc in active:
                    source = connector.get_source_name()
                    print(f"  Pulling {source}...", end=" ", flush=True)
                    try:
                        events = await connector.pull(since=None)
                        if events:
                            new_count = await event_repo.upsert_events(events)
                            if hasattr(connector, "get_sync_timestamp"):
                                ts = connector.get_sync_timestamp()
                            else:
                                ts = max(e.timestamp for e in events)
                            await sync_state.save(source, ts.isoformat())
                            total_new += new_count
                            print(f"{new_count} new events")
                        else:
                            print("0 events")
                    except Exception as e:
                        print(f"ERROR: {e}")

                return total_new

        total = asyncio.run(_run_pulls())
        print(f"  Total: {total} new events collected")

    # --- Step 3: Aggregate ---
    print("\n--- Aggregating Stats ---")
    today = date.today()
    result = asyncio.run(run_aggregation_job(day=today, database_path=config.database_path))
    print(f"  {result.detail}")

    # --- Step 4: Initial discovery (if LLM available) ---
    from pulse.llm.factory import create_providers_from_config
    _, disc_llm = create_providers_from_config(config)

    if disc_llm is not None:
        print("\n--- Running Initial Discovery ---")
        from pulse.jobs.runners import run_discovery_job

        channel = None
        if config.telegram_bot_token and config.telegram_chat_id:
            from pulse.notifications.telegram import TelegramChannel
            channel = TelegramChannel(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
            )

        result = asyncio.run(run_discovery_job(
            cadence="weekly",
            target_date=today,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=disc_llm,
            notification_channel=channel,
        ))
        print(f"  {result.detail}")
    else:
        print("\nSkipping discovery (no LLM provider configured)")

    print("\nPulse initialized! Run 'pulse run' to start the server and scheduler.")


def _collect_profile(vault) -> None:
    print("\n--- User Profile Setup ---")
    print("This helps Pulse find patterns relevant to you.")
    print("Press Enter to skip any question.\n")

    name = input("Your name: ").strip()
    occupation = input("What do you do? (e.g., student, engineer, designer): ").strip()
    interests = input("Key interests (comma-separated): ").strip()
    goals = input("What patterns would you like Pulse to find? ").strip()
    context = input("Anything else Pulse should know about you? ").strip()

    lines = ["# User Profile", ""]
    if name:
        lines.append(f"**Name:** {name}")
    if occupation:
        lines.append(f"**Occupation:** {occupation}")
    if interests:
        lines.append(f"**Interests:** {interests}")
    lines.append("")

    if goals:
        lines.extend(["## Discovery Goals", goals, ""])
    if context:
        lines.extend(["## Additional Context", context, ""])

    profile_content = "\n".join(lines)
    vault.write_config_file("profile.md", profile_content)
    print(f"\nProfile saved!")


def _digest(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_daily_digest_job, run_aggregation_job
    from pulse.llm.factory import create_providers_from_config

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    print(f"Aggregating stats for {target.isoformat()}...")
    result = asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))
    print(f"  {result.detail}")

    summ_llm, _ = create_providers_from_config(config)

    print(f"Generating digest for {target.isoformat()}...")
    result = asyncio.run(run_daily_digest_job(
        day=target,
        database_path=config.database_path,
        vault_path=config.vault_path,
        llm=summ_llm,
    ))
    print(f"  {result.status}: {result.detail}")


def _discover(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_discovery_job, run_aggregation_job, JobResult
    from pulse.llm.factory import create_providers_from_config

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    _, disc_llm = create_providers_from_config(config)
    if disc_llm is None:
        print("Error: No LLM provider configured. Set [llm.discovery] in pulse.toml or PULSE_ANTHROPIC_API_KEY.")
        sys.exit(1)

    print(f"Aggregating stats for {target.isoformat()}...")
    asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))

    print(f"Running {args.cadence} discovery for {target.isoformat()}...")
    result = asyncio.run(run_discovery_job(
        cadence=args.cadence,
        target_date=target,
        database_path=config.database_path,
        vault_path=config.vault_path,
        llm=disc_llm,
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


def _insights() -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema
    from pulse.store.analytics import AnalyticsRepository

    config = load_config()

    if not Path(config.database_path).exists():
        print("No database found. Run 'pulse pull' first.")
        sys.exit(1)

    async def _show():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

            if not insights:
                print("No patterns discovered yet. Run 'pulse discover' first.")
                return

            print(f"Discovered patterns ({len(insights)}):\n")
            for i in insights:
                conf = i["confidence"]
                status = i["status"]
                print(f"  [{status:12}] {i['title']}")
                print(f"               confidence: {conf}, seen: {i['first_seen']} to {i['last_seen']}")
                print(f"               vault: {i['vault_path']}")
                print()

    asyncio.run(_show())


def _logs(args) -> None:
    import json as json_mod
    from datetime import UTC, datetime
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

    if not Path(config.database_path).exists():
        print("No database found. Run 'pulse pull' first.")
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
                print("No events found.")
                return

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
                print(f"  {ts_short}  {source:10} {etype:28} {detail}")

    asyncio.run(_show())


def _reset(args) -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

    config = load_config()

    if not Path(config.database_path).exists():
        print("No database found.")
        sys.exit(1)

    source = args.source

    async def _do_reset():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            sync_state = SyncStateRepository(db)

            if source is None:
                # Reset all cursors
                cur = await db.execute("SELECT source, cursor FROM connector_sync_state ORDER BY source")
                rows = await cur.fetchall()
                if not rows:
                    print("No sync cursors found.")
                    return

                print("Current cursors:")
                for s, c in rows:
                    print(f"  {s:10} {c}")

                confirm = input("\nReset ALL sync cursors? This will re-pull all data. [y/N] ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Cancelled.")
                    return

                await db.execute("DELETE FROM connector_sync_state")
                await db.commit()
                print(f"All {len(rows)} cursors cleared.")
            else:
                cursor = await sync_state.load(source)
                if not cursor:
                    print(f"No sync cursor found for '{source}'.")
                    return

                print(f"Current cursor for '{source}': {cursor}")
                confirm = input(f"Reset sync cursor for '{source}'? This will re-pull all data. [y/N] ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Cancelled.")
                    return

                await db.execute(
                    "DELETE FROM connector_sync_state WHERE source = ?",
                    (source,),
                )
                await db.commit()
                print(f"Cursor for '{source}' cleared. Next pull will fetch all data.")

    asyncio.run(_do_reset())


def _cleanup(args) -> None:
    from datetime import UTC, datetime
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

    if not Path(config.database_path).exists():
        print("No database found.")
        sys.exit(1)

    async def _do_cleanup():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)

            now_iso = datetime.now(UTC).isoformat()

            cur = await db.execute(
                "SELECT source, event_type, COUNT(*) FROM events "
                "WHERE timestamp > ? "
                "GROUP BY source, event_type ORDER BY COUNT(*) DESC",
                (now_iso,),
            )
            rows = await cur.fetchall()

            if not rows:
                print("No future-dated events found.")
                return

            total = sum(r[2] for r in rows)
            print(f"Found {total} events with timestamps in the future:")
            for source, etype, count in rows:
                print(f"  {source:10} {etype:28} {count:>6}")

            if args.dry_run:
                print("\nDry run — no changes made.")
                return

            confirm = input(f"\nDelete {total} future events? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cancelled.")
                return

            await db.execute(
                "DELETE FROM events WHERE timestamp > ?", (now_iso,)
            )
            await db.commit()
            print(f"Deleted {total} future-dated events.")

    asyncio.run(_do_cleanup())


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

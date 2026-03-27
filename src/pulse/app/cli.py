import argparse
import asyncio
import logging
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rich_argparse import RichHelpFormatter

from pulse.app import cli_ui as ui
from pulse.app.cli_ui import SITE_ACCENT, SITE_CREAM, SITE_MUTED_FG
from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import GoogleAuthManager, SCOPES_BY_CONNECTOR
from pulse.llm.anthropic_errors import user_message_for_anthropic_exception
from pulse.connectors.spotify_auth import SpotifyAuthManager, SPOTIFY_SCOPES, REDIRECT_URI

logger = logging.getLogger(__name__)


def _onboard_should_run_google_auth(config: PulseConfig) -> bool:
    if not config.google_client_id or not config.google_client_secret:
        return False
    google_connectors = [
        name
        for name in config.connectors
        if name in SCOPES_BY_CONNECTOR and config.connectors[name].enabled
    ]
    return bool(google_connectors)


def _onboard_should_run_spotify_auth(config: PulseConfig) -> bool:
    if not config.spotify_client_id or not config.spotify_client_secret:
        return False
    spot = config.connectors.get("spotify")
    return spot is not None and spot.enabled


def _onboard_print_prerequisites() -> None:
    ui.rule("Before you start")
    ui.muted_line("Run from the directory where .env and pulse.toml should live (usually the repo root).")
    ui.muted_line("Install the CLI first (e.g. pip install -e . or uv sync).")
    ui.muted_line("For Google or Spotify, create OAuth apps and have client IDs/secrets ready for .env.")
    ui.muted_line("Spotify OAuth uses a callback on localhost:8888 — keep that port free during auth.")


def _onboard_print_next_steps(host: str, port: int) -> None:
    ui.rule("Next steps")
    ui.muted_line("Starting the server — open the app in a browser on this machine:")
    ui.kv_line("URL", f"http://127.0.0.1:{port}/")
    if host not in ("127.0.0.1", "localhost"):
        ui.muted_line(f"Listen address is {host} — use your machine's IP or hostname if you browse from elsewhere.")
    ui.step("While Pulse is running")
    ui.muted_line("In another terminal: [cmd]pulse status[/]   [cmd]pulse insights[/]")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pulse",
        description=(
            f"[bold {SITE_ACCENT}]Pulse[/] — [{SITE_CREAM}]self-hosted personal intelligence[/] "
            f"[dim {SITE_MUTED_FG}](connectors · digests · insights)[/]"
        ),
        formatter_class=RichHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Start Pulse (API server + scheduler)")
    run_parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    run_parser.add_argument("--log-level", default="info", help="Log level (default: info)")

    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Configure, authorize, initialize, and run (Google/Spotify auth only when applicable)",
    )
    onboard_parser.add_argument("--host", default="0.0.0.0", help="Bind address for pulse run (default: 0.0.0.0)")
    onboard_parser.add_argument("--port", type=int, default=8000, help="Port for pulse run (default: 8000)")
    onboard_parser.add_argument("--log-level", default="info", help="Log level for pulse run (default: info)")
    onboard_parser.add_argument(
        "--strict",
        action="store_true",
        help="Always run pulse auth google and pulse auth spotify (exit if a step cannot run)",
    )
    onboard_parser.add_argument(
        "-f",
        "--profile-file",
        type=Path,
        default=None,
        help="Same as pulse init: read profile text from this file",
    )
    onboard_parser.add_argument(
        "--profile-text",
        default=None,
        metavar="TEXT",
        help="Same as pulse init: profile text (non-interactive)",
    )

    pull_parser = subparsers.add_parser("pull", help="Run pull cycle immediately")
    pull_parser.add_argument("sources", nargs="*", help="Connectors to pull (default: all)")

    digest_parser = subparsers.add_parser("digest", help="Run daily digest for a given day")
    digest_parser.add_argument("--date", default=None, help="Date to digest (YYYY-MM-DD, default: today)")

    discover_parser = subparsers.add_parser("discover", help="Run LLM discovery pass")
    discover_parser.add_argument("--cadence", default="daily", choices=["daily", "weekly", "monthly"])
    discover_parser.add_argument("--date", default=None, help="Target date (YYYY-MM-DD, default: today)")

    subparsers.add_parser("configure", help="Interactive setup for .env, connectors, and auth")
    init_parser = subparsers.add_parser("init", help="Set up profile and run initial data collection")
    init_parser.add_argument(
        "-f",
        "--profile-file",
        type=Path,
        default=None,
        help="Read free-form profile text from this file instead of interactive paste",
    )
    init_parser.add_argument(
        "--profile-text",
        default=None,
        metavar="TEXT",
        help="Free-form profile text (non-interactive; skips paste prompt)",
    )
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
    elif args.command == "onboard":
        _onboard(args)
    elif args.command == "pull":
        _pull(args)
    elif args.command == "digest":
        _digest(args)
    elif args.command == "discover":
        _discover(args)
    elif args.command == "configure":
        _configure(offer_oauth=True)
    elif args.command == "init":
        _init(
            profile_file=getattr(args, "profile_file", None),
            profile_text=getattr(args, "profile_text", None),
        )
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


def _onboard(args) -> None:
    """Interactive first-time setup: configure, OAuth, init, then `pulse run`."""
    ui.banner_tagline()
    ui.rule("pulse onboard")
    _onboard_print_prerequisites()
    _configure(offer_oauth=False)
    config = load_config()
    strict = args.strict

    ui.onboard_phase("auth google")
    if strict or _onboard_should_run_google_auth(config):
        _auth_google(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — no Google OAuth client in .env or no enabled Gmail / Calendar / YouTube connector."
        )

    ui.onboard_phase("auth spotify")
    if strict or _onboard_should_run_spotify_auth(config):
        _auth_spotify(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — Spotify client secrets missing, connector disabled, or spotify not in pulse.toml."
        )

    ui.onboard_phase("init")
    _init(
        profile_file=getattr(args, "profile_file", None),
        profile_text=getattr(args, "profile_text", None),
    )
    ui.onboard_phase("run")
    _onboard_print_next_steps(args.host, args.port)
    _run(args)


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

    ui.startup_panel(
        host=args.host,
        port=args.port,
        pull_names=", ".join(c.get_source_name() for c, _ in active_pull) or "none",
        push_names=", ".join(c.get_source_name() for c, _ in active_push) or "none",
        vault=str(config.vault_path),
        database=str(config.database_path),
    )

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


def _configure(*, offer_oauth: bool = True) -> None:
    import tomllib

    env_path = Path(".env")
    toml_path = Path("pulse.toml")

    ui.banner_tagline()
    ui.rule("Pulse configuration")

    # Load existing .env
    existing_env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                existing_env[key.strip()] = val.strip()

    # --- Step 1: Core settings ---
    ui.step("Step 1: Core settings")

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
    ui.step("Step 2: Service credentials")
    ui.muted_line("Leave blank to skip a service.")

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
    ui.success(f"Saved {env_path}")

    # --- Step 3: Connector config (pulse.toml) ---
    ui.step("Step 3: Connector configuration")

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
        ("feeds", "1h", "RSS/Atom feeds (URLs in pulse.toml)"),
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

        if name == "feeds":
            prev_urls: list = list(existing.get("urls", [])) if existing else []
            if isinstance(prev_urls, str):
                prev_urls = [prev_urls] if prev_urls else []
            if enabled:
                if prev_urls:
                    preview = ", ".join(prev_urls[:2]) + ("…" if len(prev_urls) > 2 else "")
                    keep = input(f"    Keep feed URLs ({preview})? [Y/n] ").strip().lower()
                    if keep in ("n", "no"):
                        prev_urls = []
                if not prev_urls:
                    line = input(
                        "    Feed URLs (comma-separated RSS/Atom URLs; leave empty to add later): "
                    ).strip()
                    prev_urls = [u.strip() for u in line.split(",") if u.strip()]
            escaped = [u.replace("\\", "\\\\").replace('"', '\\"') for u in prev_urls]
            if escaped:
                toml_lines.append("urls = [" + ", ".join(f'"{u}"' for u in escaped) + "]")
            else:
                toml_lines.append("urls = []")

        toml_lines.append("")
        if enabled:
            enabled_connectors.append(name)

    toml_path.write_text("\n".join(toml_lines))
    ui.success(f"Saved {toml_path}")
    ui.kv_line("Enabled", ", ".join(enabled_connectors) or "none")

    # --- Step 4: OAuth flows ---
    if offer_oauth:
        google_connectors = [c for c in enabled_connectors if c in ("gmail", "calendar", "youtube")]
        has_google_creds = env_values.get("PULSE_GOOGLE_CLIENT_ID") and env_values.get(
            "PULSE_GOOGLE_CLIENT_SECRET"
        )
        has_spotify_creds = env_values.get("PULSE_SPOTIFY_CLIENT_ID") and env_values.get(
            "PULSE_SPOTIFY_CLIENT_SECRET"
        )

        # Check if tokens already exist
        data_dir = Path(env_values.get("PULSE_DATABASE_PATH", "data/pulse.db")).parent
        google_tokens = data_dir / "google_tokens.json"
        spotify_tokens = data_dir / "spotify_tokens.json"

        if google_connectors and has_google_creds:
            if google_tokens.exists():
                ui.muted_line(f"Google: already authorized ({google_tokens})")
                answer = input("  Re-authorize? [y/N] ").strip().lower()
                if answer in ("y", "yes"):
                    _auth_google()
            else:
                ui.step("Google authorization")
                ui.kv_line("Connectors", ", ".join(google_connectors))
                answer = input("  Run Google OAuth now? [Y/n] ").strip().lower()
                if answer not in ("n", "no"):
                    _auth_google()

        if "spotify" in enabled_connectors and has_spotify_creds:
            if spotify_tokens.exists():
                ui.muted_line(f"Spotify: already authorized ({spotify_tokens})")
                answer = input("  Re-authorize? [y/N] ").strip().lower()
                if answer in ("y", "yes"):
                    _auth_spotify()
            else:
                ui.step("Spotify authorization")
                answer = input("  Run Spotify OAuth now? [Y/n] ").strip().lower()
                if answer not in ("n", "no"):
                    _auth_spotify()

    # --- Done ---
    ui.rule("Configuration complete")
    if offer_oauth:
        ui.say("[accent]Next steps[/]")
        ui.kv_line("Profile + first pull", "[cmd]pulse init[/]")
        ui.kv_line("Server + scheduler", "[cmd]pulse run[/]")


_PROFILE_STRUCTURE_MODEL = "claude-haiku-4-5-20251001"

_PROFILE_STRUCTURE_SYSTEM = """You format free-form text into a concise Obsidian markdown profile for Pulse, an app that analyzes the user's email, calendar, music, and browsing history.

Output ONLY the markdown document. No surrounding code fences, no preamble or explanation.

Use this shape when the user's text supports it (omit a **field** line or entire section if unknown):

# User Profile

**Name:** ...
**Occupation:** ...
**Interests:** ...

## Discovery goals

What patterns or themes they want Pulse to surface.

## Additional context

Other facts useful for personalization.

Rules:
- Preserve specifics from the user's text; do not invent biographical facts they did not imply.
- If the input is sparse, keep the file short rather than padding with guesses."""


def _read_profile_raw_text(*, profile_file: Path | None, profile_text: str | None) -> str:
    """Load free-form profile source: explicit args, then stdin if piped, else interactive paste."""
    if profile_text is not None:
        return profile_text.strip()
    if profile_file is not None:
        path = profile_file.expanduser()
        if not path.is_file():
            ui.error(f"Profile file not found: {path}")
            sys.exit(1)
        return path.read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    ui.say(
        "\n[accent]Paste[/] a free-form description of yourself [muted](role, interests, what you want Pulse to notice).[/]\n"
        "[muted]End input with Ctrl-D on a new line (macOS/Linux), or Ctrl-Z then Enter (Windows).[/]\n"
    )
    try:
        return sys.stdin.read().strip()
    except KeyboardInterrupt:
        ui.warning("Cancelled.")
        return ""


def _profile_markdown_without_llm(raw: str) -> str:
    """Wrap raw text when no LLM is configured."""
    return (
        "# User Profile\n\n"
        "## Self description\n\n"
        f"{raw.strip()}\n"
    )


def _strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


async def _structure_profile_markdown(raw: str, api_key: str) -> str:
    from pulse.llm.anthropic import AnthropicProvider

    llm = AnthropicProvider(api_key=api_key, model=_PROFILE_STRUCTURE_MODEL)
    structured = await llm.complete(
        f"The user wrote the following about themselves. Turn it into the vault profile markdown.\n\n---\n{raw}\n---",
        system_prompt=_PROFILE_STRUCTURE_SYSTEM,
        model=_PROFILE_STRUCTURE_MODEL,
    )
    return _strip_markdown_fences(structured)


def _init(
    *,
    profile_file: Path | None = None,
    profile_text: str | None = None,
) -> None:
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

    ui.rule("pulse init")

    # --- Step 1: User profile ---
    profile_path = Path(config.vault_path) / "04-Config" / "profile.md"
    if profile_path.exists():
        ui.warning(f"Profile already exists at [bold]{profile_path}[/]")
        overwrite = input("Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            ui.muted_line("Keeping existing profile.")
        else:
            _collect_profile(
                vault,
                config,
                profile_file=profile_file,
                profile_text=profile_text,
            )
    else:
        _collect_profile(
            vault,
            config,
            profile_file=profile_file,
            profile_text=profile_text,
        )

    # --- Step 2: Initial data pull ---
    ui.step("Initial data pull")
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)

    registry = ConnectorRegistry()
    register_all(registry, config)
    asyncio.run(registry.build_active_connectors(config))

    active = registry.get_pull_connectors()
    if not active:
        ui.warning("No active connectors. Run [cmd]pulse auth[/] first to set up credentials.")
    else:
        async def _run_pulls():
            async with connect_db(config.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                sync_state = SyncStateRepository(db)
                total_new = 0

                for connector, _cc in active:
                    source = connector.get_source_name()
                    ui.inline(f"  [bullet]●[/] [bold]{source}[/] … ", end="")
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
                            ui.say(f"[ok]{new_count}[/] new events")
                        else:
                            ui.say("[muted]0 events[/]")
                    except Exception as e:
                        ui.say(f"[err]ERROR:[/] {e}")

                return total_new

        total = asyncio.run(_run_pulls())
        ui.kv_line("Total new events", str(total))

    # --- Step 3: Aggregate ---
    ui.step("Aggregating stats")
    today = date.today()
    result = asyncio.run(run_aggregation_job(day=today, database_path=config.database_path))
    ui.muted_line(result.detail)

    # --- Step 4: Initial discovery (if LLM available) ---
    if config.anthropic_api_key:
        ui.step("Running initial discovery")
        from pulse.jobs.runners import run_discovery_job
        from pulse.llm.anthropic import AnthropicProvider

        llm = AnthropicProvider(api_key=config.anthropic_api_key)
        channel = None
        if config.telegram_bot_token and config.telegram_chat_id:
            from pulse.notifications.telegram import TelegramChannel
            channel = TelegramChannel(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
            )

        try:
            result = asyncio.run(
                run_discovery_job(
                    cadence="weekly",
                    target_date=today,
                    database_path=config.database_path,
                    vault_path=config.vault_path,
                    llm=llm,
                    notification_channel=channel,
                )
            )
        except Exception as e:
            um = user_message_for_anthropic_exception(e)
            if um:
                ui.error(um)
            else:
                ui.error(f"Initial discovery failed: {e}")
            raise SystemExit(1) from e
        ui.muted_line(result.detail)
    else:
        ui.muted_line("Skipping discovery (no PULSE_ANTHROPIC_API_KEY set).")

    ui.success("Pulse initialized! Run [cmd]pulse run[/] to start the server and scheduler.")


def _collect_profile(
    vault,
    config,
    *,
    profile_file: Path | None = None,
    profile_text: str | None = None,
) -> None:
    ui.step("User profile")
    ui.muted_line("Describe yourself in free form; Pulse will structure it for your vault.")

    raw = _read_profile_raw_text(profile_file=profile_file, profile_text=profile_text)
    if not raw:
        ui.warning("No profile text provided; skipping profile write.")
        return

    if config.anthropic_api_key:
        ui.say("[accent]Structuring profile[/] with the LLM…")
        try:
            profile_content = asyncio.run(
                _structure_profile_markdown(raw, config.anthropic_api_key)
            )
        except Exception as e:
            um = user_message_for_anthropic_exception(e)
            if um:
                ui.warning(f"{um} Saving raw text under a single section instead.")
            else:
                ui.warning(f"LLM error ({e}); saving raw text under a single section instead.")
            profile_content = _profile_markdown_without_llm(raw)
    else:
        ui.muted_line(
            "No PULSE_ANTHROPIC_API_KEY; saving your text under “Self description” (no LLM pass)."
        )
        profile_content = _profile_markdown_without_llm(raw)

    vault.write_config_file("profile.md", profile_content)
    ui.success("Profile saved.")


def _digest(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_daily_digest_job, run_aggregation_job

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    ui.rule("pulse digest")
    ui.say(f"[accent]Aggregating stats[/] for [bold]{target.isoformat()}[/]…")
    result = asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))
    ui.muted_line(result.detail)

    ui.say(f"[accent]Generating digest[/] for [bold]{target.isoformat()}[/]…")
    result = asyncio.run(run_daily_digest_job(
        day=target,
        database_path=config.database_path,
        vault_path=config.vault_path,
    ))
    ui.say(f"[bold]{result.status}[/]: {result.detail}")


def _discover(args) -> None:
    from datetime import date
    from pulse.jobs.runners import run_discovery_job, run_aggregation_job
    from pulse.llm.anthropic import AnthropicProvider

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    if not config.anthropic_api_key:
        ui.error("PULSE_ANTHROPIC_API_KEY must be set for discovery.")
        sys.exit(1)

    llm = AnthropicProvider(api_key=config.anthropic_api_key)

    ui.rule("pulse discover")
    ui.say(f"[accent]Aggregating stats[/] for [bold]{target.isoformat()}[/]…")
    asyncio.run(run_aggregation_job(day=target, database_path=config.database_path))

    ui.say(
        f"[accent]Running {args.cadence} discovery[/] for [bold]{target.isoformat()}[/]…"
    )
    try:
        result = asyncio.run(
            run_discovery_job(
                cadence=args.cadence,
                target_date=target,
                database_path=config.database_path,
                vault_path=config.vault_path,
                llm=llm,
            )
        )
    except Exception as e:
        um = user_message_for_anthropic_exception(e)
        if um:
            ui.error(um)
        else:
            ui.error(f"Discovery failed: {e}")
        raise SystemExit(1) from e
    ui.say(f"[bold]{result.status}[/]: {result.detail}")


def _status() -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

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

            cur4 = await db.execute("SELECT source, cursor, updated_at FROM connector_sync_state ORDER BY source")
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


def _insights() -> None:
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema
    from pulse.store.analytics import AnalyticsRepository

    config = load_config()

    if not Path(config.database_path).exists():
        ui.error("No database found. Run [cmd]pulse pull[/] first.")
        sys.exit(1)

    async def _show():
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

            ui.rule("pulse insights")
            if not insights:
                ui.warning("No patterns discovered yet. Run [cmd]pulse discover[/] first.")
                return

            ui.say(f"[accent]Discovered patterns[/] [bold]({len(insights)})[/]\n")
            ui.insights_panel(insights)

    asyncio.run(_show())


def _logs(args) -> None:
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


def _reset(args) -> None:
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
                cur = await db.execute("SELECT source, cursor FROM connector_sync_state ORDER BY source")
                rows = await cur.fetchall()
                if not rows:
                    ui.muted_line("No sync cursors found.")
                    return

                ui.say("[accent]Current cursors[/]")
                for s, c in rows:
                    ui.kv_line(str(s), str(c))

                confirm = input("\nReset ALL sync cursors? This will re-pull all data. [y/N] ").strip().lower()
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
                confirm = input(f"Reset sync cursor for '{source}'? This will re-pull all data. [y/N] ").strip().lower()
                if confirm not in ("y", "yes"):
                    ui.warning("Cancelled.")
                    return

                await db.execute(
                    "DELETE FROM connector_sync_state WHERE source = ?",
                    (source,),
                )
                await db.commit()
                ui.success(f"Cursor for '{source}' cleared. Next pull will fetch all data.")

    asyncio.run(_do_reset())


def _cleanup(args) -> None:
    from datetime import UTC, datetime
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    config = load_config()

    if not Path(config.database_path).exists():
        ui.error("No database found.")
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

            ui.rule("pulse cleanup")
            if not rows:
                ui.muted_line("No future-dated events found.")
                return

            total = sum(r[2] for r in rows)
            ui.warning(f"Found [bold]{total}[/] events with timestamps in the future:")
            for source, etype, count in rows:
                ui.kv_line(f"{source} / {etype}", str(count))

            if args.dry_run:
                ui.muted_line("Dry run — no changes made.")
                return

            confirm = input(f"\nDelete {total} future events? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                ui.warning("Cancelled.")
                return

            await db.execute(
                "DELETE FROM events WHERE timestamp > ?", (now_iso,)
            )
            await db.commit()
            ui.success(f"Deleted {total} future-dated events.")

    asyncio.run(_do_cleanup())


def _test_telegram() -> None:
    from pulse.notifications.telegram import TelegramChannel
    from pulse.domain.notifications import Notification

    config = load_config()

    if not config.telegram_bot_token or not config.telegram_chat_id:
        ui.error("PULSE_TELEGRAM_BOT_TOKEN and PULSE_TELEGRAM_CHAT_ID must be set in .env")
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
        ui.success("Test message sent! Check your Telegram.")
    except Exception as e:
        ui.error(f"Failed to send: {e}")
        sys.exit(1)


def _auth_google(*, show_rule: bool = True) -> None:
    config = load_config()

    if not config.google_client_id or not config.google_client_secret:
        ui.error("PULSE_GOOGLE_CLIENT_ID and PULSE_GOOGLE_CLIENT_SECRET must be set.")
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
        ui.error("No Google connectors enabled in pulse.toml. Enable gmail, calendar, or youtube.")
        sys.exit(1)

    scopes = auth_manager.get_required_scopes(google_connectors)
    if show_rule:
        ui.rule("pulse auth google")
    ui.kv_line("Authorizing for", ", ".join(google_connectors))
    ui.muted_line("Scopes: " + ", ".join(scopes))

    auth_manager.authorize(scopes)
    ui.success("Google authorization complete!")


def _auth_spotify(*, show_rule: bool = True) -> None:
    config = load_config()

    if not config.spotify_client_id or not config.spotify_client_secret:
        ui.error("PULSE_SPOTIFY_CLIENT_ID and PULSE_SPOTIFY_CLIENT_SECRET must be set.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "spotify_tokens.json"
    auth_manager = SpotifyAuthManager(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        token_path=token_path,
    )

    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(SPOTIFY_SCOPES, state)

    if show_rule:
        ui.rule("pulse auth spotify")
    ui.say("[accent]Opening browser[/] for Spotify authorization…")
    ui.muted_line(f"If it doesn't open, visit: {auth_url}")
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
        ui.error("No authorization code received.")
        sys.exit(1)

    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("Spotify authorization complete!")

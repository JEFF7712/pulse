import argparse
import asyncio
import logging
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from rich_argparse import RichHelpFormatter

from pulse.app import cli_ui as ui
from pulse.app.cli_ui import SITE_ACCENT, SITE_CREAM, SITE_MUTED_FG
from pulse.app.config import PulseConfig
from pulse.app.config_loader import PulseConfigNotFoundError, default_pulse_config_path, load_config
from pulse.app.paths import PulsePaths, resolve_pulse_paths
from pulse.connectors.github_auth import (
    GITHUB_AUTH_PORT,
    GITHUB_SCOPES,
    GitHubAuthManager,
)
from pulse.connectors.gitlab_auth import (
    GITLAB_AUTH_PORT,
    GITLAB_SCOPES,
    GitLabAuthManager,
)
from pulse.connectors.google_auth import SCOPES_BY_CONNECTOR, GoogleAuthManager
from pulse.connectors.microsoft_auth import MICROSOFT_AUTH_PORT, MicrosoftAuthManager
from pulse.connectors.oura_auth import (
    OURA_AUTH_PORT,
    OURA_SCOPES,
    OuraAuthManager,
)
from pulse.connectors.plaid_link import run_plaid_link_flow
from pulse.connectors.spotify_auth import (
    REDIRECT_URI,
    SPOTIFY_SCOPES,
    SpotifyAuthManager,
)
from pulse.llm.anthropic_errors import user_message_for_anthropic_exception

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


def _onboard_should_run_microsoft_auth(config: PulseConfig) -> bool:
    if not config.microsoft_client_id or not config.microsoft_client_secret:
        return False
    for name in ("microsoft_mail", "microsoft_calendar"):
        cc = config.connectors.get(name)
        if cc is not None and cc.enabled:
            return True
    return False


def _onboard_should_run_github_auth(config: PulseConfig) -> bool:
    if not config.github_client_id or not config.github_client_secret:
        return False
    gh = config.connectors.get("github")
    return gh is not None and gh.enabled


def _onboard_should_run_gitlab_auth(config: PulseConfig) -> bool:
    gl = config.connectors.get("gitlab")
    if gl is None or not gl.enabled:
        return False
    if config.gitlab_token:
        return False
    return bool(config.gitlab_client_id and config.gitlab_client_secret)


def _onboard_should_run_plaid_link(config: PulseConfig) -> bool:
    if not config.plaid_client_id or not config.plaid_secret:
        return False
    pl = config.connectors.get("plaid")
    return pl is not None and pl.enabled


def _onboard_should_run_oura_auth(config: PulseConfig) -> bool:
    if (config.oura_personal_access_token or "").strip():
        return False
    if not config.oura_client_id or not config.oura_client_secret:
        return False
    ou = config.connectors.get("oura")
    return ou is not None and ou.enabled


def _gitlab_base_url(config: PulseConfig) -> str:
    cc = config.connectors.get("gitlab")
    if cc is None:
        return "https://gitlab.com"
    u = cc.model_dump(mode="python").get("gitlab_base_url")
    if isinstance(u, str) and u.strip():
        return u.strip().rstrip("/")
    return "https://gitlab.com"


def _onboard_print_prerequisites() -> None:
    ui.rule("Before you start")
    ui.muted_line(
        "Run from the directory where your Pulse config lives (usually ``.config/pulse.toml`` or repo-root ``pulse.toml``)."
    )
    ui.muted_line("Install the CLI first (e.g. pip install -e . or uv sync).")
    ui.muted_line(
        "For Google, Spotify, Microsoft, GitHub, or GitLab, create OAuth apps as needed."
    )
    ui.muted_line(
        "Local callbacks: Spotify :8888, Microsoft :8890, GitHub :8891, GitLab :8892, Plaid Link :8893, Oura :8894."
    )


def _onboard_print_next_steps(host: str, port: int) -> None:
    ui.rule("Next steps")
    ui.muted_line("Starting the server — open the app in a browser on this machine:")
    ui.kv_line("URL", f"http://127.0.0.1:{port}/")
    if host not in ("127.0.0.1", "localhost"):
        ui.muted_line(
            f"Listen address is {host} — use your machine's IP or hostname if you browse from elsewhere."
        )
    ui.step("While Pulse is running")
    ui.muted_line("In another terminal: [cmd]pulse status[/]   [cmd]pulse insights[/]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulse",
        description=(
            f"[bold {SITE_ACCENT}]Pulse[/] — [{SITE_CREAM}]self-hosted personal intelligence[/] "
            f"[dim {SITE_MUTED_FG}](connectors · insights)[/]"
        ),
        formatter_class=RichHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Shared parent parser for --config-dir
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing pulse.toml",
    )

    run_parser = subparsers.add_parser(
        "run",
        parents=[config_parent],
        help="Start FastAPI server, scheduler, and operator web UI",
    )
    run_parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    run_parser.add_argument(
        "--port", type=int, default=8000, help="Port (default: 8000)"
    )
    run_parser.add_argument(
        "--log-level", default="info", help="Log level (default: info)"
    )

    onboard_parser = subparsers.add_parser(
        "onboard",
        parents=[config_parent],
        help=(
            "First-run pipeline: full configure wizard, connector OAuth when applicable, "
            "pulse init, then pulse run"
        ),
    )
    onboard_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address for pulse run (default: 0.0.0.0)",
    )
    onboard_parser.add_argument(
        "--port", type=int, default=8000, help="Port for pulse run (default: 8000)"
    )
    onboard_parser.add_argument(
        "--log-level", default="info", help="Log level for pulse run (default: info)"
    )
    onboard_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Always run every onboard auth/link step that applies (Google, Spotify, Microsoft, "
            "GitHub, GitLab, Plaid, Oura); exit non-zero if a required step fails"
        ),
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

    pull_parser = subparsers.add_parser(
        "pull", parents=[config_parent], help="Run connector pull jobs now (omit sources to pull all enabled)"
    )
    pull_parser.add_argument(
        "sources", nargs="*", help="Connectors to pull (default: all)"
    )

    discover_parser = subparsers.add_parser(
        "discover",
        parents=[config_parent],
        help="Run LLM discovery pass (scheduled jobs use daily cadence only)",
    )
    discover_parser.add_argument(
        "--cadence",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Discovery cadence (default: daily)",
    )
    discover_parser.add_argument(
        "--date",
        default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )

    subparsers.add_parser(
        "configure",
        parents=[config_parent],
        help=(
            "Interactive setup: core, connectors, notifications, model API keys, "
            "[llm] roles in pulse.toml, full wizard"
        ),
    )
    init_parser = subparsers.add_parser(
        "init",
        parents=[config_parent],
        help="Structure vault profile (optional LLM) and run initial connector pulls",
    )
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
    subparsers.add_parser(
        "status", parents=[config_parent], help="Show database paths, counts, and connector snapshot"
    )
    subparsers.add_parser(
        "insights", parents=[config_parent], help="List stored discovery patterns (from the database)"
    )
    subparsers.add_parser(
        "test-telegram",
        parents=[config_parent],
        help="Send one Telegram test message (requires Telegram settings in pulse.toml or env)",
    )

    reset_parser = subparsers.add_parser(
        "reset",
        parents=[config_parent],
        help="Clear connector sync cursors so the next pull re-fetches from scratch",
    )
    reset_parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Connector source name (e.g., gmail, browser), or omit for all",
    )

    logs_parser = subparsers.add_parser(
        "logs", parents=[config_parent], help="Print recent rows from the event store (newest first)"
    )
    logs_parser.add_argument("--source", default=None, help="Filter by source")
    logs_parser.add_argument(
        "-n", type=int, default=20, help="Number of events (default: 20)"
    )
    logs_parser.add_argument(
        "--all", action="store_true", help="Include future events (excluded by default)"
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        _run(args)
    elif args.command == "onboard":
        _onboard(args)
    elif args.command == "pull":
        _pull(args)
    elif args.command == "discover":
        _discover(args)
    elif args.command == "configure":
        _configure(offer_oauth=True, config_dir=getattr(args, "config_dir", None))
    elif args.command == "init":
        _init(
            profile_file=getattr(args, "profile_file", None),
            profile_text=getattr(args, "profile_text", None),
            config_dir=getattr(args, "config_dir", None),
        )
    elif args.command == "status":
        _status(config_dir=getattr(args, "config_dir", None))
    elif args.command == "insights":
        _insights()
    elif args.command == "logs":
        _logs(args)
    elif args.command == "reset":
        _reset(args)
    elif args.command == "test-telegram":
        _test_telegram()
    else:
        parser.print_help()
        sys.exit(1)


def _onboard(args) -> None:
    """Interactive first-time setup: configure (same hub menus as ``pulse configure``), OAuth, init, then `pulse run`."""
    ui.banner_tagline()
    ui.rule("pulse onboard")
    _onboard_print_prerequisites()
    config_dir = getattr(args, "config_dir", None)
    _configure(
        offer_oauth=False,
        menu_walkthrough=True,
        suppress_banner=True,
        submenu_exit_label="→ Next",
        config_dir=config_dir,
    )
    config = load_config(config_dir=config_dir)
    strict = args.strict

    ui.onboard_phase("auth google")
    if strict or _onboard_should_run_google_auth(config):
        _auth_google(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — no Google OAuth client configured or no enabled Gmail / Calendar / YouTube connector."
        )

    ui.onboard_phase("auth spotify")
    if strict or _onboard_should_run_spotify_auth(config):
        _auth_spotify(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — Spotify client secrets missing, connector disabled, or spotify not in pulse.toml."
        )

    ui.onboard_phase("auth microsoft")
    if strict or _onboard_should_run_microsoft_auth(config):
        _auth_microsoft(show_rule=False)
    else:
        ui.muted_line("Skipping — Microsoft 365 OAuth not needed or not configured.")

    ui.onboard_phase("auth github")
    if strict or _onboard_should_run_github_auth(config):
        _auth_github(show_rule=False)
    else:
        ui.muted_line("Skipping — GitHub OAuth not needed or not configured.")

    ui.onboard_phase("auth gitlab")
    if strict or _onboard_should_run_gitlab_auth(config):
        _auth_gitlab(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — GitLab OAuth not needed, PAT in use, or not configured."
        )

    ui.onboard_phase("plaid link")
    if strict or _onboard_should_run_plaid_link(config):
        token_path = Path(config.database_path).parent / "plaid_tokens.json"
        if not token_path.exists():
            try:
                _auth_plaid(show_rule=False)
            except RuntimeError as e:
                ui.error(str(e))
                if strict:
                    sys.exit(1)
        else:
            ui.muted_line(f"Plaid already linked ({token_path}); skipping Link.")
    else:
        ui.muted_line("Skipping — Plaid not enabled or credentials missing.")

    ui.onboard_phase("auth oura")
    if _onboard_should_run_oura_auth(config):
        token_path = Path(config.database_path).parent / "oura_tokens.json"
        if not token_path.exists():
            _auth_oura(show_rule=False)
        else:
            ui.muted_line(f"Oura already authorized ({token_path}); skipping.")
    else:
        ui.muted_line(
            "Skipping — Oura not enabled, using PAT, or OAuth client not configured."
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


def _prompt_env_field(
    key: str, label: str, current: str, is_secret: bool = False
) -> str:
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


# Core paths & timezone — one submenu row each in `pulse configure` → Core settings.
_CORE_SETTING_DEFS: list[tuple[str, str, str, list[tuple[str, str, str, bool]]]] = [
    (
        "database",
        "Database",
        "🗄️",
        [
            ("PULSE_DATABASE_PATH", "Database path", "data/pulse.db", False),
        ],
    ),
    (
        "vault",
        "Obsidian vault",
        "📓",
        [
            ("PULSE_VAULT_PATH", "Obsidian vault path", "Pulse-Vault", False),
        ],
    ),
    (
        "timezone",
        "Timezone",
        "🌍",
        [
            ("PULSE_TIMEZONE", "Timezone (e.g., America/Chicago)", "UTC", False),
        ],
    ),
]

# Flat list for full wizard core pass and pulse.toml root emit order in configure.
_CONFIGURE_CORE_FIELDS: list[tuple[str, str, str, bool]] = [
    fld for *_, flds in _CORE_SETTING_DEFS for fld in flds
]

# Flat list for full wizard “integrations” pass. Per-connector menus reuse the same keys
# via _CONNECTOR_ENV_FIELDS (intentional overlap — connector flow is scoped per source).
_CONFIGURE_INTEGRATION_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_GOOGLE_CLIENT_ID", "Google Client ID", True),
    ("PULSE_GOOGLE_CLIENT_SECRET", "Google Client Secret", True),
    ("PULSE_SPOTIFY_CLIENT_ID", "Spotify Client ID", True),
    ("PULSE_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", True),
    ("PULSE_MICROSOFT_CLIENT_ID", "Microsoft / Azure app Client ID", True),
    ("PULSE_MICROSOFT_CLIENT_SECRET", "Microsoft / Azure app Client Secret", True),
    ("PULSE_MICROSOFT_TENANT_ID", "Microsoft tenant (blank = common)", False),
    ("PULSE_GITHUB_CLIENT_ID", "GitHub OAuth Client ID", True),
    ("PULSE_GITHUB_CLIENT_SECRET", "GitHub OAuth Client Secret", True),
    ("PULSE_GITLAB_CLIENT_ID", "GitLab OAuth Application ID", True),
    ("PULSE_GITLAB_CLIENT_SECRET", "GitLab OAuth Secret", True),
    ("PULSE_GITLAB_TOKEN", "GitLab personal access token (optional)", True),
    ("PULSE_PLAID_CLIENT_ID", "Plaid client ID", True),
    ("PULSE_PLAID_SECRET", "Plaid secret", True),
    ("PULSE_PLAID_ENV", "Plaid environment (sandbox or production)", False),
    ("PULSE_OURA_CLIENT_ID", "Oura OAuth client ID (optional)", True),
    ("PULSE_OURA_CLIENT_SECRET", "Oura OAuth client secret (optional)", True),
    (
        "PULSE_OURA_PERSONAL_ACCESS_TOKEN",
        "Oura personal access token (optional; skips OAuth if set)",
        True,
    ),
    ("PULSE_NOTION_TOKEN", "Notion integration secret (internal integration)", True),
    ("PULSE_LINEAR_API_KEY", "Linear personal API key (assigned issues)", True),
]

# LLM vendor API keys (see pulse.llm.factory — also ``anthropic_api_key`` / ``PULSE_ANTHROPIC_API_KEY`` in TOML or env).
_MODEL_PROVIDER_DEFS: list[tuple[str, str, str, list[tuple[str, str, bool]]]] = [
    (
        "anthropic",
        "Anthropic",
        "🅰️",
        [
            (
                "ANTHROPIC_API_KEY",
                "Anthropic API key ([llm.*] provider = anthropic; or pulse.toml anthropic_api_key)",
                True,
            ),
            (
                "PULSE_ANTHROPIC_API_KEY",
                "Same key as ANTHROPIC_API_KEY (TOML / env alias)",
                True,
            ),
        ],
    ),
    (
        "openai",
        "OpenAI / compatible",
        "🧠",
        [
            (
                "OPENAI_API_KEY",
                "OpenAI API key (OpenAI, Azure OpenAI-compatible, or optional for Ollama)",
                True,
            ),
        ],
    ),
    (
        "gemini",
        "Google Gemini",
        "✨",
        [
            ("GEMINI_API_KEY", "Gemini API key ([llm.*] provider = gemini)", True),
        ],
    ),
    (
        "ollama",
        "Ollama (local)",
        "🦙",
        [],
    ),
]

_CONFIGURE_MODEL_PROVIDER_FIELDS: list[tuple[str, str, bool]] = [
    fld for *_, flds in _MODEL_PROVIDER_DEFS for fld in flds
]

# Per-provider notification / webhook keys (order preserved for full wizard + pulse.toml key order).
_NOTIFICATION_PROVIDER_DEFS: list[tuple[str, str, str, list[tuple[str, str, bool]]]] = [
    (
        "telegram",
        "Telegram",
        "📱",
        [
            ("PULSE_TELEGRAM_BOT_TOKEN", "Telegram Bot Token", True),
            ("PULSE_TELEGRAM_CHAT_ID", "Telegram Chat ID", False),
        ],
    ),
    (
        "corrections",
        "Corrections API",
        "🛠️",
        [
            (
                "PULSE_CORRECTIONS_WEBHOOK_SECRET",
                "Corrections webhook secret (optional; enables POST /webhooks/corrections)",
                True,
            ),
        ],
    ),
    (
        "ntfy",
        "ntfy",
        "🔔",
        [
            ("PULSE_NTFY_TOPIC", "ntfy topic (optional; leave blank to skip)", False),
            (
                "PULSE_NTFY_BASE_URL",
                "ntfy server base URL (optional; blank uses https://ntfy.sh)",
                False,
            ),
        ],
    ),
    (
        "webhook",
        "JSON webhook",
        "🔗",
        [
            (
                "PULSE_NOTIFICATION_WEBHOOK_URL",
                "Notification webhook URL (optional JSON POST)",
                False,
            ),
        ],
    ),
    (
        "discord",
        "Discord",
        "🎮",
        [
            ("PULSE_DISCORD_WEBHOOK_URL", "Discord incoming webhook URL (optional)", False),
        ],
    ),
    (
        "slack",
        "Slack",
        "💬",
        [
            ("PULSE_SLACK_WEBHOOK_URL", "Slack incoming webhook URL (optional)", False),
        ],
    ),
    (
        "pushover",
        "Pushover",
        "📲",
        [
            (
                "PULSE_PUSHOVER_USER_KEY",
                "Pushover user key (optional; needs API token too)",
                False,
            ),
            ("PULSE_PUSHOVER_API_TOKEN", "Pushover application API token", True),
        ],
    ),
    (
        "gotify",
        "Gotify",
        "📮",
        [
            (
                "PULSE_GOTIFY_URL",
                "Gotify server URL (optional; e.g. https://gotify.example.com)",
                False,
            ),
            ("PULSE_GOTIFY_APP_TOKEN", "Gotify application token", True),
        ],
    ),
    (
        "smtp",
        "SMTP email",
        "✉️",
        [
            ("PULSE_SMTP_HOST", "SMTP host (optional)", False),
            ("PULSE_SMTP_PORT", "SMTP port", False),
            ("PULSE_SMTP_USER", "SMTP username (optional)", False),
            ("PULSE_SMTP_PASSWORD", "SMTP password (optional)", True),
            ("PULSE_SMTP_USE_TLS", "SMTP STARTTLS after connect (true/false)", False),
            ("PULSE_SMTP_USE_SSL", "SMTP implicit SSL (true/false)", False),
            ("PULSE_SMTP_FROM", "SMTP From address (optional)", False),
            (
                "PULSE_SMTP_TO",
                "SMTP To address(es), comma-separated (optional)",
                False,
            ),
        ],
    ),
    (
        "companion",
        "Companion / FCM",
        "🤝",
        [
            (
                "PULSE_COMPANION_TOKEN",
                "Companion API bearer token (POST /webhooks/companion)",
                True,
            ),
            (
                "PULSE_FCM_SERVICE_ACCOUNT_PATH",
                "Path to Firebase service account JSON (FCM push)",
                False,
            ),
        ],
    ),
]

_CONFIGURE_NOTIFICATION_FIELDS: list[tuple[str, str, bool]] = [
    fld for *_, flds in _NOTIFICATION_PROVIDER_DEFS for fld in flds
]

_CONFIGURE_ENV_KEY_ORDER: list[str] = (
    [t[0] for t in _CONFIGURE_CORE_FIELDS]
    + [t[0] for t in _CONFIGURE_INTEGRATION_FIELDS]
    + [t[0] for t in _CONFIGURE_MODEL_PROVIDER_FIELDS]
    + [t[0] for t in _CONFIGURE_NOTIFICATION_FIELDS]
)

# Map configure / model-provider env keys to ``PulseConfig`` root field names (pulse.toml).
_ENV_KEY_TO_CONFIG_FIELD: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "PULSE_ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
}

_PULSE_ROOT_FIELD_NAMES: frozenset[str] = frozenset(
    k for k in PulseConfig.model_fields if k not in ("connectors", "llm")
)

_CONNECTOR_DEFS: list[tuple[str, str, str]] = [
    ("gmail", "15m", "Gmail (email)"),
    ("calendar", "30m", "Google Calendar"),
    ("youtube", "1h", "YouTube"),
    ("spotify", "30m", "Spotify"),
    ("microsoft_mail", "15m", "Microsoft 365 mail (Outlook)"),
    ("microsoft_calendar", "30m", "Microsoft 365 calendar"),
    ("github", "30m", "GitHub activity"),
    ("linear", "30m", "Linear (issues assigned to you)"),
    ("gitlab", "30m", "GitLab activity"),
    ("plaid", "6h", "Plaid bank transactions"),
    ("browser", "15m", "Browser history"),
    ("feeds", "1h", "RSS/Atom feeds (URLs in pulse.toml)"),
    ("notion", "45m", "Notion (pages shared with your integration)"),
    ("oura", "6h", "Oura Ring (sleep & readiness)"),
]

_CONNECTOR_MENU_EMOJI: dict[str, str] = {
    "gmail": "📧",
    "calendar": "📅",
    "youtube": "▶️",
    "spotify": "🎵",
    "microsoft_mail": "✉️",
    "microsoft_calendar": "📆",
    "github": "🐙",
    "linear": "⚡",
    "gitlab": "🦊",
    "plaid": "🏦",
    "browser": "🌍",
    "feeds": "📡",
    "notion": "📓",
    "oura": "💍",
}

_CONNECTOR_MENU_SHORT: dict[str, str] = {
    "gmail": "Gmail",
    "calendar": "G Cal",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "microsoft_mail": "Outlook",
    "microsoft_calendar": "365 Cal",
    "github": "GitHub",
    "linear": "Linear",
    "gitlab": "GitLab",
    "plaid": "Plaid",
    "browser": "Browser",
    "feeds": "Feeds",
    "notion": "Notion",
    "oura": "Oura",
}

_GOOGLE_ENV_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_GOOGLE_CLIENT_ID", "Google Client ID", True),
    ("PULSE_GOOGLE_CLIENT_SECRET", "Google Client Secret", True),
]
_MS_ENV_FIELDS: list[tuple[str, str, bool]] = [
    ("PULSE_MICROSOFT_CLIENT_ID", "Microsoft / Azure app Client ID", True),
    ("PULSE_MICROSOFT_CLIENT_SECRET", "Microsoft / Azure app Client Secret", True),
    ("PULSE_MICROSOFT_TENANT_ID", "Microsoft tenant (blank = common)", False),
]

_CONNECTOR_ENV_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "gmail": _GOOGLE_ENV_FIELDS,
    "calendar": _GOOGLE_ENV_FIELDS,
    "youtube": _GOOGLE_ENV_FIELDS,
    "spotify": [
        ("PULSE_SPOTIFY_CLIENT_ID", "Spotify Client ID", True),
        ("PULSE_SPOTIFY_CLIENT_SECRET", "Spotify Client Secret", True),
    ],
    "microsoft_mail": _MS_ENV_FIELDS,
    "microsoft_calendar": _MS_ENV_FIELDS,
    "github": [
        ("PULSE_GITHUB_CLIENT_ID", "GitHub OAuth Client ID", True),
        ("PULSE_GITHUB_CLIENT_SECRET", "GitHub OAuth Client Secret", True),
    ],
    "gitlab": [
        ("PULSE_GITLAB_CLIENT_ID", "GitLab OAuth Application ID", True),
        ("PULSE_GITLAB_CLIENT_SECRET", "GitLab OAuth Secret", True),
        ("PULSE_GITLAB_TOKEN", "GitLab personal access token (optional)", True),
    ],
    "plaid": [
        ("PULSE_PLAID_CLIENT_ID", "Plaid client ID", True),
        ("PULSE_PLAID_SECRET", "Plaid secret", True),
        ("PULSE_PLAID_ENV", "Plaid environment (sandbox or production)", False),
    ],
    "oura": [
        ("PULSE_OURA_CLIENT_ID", "Oura OAuth client ID (optional)", True),
        ("PULSE_OURA_CLIENT_SECRET", "Oura OAuth client secret (optional)", True),
        (
            "PULSE_OURA_PERSONAL_ACCESS_TOKEN",
            "Oura personal access token (optional; skips OAuth if set)",
            True,
        ),
    ],
    "notion": [
        ("PULSE_NOTION_TOKEN", "Notion integration secret (internal integration)", True),
    ],
    "linear": [("PULSE_LINEAR_API_KEY", "Linear personal API key (assigned issues)", True)],
}

_CONFIGURE_MENU_ITEMS: list[tuple[str, str]] = [
    ("core", "⚙️ Core settings (paths, timezone)"),
    (
        "connectors",
        "🔌 Connectors (pulse.toml credentials + blocks, OAuth / Plaid / Oura when needed)",
    ),
    (
        "notifications",
        "🔔 Notifications (Telegram, SMTP, webhooks, companion/FCM, …)",
    ),
    (
        "model",
        "🧠 Model (provider API keys + [llm] provider & summarization / discovery models)",
    ),
    ("full", "✨ Full wizard (all of the above)"),
    ("done", "✅ Done"),
]

# Submenu under `pulse configure` → Model (API keys vs [llm] roles).
_MODEL_HUB_ITEMS: list[tuple[str, str]] = [
    ("api_keys", "🔑 Provider API keys (Anthropic, OpenAI, Gemini, Ollama …)"),
    (
        "llm_roles",
        "💬 LLM in pulse.toml (provider + summarization & discovery models)",
    ),
]

# Main configure areas in walkthrough order (excludes Full wizard & Done) — e.g. `pulse onboard`.
_CONFIGURE_SEQUENTIAL_ORDER: tuple[str, ...] = (
    "core",
    "connectors",
    "notifications",
    "model",
)

_CONFIGURE_SECTION_BANNER: dict[str, str] = {
    "core": "Core settings",
    "connectors": "Connectors",
    "notifications": "Notifications",
    "model": "Model",
}


def _pick_configure_menu_action() -> str:
    """Return menu action key, or ``__invalid__`` for bad numeric fallback input."""
    non_done = _CONFIGURE_MENU_ITEMS[:-1]
    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]What would you like to configure?[/]")
        for i, (_, label) in enumerate(non_done, start=1):
            ui.muted_line(f"  {i}) {label}")
        ui.muted_line("  0) Done")
        raw = input(
            f"Choose an option [0-{len(non_done)}]: "
        ).strip()
        if raw == "0":
            return "done"
        idx_map = {str(i): non_done[i - 1][0] for i in range(1, len(non_done) + 1)}
        return idx_map.get(raw, "__invalid__")

    import questionary
    from questionary import Style

    labels = [label for _, label in _CONFIGURE_MENU_ITEMS]
    label_to_key = {label: key for key, label in _CONFIGURE_MENU_ITEMS}
    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "What would you like to configure?",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "done"
    return label_to_key[chosen]


def _configure_section_has_values(env: dict[str, str], fields: list[tuple]) -> bool:
    keys = [f[0] for f in fields]
    return any((env.get(k) or "").strip() for k in keys)


def _offer_bulk_keep_section(
    env: dict[str, str],
    fields: list[tuple],
    section_label: str,
) -> bool:
    """Return True if user wants to keep all existing values for keys in this section."""
    if not _configure_section_has_values(env, fields):
        return False
    ans = input(f"  Keep all existing {section_label}? [Y/n] ").strip().lower()
    return ans not in ("n", "no")


def _prompt_env_field_list(
    fields: list[tuple[str, str, bool]],
    working_env: dict[str, str],
    *,
    offer_bulk_keep: bool,
    section_label: str,
) -> None:
    if offer_bulk_keep and _offer_bulk_keep_section(working_env, fields, section_label):
        return
    for key, label, is_secret in fields:
        current = working_env.get(key, "")
        working_env[key] = _prompt_env_field(key, label, current, is_secret)


def _env_key_to_pulse_field(ek: str) -> str | None:
    if ek in _ENV_KEY_TO_CONFIG_FIELD:
        return _ENV_KEY_TO_CONFIG_FIELD[ek]
    if ek.startswith("PULSE_"):
        cand = ek[6:].lower()
        if cand in _PULSE_ROOT_FIELD_NAMES:
            return cand
    return None


def _ordered_pulse_root_field_names() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ek in _CONFIGURE_ENV_KEY_ORDER:
        fname = _env_key_to_pulse_field(ek)
        if fname and fname not in seen:
            seen.add(fname)
            out.append(fname)
    for fname in sorted(_PULSE_ROOT_FIELD_NAMES):
        if fname not in seen:
            out.append(fname)
    return out


def _pulse_config_to_working_env(cfg: PulseConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    for fname in _PULSE_ROOT_FIELD_NAMES:
        val = getattr(cfg, fname)
        env_k = f"PULSE_{fname.upper()}"
        if val is None:
            out[env_k] = ""
        elif isinstance(val, bool):
            out[env_k] = "true" if val else "false"
        else:
            out[env_k] = str(val)
    if cfg.anthropic_api_key:
        ak = cfg.anthropic_api_key
        out["ANTHROPIC_API_KEY"] = ak
        out["PULSE_ANTHROPIC_API_KEY"] = ak
    if cfg.openai_api_key:
        out["OPENAI_API_KEY"] = cfg.openai_api_key
    if cfg.gemini_api_key:
        out["GEMINI_API_KEY"] = cfg.gemini_api_key
    return out


def _connector_prereqs_met(name: str, env: dict[str, str]) -> bool:
    g = (env.get("PULSE_GOOGLE_CLIENT_ID") or "").strip() and (
        env.get("PULSE_GOOGLE_CLIENT_SECRET") or ""
    ).strip()
    if name in ("gmail", "calendar", "youtube"):
        return bool(g)
    if name == "spotify":
        return bool(
            (env.get("PULSE_SPOTIFY_CLIENT_ID") or "").strip()
            and (env.get("PULSE_SPOTIFY_CLIENT_SECRET") or "").strip()
        )
    if name in ("microsoft_mail", "microsoft_calendar"):
        return bool(
            (env.get("PULSE_MICROSOFT_CLIENT_ID") or "").strip()
            and (env.get("PULSE_MICROSOFT_CLIENT_SECRET") or "").strip()
        )
    if name == "github":
        return bool(
            (env.get("PULSE_GITHUB_CLIENT_ID") or "").strip()
            and (env.get("PULSE_GITHUB_CLIENT_SECRET") or "").strip()
        )
    if name == "gitlab":
        return bool(
            (env.get("PULSE_GITLAB_TOKEN") or "").strip()
            or (
                (env.get("PULSE_GITLAB_CLIENT_ID") or "").strip()
                and (env.get("PULSE_GITLAB_CLIENT_SECRET") or "").strip()
            )
        )
    if name == "plaid":
        return bool(
            (env.get("PULSE_PLAID_CLIENT_ID") or "").strip()
            and (env.get("PULSE_PLAID_SECRET") or "").strip()
            and (env.get("PULSE_PLAID_ENV") or "").strip()
        )
    if name == "oura":
        return bool(
            (env.get("PULSE_OURA_PERSONAL_ACCESS_TOKEN") or "").strip()
            or (
                (env.get("PULSE_OURA_CLIENT_ID") or "").strip()
                and (env.get("PULSE_OURA_CLIENT_SECRET") or "").strip()
            )
        )
    if name == "notion":
        return bool((env.get("PULSE_NOTION_TOKEN") or "").strip())
    if name == "linear":
        return bool((env.get("PULSE_LINEAR_API_KEY") or "").strip())
    return True


def _prompt_enable_connector(
    label: str,
    *,
    creds_ok: bool,
    was_enabled: bool,
) -> bool:
    if was_enabled and not creds_ok:
        ui.muted_line(
            "  (Note: connector was enabled but matching credentials look missing.)"
        )
    # First-time / currently off: opt in (default off) even if pulse.toml already has creds.
    if not was_enabled:
        yn = input(f"  Enable {label}? [y/N] ").strip().lower()
        return yn in ("y", "yes")
    if creds_ok:
        yn = input(f"  Enable {label}? [Y/n] ").strip().lower()
        return yn not in ("n", "no")
    yn = input(f"  Keep {label} enabled (creds look missing)? [y/N] ").strip().lower()
    return yn in ("y", "yes")


def _load_full_pulse_toml(toml_path: Path) -> dict:
    """Parse pulse.toml into a nested dict (empty if missing)."""
    import tomllib

    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _load_connectors_state(toml_path: Path) -> dict[str, dict]:
    raw_block: dict = {}
    data = _load_full_pulse_toml(toml_path)
    cc = data.get("connectors")
    if isinstance(cc, dict):
        raw_block = cc
    state: dict[str, dict] = {}
    for name, _, _ in _CONNECTOR_DEFS:
        v = raw_block.get(name)
        state[name] = dict(v) if isinstance(v, dict) else {}
    return state


def _toml_inline_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    raise TypeError(f"Unsupported TOML value type: {type(v)!r}")


def _coerce_pulse_root_string(fname: str, raw: str) -> str | int | bool:
    raw = raw.strip()
    if fname == "smtp_port":
        return int(raw)
    if fname in ("smtp_use_tls", "smtp_use_ssl"):
        return raw.lower() in ("1", "true", "yes", "on")
    return raw


def _merge_working_env_into_full_root(full: dict, working_env: dict[str, str]) -> None:
    for ek, fname in _ENV_KEY_TO_CONFIG_FIELD.items():
        if ek not in working_env:
            continue
        v = working_env[ek].strip()
        if v:
            full[fname] = v
        else:
            full.pop(fname, None)
    for key, val in working_env.items():
        if not key.startswith("PULSE_"):
            continue
        fname = key[6:].lower()
        if fname not in _PULSE_ROOT_FIELD_NAMES:
            continue
        v = val.strip()
        if not v:
            full.pop(fname, None)
        else:
            full[fname] = _coerce_pulse_root_string(fname, v)


def _pulse_scalar_empty_for_emit(v: object) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _emit_pulse_root_scalar_lines(full: dict) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for fname in _ordered_pulse_root_field_names():
        if fname not in full:
            continue
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
        seen.add(fname)
    for fname in sorted(k for k in full if k in _PULSE_ROOT_FIELD_NAMES and k not in seen):
        v = full[fname]
        if _pulse_scalar_empty_for_emit(v):
            continue
        lines.append(f"{fname} = {_toml_inline_value(v)}")
    return lines


def _connector_emit_lines(
    name: str, sec: dict, default_interval: str
) -> list[str]:
    lines: list[str] = []
    enabled = _connector_section_enabled(sec)
    interval = sec.get("poll_interval") or default_interval
    if not isinstance(interval, str):
        interval = str(interval)
    lines.append(f"[connectors.{name}]")
    lines.append(f"enabled = {'true' if enabled else 'false'}")
    lines.append(f'poll_interval = "{interval}"')
    if name == "spotify":
        supp = sec.get("supplementary_interval", "6h")
        if not isinstance(supp, str):
            supp = str(supp)
        lines.append(f'supplementary_interval = "{supp}"')
    if name == "browser":
        bt = sec.get("browser", "chrome")
        if not isinstance(bt, str):
            bt = str(bt)
        lines.append(f'browser = "{bt}"')
        dbp = sec.get("db_path")
        if enabled and isinstance(dbp, str) and dbp.strip():
            safe = dbp.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'db_path = "{safe}"')
    if name == "microsoft_calendar":
        cal_id = sec.get("calendar_id", "primary")
        if not isinstance(cal_id, str):
            cal_id = str(cal_id)
        safe_cal = cal_id.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'calendar_id = "{safe_cal}"')
    if name == "gitlab":
        bu = sec.get("gitlab_base_url", "https://gitlab.com")
        if not isinstance(bu, str):
            bu = str(bu)
        escaped = bu.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'gitlab_base_url = "{escaped}"')
    if name == "plaid":
        omit = bool(
            sec.get("omit_amounts_in_summary") or sec.get("omit_amounts_in_digest", False)
        )
        lines.append(f"omit_amounts_in_summary = {'true' if omit else 'false'}")
    if name == "notion":
        prev_dbs = sec.get("database_ids") or []
        if isinstance(prev_dbs, str):
            prev_dbs = [prev_dbs] if prev_dbs else []
        escaped = [u.replace("\\", "\\\\").replace('"', '\\"') for u in prev_dbs]
        if escaped:
            lines.append(
                "database_ids = [" + ", ".join(f'"{u}"' for u in escaped) + "]"
            )
    if name == "feeds":
        prev_urls = sec.get("urls")
        if prev_urls is None:
            prev_urls = []
        if isinstance(prev_urls, str):
            prev_urls = [prev_urls] if prev_urls else []
        escaped = [u.replace("\\", "\\\\").replace('"', '\\"') for u in prev_urls]
        if escaped:
            lines.append("urls = [" + ", ".join(f'"{u}"' for u in escaped) + "]")
        else:
            lines.append("urls = []")
    lines.append("")
    return lines


def _emit_generic_connectors_table(name: str, sec: dict) -> list[str]:
    """Emit [connectors.X] for keys not in _CONNECTOR_DEFS (e.g. companion)."""
    lines = [f"[connectors.{name}]"]
    for k, v in sorted(sec.items()):
        if isinstance(v, dict):
            continue
        if isinstance(v, list):
            parts = []
            for x in v:
                if isinstance(x, str):
                    sx = x.replace("\\", "\\\\").replace('"', '\\"')
                    parts.append(f'"{sx}"')
                else:
                    parts.append(_toml_inline_value(x))
            lines.append(f"{k} = [" + ", ".join(parts) + "]")
        else:
            lines.append(f"{k} = {_toml_inline_value(v)}")
    lines.append("")
    return lines


def _emit_llm_sections(llm: dict) -> list[str]:
    lines: list[str] = []
    scalars: dict[str, object] = {}
    nested: dict[str, dict] = {}
    for k, v in llm.items():
        if isinstance(v, dict):
            nested[k] = v
        else:
            scalars[k] = v
    if scalars:
        lines.append("[llm]")
        for k in sorted(scalars):
            lines.append(f"{k} = {_toml_inline_value(scalars[k])}")
        lines.append("")
    for sub in ("summarization", "discovery", "corrections"):
        if sub not in nested:
            continue
        blk = nested[sub]
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    for sub, blk in sorted(nested.items()):
        if sub in ("summarization", "discovery", "corrections"):
            continue
        if not isinstance(blk, dict) or not blk:
            continue
        lines.append(f"[llm.{sub}]")
        for k in sorted(blk):
            lines.append(f"{k} = {_toml_inline_value(blk[k])}")
        lines.append("")
    return lines


def _serialize_pulse_toml_document(full: dict) -> str:
    """Emit pulse.toml: app scalars, connectors, ``[llm]``, then other top-level tables."""
    lines = [
        "# Pulse configuration (single file: paths, secrets, connectors, LLM roles).",
        "# ``PULSE_*`` and vendor API env vars override values from this file when set.",
        "",
    ]
    root_lines = _emit_pulse_root_scalar_lines(full)
    if root_lines:
        lines.append("# --- App (paths, integrations, notifications, API keys) ---")
        lines.extend(root_lines)
        lines.append("")
    connectors = full.get("connectors")
    if not isinstance(connectors, dict):
        connectors = {}
    known = {n for n, _, _ in _CONNECTOR_DEFS}
    for name, default_interval, _label in _CONNECTOR_DEFS:
        sec = connectors.get(name)
        if not isinstance(sec, dict):
            sec = {}
        lines.extend(_connector_emit_lines(name, sec, default_interval))
    for name in sorted(k for k in connectors if k not in known):
        sec = connectors.get(name)
        if isinstance(sec, dict) and sec:
            lines.extend(_emit_generic_connectors_table(name, sec))
    llm = full.get("llm")
    if isinstance(llm, dict) and llm:
        lines.append("# --- LLM (source summarization, discovery, corrections) ---")
        lines.append("")
        lines.extend(_emit_llm_sections(llm))
    skip_top = frozenset(("connectors", "llm")) | _PULSE_ROOT_FIELD_NAMES
    for top_key in sorted(k for k in full if k not in skip_top):
        # Forward-compat: extra top-level sections as [key] with flat scalars only.
        block = full[top_key]
        if not isinstance(block, dict):
            continue
        if not block or any(isinstance(v, dict) for v in block.values()):
            continue
        lines.append(f"[{top_key}]")
        for k in sorted(block):
            lines.append(f"{k} = {_toml_inline_value(block[k])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _save_pulse_settings(toml_path: Path, working_env: dict[str, str]) -> None:
    if not (working_env.get("PULSE_SMTP_PORT") or "").strip():
        working_env["PULSE_SMTP_PORT"] = "587"
    full = _load_full_pulse_toml(toml_path)
    _merge_working_env_into_full_root(full, working_env)
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _write_connectors_state(state: dict[str, dict], toml_path: Path) -> None:
    full = _load_full_pulse_toml(toml_path)
    old_c = full.get("connectors")
    if not isinstance(old_c, dict):
        old_c = {}
    merged = dict(old_c)
    for name, _, _ in _CONNECTOR_DEFS:
        merged[name] = state.get(name) or {}
    full["connectors"] = merged
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))


def _connector_section_enabled(section: dict) -> bool:
    """True only when this connector block is turned on in pulse.toml.

    Avoid ``bool("false")`` which is True in Python — some hand-edited files use strings.
    """
    if not section:
        return False
    raw = section.get("enabled")
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, str):
        t = raw.strip().lower()
        return t in ("true", "1", "yes", "on")
    if isinstance(raw, (int, float)):
        return raw != 0
    return False


def _prompt_one_connector_toml_section(
    name: str,
    default_interval: str,
    label: str,
    existing: dict,
    working_env: dict[str, str],
) -> dict:
    was_enabled = existing.get("enabled", True) if existing else False
    if not isinstance(was_enabled, bool):
        was_enabled = bool(was_enabled)
    interval = existing.get("poll_interval", default_interval)
    if not isinstance(interval, str):
        interval = str(interval)
    creds_ok = _connector_prereqs_met(name, working_env)

    if existing:
        status = "enabled" if was_enabled else "disabled"
        answer = (
            input(f"  {label}: {status}, poll {interval} — keep? [Y/n] ").strip().lower()
        )
        if answer in ("n", "no"):
            enabled = _prompt_enable_connector(
                label, creds_ok=creds_ok, was_enabled=was_enabled
            )
            new_interval = input(f"    Poll interval [{interval}]: ").strip()
            if new_interval:
                interval = new_interval
        else:
            enabled = was_enabled
            if enabled and not creds_ok:
                ui.muted_line(
                    "  (Note: still enabled, but matching credentials look missing.)"
                )
    else:
        enabled = _prompt_enable_connector(
            label, creds_ok=creds_ok, was_enabled=False
        )
        if enabled:
            new_interval = input(f"    Poll interval [{interval}]: ").strip()
            if new_interval:
                interval = new_interval

    enabled = bool(enabled)
    section: dict = {"enabled": enabled, "poll_interval": interval}

    if name == "spotify":
        supp = existing.get("supplementary_interval", "6h")
        section["supplementary_interval"] = str(supp) if supp is not None else "6h"

    if name == "browser":
        browser_type = existing.get("browser", "chrome")
        if not isinstance(browser_type, str):
            browser_type = str(browser_type)
        if existing:
            answer = (
                input(f"    Browser: {browser_type} — keep? [Y/n] ").strip().lower()
            )
            if answer in ("n", "no"):
                choice = input("    Browser type (chrome/firefox): ").strip()
                browser_type = choice if choice else browser_type
        else:
            choice = input(f"    Browser type [{browser_type}]: ").strip()
            browser_type = choice if choice else browser_type
        section["browser"] = browser_type

        db_path_existing = ""
        if existing:
            raw_db = existing.get("db_path")
            if isinstance(raw_db, str):
                db_path_existing = raw_db.strip()
        db_path_val = db_path_existing
        if enabled:
            if db_path_existing:
                answer = (
                    input(
                        f"    Browser history SQLite path [{db_path_existing}] — keep? [Y/n] "
                    )
                    .strip()
                    .lower()
                )
                if answer in ("n", "no"):
                    db_path_val = input(
                        "    Path to browser history DB (blank = default for OS): "
                    ).strip()
            else:
                db_path_val = input(
                    "    Path to browser history SQLite (optional; blank = default): "
                ).strip()
        if enabled and db_path_val:
            section["db_path"] = db_path_val

    if name == "microsoft_calendar":
        cal_id = (existing.get("calendar_id") if existing else None) or "primary"
        if not isinstance(cal_id, str):
            cal_id = str(cal_id)
        if enabled:
            if existing:
                answer = (
                    input(f"    Calendar ID [{cal_id}] — keep? [Y/n] ").strip().lower()
                )
                if answer in ("n", "no"):
                    cal_id = (
                        input(
                            "    Graph calendar id (primary or calendar UUID): "
                        ).strip()
                        or cal_id
                    )
            else:
                cal_id = (
                    input("    Graph calendar id [primary]: ").strip() or "primary"
                )
        section["calendar_id"] = cal_id

    if name == "gitlab":
        base_url = (
            (existing.get("gitlab_base_url") if existing else None)
            or "https://gitlab.com"
        )
        if not isinstance(base_url, str):
            base_url = str(base_url)
        if enabled:
            if existing:
                answer = (
                    input(f"    GitLab base URL [{base_url}] — keep? [Y/n] ")
                    .strip()
                    .lower()
                )
                if answer in ("n", "no"):
                    base_url = input("    GitLab base URL: ").strip() or base_url
            else:
                base_url = (
                    input("    GitLab base URL [https://gitlab.com]: ").strip()
                    or base_url
                )
        section["gitlab_base_url"] = base_url

    if name == "plaid":
        raw_existing = existing or {}
        omit = bool(
            raw_existing.get("omit_amounts_in_summary")
            or raw_existing.get("omit_amounts_in_digest", False)
        )
        if enabled:
            yn = (
                input("    Omit transaction amounts from finance summaries? [y/N] ")
                .strip()
                .lower()
            )
            if yn in ("y", "yes"):
                omit = True
        section["omit_amounts_in_summary"] = omit

    if name == "notion":
        prev_dbs: list = list(existing.get("database_ids", [])) if existing else []
        if isinstance(prev_dbs, str):
            prev_dbs = [prev_dbs] if prev_dbs else []
        if enabled:
            if prev_dbs:
                preview = ", ".join(str(x) for x in prev_dbs[:2])
                if len(prev_dbs) > 2:
                    preview += "…"
                keep = (
                    input(f"    Keep Notion database_ids ({preview})? [Y/n] ")
                    .strip()
                    .lower()
                )
                if keep in ("n", "no"):
                    prev_dbs = []
            if not prev_dbs:
                line = input(
                    "    Optional database UUIDs (comma-separated) to query in addition "
                    "to workspace search; leave empty for search only: "
                ).strip()
                prev_dbs = [u.strip() for u in line.split(",") if u.strip()]
        section["database_ids"] = prev_dbs

    if name == "feeds":
        prev_urls: list = list(existing.get("urls", [])) if existing else []
        if isinstance(prev_urls, str):
            prev_urls = [prev_urls] if prev_urls else []
        if enabled:
            if prev_urls:
                preview = ", ".join(prev_urls[:2]) + (
                    "…" if len(prev_urls) > 2 else ""
                )
                keep = (
                    input(f"    Keep feed URLs ({preview})? [Y/n] ").strip().lower()
                )
                if keep in ("n", "no"):
                    prev_urls = []
            if not prev_urls:
                line = input(
                    "    Feed URLs (comma-separated RSS/Atom URLs; leave empty to add later): "
                ).strip()
                prev_urls = [u.strip() for u in line.split(",") if u.strip()]
        section["urls"] = prev_urls

    return section


def _configure_connectors_toml(
    working_env: dict[str, str],
    toml_path: Path,
) -> list[str]:
    state = _load_connectors_state(toml_path)
    for name, default_interval, label in _CONNECTOR_DEFS:
        existing = state.get(name, {})
        state[name] = _prompt_one_connector_toml_section(
            name, default_interval, label, existing, working_env
        )
    _write_connectors_state(state, toml_path)
    return [n for n, _, _ in _CONNECTOR_DEFS if _connector_section_enabled(state[n])]


def _connector_submenu_row_label(
    name: str,
    default_interval: str,
    working_env: dict[str, str],
    state: dict[str, dict],
) -> str:
    """Compact row: ●/○ (pulse.toml enabled) · emoji · short · ✓/✗ only when ● · poll."""
    creds = _connector_prereqs_met(name, working_env)
    st = state.get(name, {})
    en = _connector_section_enabled(st)
    poll = st.get("poll_interval", default_interval)
    if not isinstance(poll, str):
        poll = str(poll)
    circle = "●" if en else "○"
    emoji = _CONNECTOR_MENU_EMOJI[name]
    short = _CONNECTOR_MENU_SHORT[name]
    cred_mark = f" {'✓' if creds else '✗'}" if en else ""
    return f"{circle} {emoji} {short}{cred_mark} {poll}"


def _pick_connector_submenu(
    working_env: dict[str, str],
    state: dict[str, dict],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for name, default_interval, _label in _CONNECTOR_DEFS:
        disp = _connector_submenu_row_label(
            name, default_interval, working_env, state
        )
        rows.append((name, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a connector to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Connectors",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_connectors_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_connector_legend = False
    while True:
        state = _load_connectors_state(toml_path)
        if not showed_connector_legend:
            ui.muted_line(
                "● = enabled in pulse.toml · ○ = disabled · ✓/✗ = credential prereqs (only when ●). "
                "Pick a source to edit its credentials and block; when you save with ●, "
                "OAuth / Plaid Link / Oura run here if that source needs tokens."
            )
            showed_connector_legend = True
        pick = _pick_connector_submenu(
            working_env, state, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        name = pick
        _triple = next(t for t in _CONNECTOR_DEFS if t[0] == name)
        _, default_interval, label = _triple
        ui.step(label)
        fields = _CONNECTOR_ENV_FIELDS.get(name, [])
        if fields:
            ui.muted_line("Credentials for this connector (saved in pulse.toml; leave blank to skip).")
            _prompt_env_field_list(
                fields,
                working_env,
                offer_bulk_keep=toml_path.exists(),
                section_label=f"{label} credentials",
            )
            _save_pulse_settings(toml_path, working_env)
            ui.success(f"Saved {toml_path}")
        state = _load_connectors_state(toml_path)
        existing = state.get(name, {})
        state[name] = _prompt_one_connector_toml_section(
            name, default_interval, label, existing, working_env
        )
        _write_connectors_state(state, toml_path)
        ui.success(f"Saved {toml_path}")
        enabled_now = [
            n for n, _, _ in _CONNECTOR_DEFS if _connector_section_enabled(state[n])
        ]
        ui.kv_line("Enabled connectors", ", ".join(enabled_now) or "none")
        if offer_oauth and _connector_section_enabled(state[name]):
            _configure_oauth_prompts(working_env, [name])


def _configure_oauth_prompts(
    env_values: dict[str, str], enabled_connectors: list[str]
) -> None:
    google_connectors = [
        c for c in enabled_connectors if c in ("gmail", "calendar", "youtube")
    ]
    has_google_creds = env_values.get("PULSE_GOOGLE_CLIENT_ID") and env_values.get(
        "PULSE_GOOGLE_CLIENT_SECRET"
    )
    has_spotify_creds = env_values.get("PULSE_SPOTIFY_CLIENT_ID") and env_values.get(
        "PULSE_SPOTIFY_CLIENT_SECRET"
    )

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

    ms_connectors = [
        c for c in enabled_connectors if c in ("microsoft_mail", "microsoft_calendar")
    ]
    has_ms_creds = env_values.get("PULSE_MICROSOFT_CLIENT_ID") and env_values.get(
        "PULSE_MICROSOFT_CLIENT_SECRET"
    )
    microsoft_tokens = data_dir / "microsoft_tokens.json"
    if ms_connectors and has_ms_creds:
        if microsoft_tokens.exists():
            ui.muted_line(f"Microsoft 365: already authorized ({microsoft_tokens})")
            answer = input("  Re-authorize? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_microsoft()
        else:
            ui.step("Microsoft 365 authorization")
            ui.kv_line("Connectors", ", ".join(ms_connectors))
            answer = input("  Run Microsoft OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_microsoft()

    gh_enabled = "github" in enabled_connectors
    has_gh = env_values.get("PULSE_GITHUB_CLIENT_ID") and env_values.get(
        "PULSE_GITHUB_CLIENT_SECRET"
    )
    github_tokens = data_dir / "github_tokens.json"
    if gh_enabled and has_gh:
        if github_tokens.exists():
            ui.muted_line(f"GitHub: already authorized ({github_tokens})")
            answer = input("  Re-authorize GitHub? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_github()
        else:
            ui.step("GitHub authorization")
            answer = input("  Run GitHub OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_github()

    gl_enabled = "gitlab" in enabled_connectors
    has_gl_oauth = env_values.get("PULSE_GITLAB_CLIENT_ID") and env_values.get(
        "PULSE_GITLAB_CLIENT_SECRET"
    )
    has_gl_pat = bool(env_values.get("PULSE_GITLAB_TOKEN"))
    gitlab_tokens = data_dir / "gitlab_tokens.json"
    if gl_enabled and has_gl_oauth and not has_gl_pat:
        if gitlab_tokens.exists():
            ui.muted_line(f"GitLab: already authorized ({gitlab_tokens})")
            answer = input("  Re-authorize GitLab? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_gitlab()
        else:
            ui.step("GitLab authorization")
            answer = input("  Run GitLab OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_gitlab()
    elif gl_enabled and has_gl_pat:
        ui.muted_line("GitLab: using PULSE_GITLAB_TOKEN — OAuth skipped.")

    plaid_enabled = "plaid" in enabled_connectors
    has_plaid = env_values.get("PULSE_PLAID_CLIENT_ID") and env_values.get(
        "PULSE_PLAID_SECRET"
    )
    plaid_tokens = data_dir / "plaid_tokens.json"
    if plaid_enabled and has_plaid:
        if plaid_tokens.exists():
            ui.muted_line(f"Plaid: already linked ({plaid_tokens})")
            answer = input("  Re-link Plaid? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_plaid()
        else:
            ui.step("Plaid Link")
            answer = input("  Open Plaid Link now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_plaid()

    oura_enabled = "oura" in enabled_connectors
    has_oura_oauth = env_values.get("PULSE_OURA_CLIENT_ID") and env_values.get(
        "PULSE_OURA_CLIENT_SECRET"
    )
    has_oura_pat = bool(env_values.get("PULSE_OURA_PERSONAL_ACCESS_TOKEN"))
    oura_tokens = data_dir / "oura_tokens.json"
    if oura_enabled and has_oura_oauth and not has_oura_pat:
        if oura_tokens.exists():
            ui.muted_line(f"Oura: already authorized ({oura_tokens})")
            answer = input("  Re-authorize Oura? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                _auth_oura()
        else:
            ui.step("Oura authorization")
            answer = input("  Run Oura OAuth now? [Y/n] ").strip().lower()
            if answer not in ("n", "no"):
                _auth_oura()
    elif oura_enabled and has_oura_pat:
        ui.muted_line("Oura: using PULSE_OURA_PERSONAL_ACCESS_TOKEN — OAuth skipped.")


def _configure_core_only(working_env: dict[str, str]) -> None:
    ui.step("Core settings")
    for key, label, default, is_secret in _CONFIGURE_CORE_FIELDS:
        current = working_env.get(key, "") or default
        working_env[key] = _prompt_env_field(key, label, current, is_secret)


def _core_setting_ready(setting_id: str, env: dict[str, str]) -> bool:
    row = next(r for r in _CORE_SETTING_DEFS if r[0] == setting_id)
    _sid, _label, _emoji, fields = row
    return all((env.get(f[0]) or "").strip() for f in fields)


def _core_setting_submenu_row_label(
    setting_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _core_setting_ready(setting_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_core_setting_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for sid, short, emoji, _fields in _CORE_SETTING_DEFS:
        disp = _core_setting_submenu_row_label(sid, short, emoji, working_env)
        rows.append((sid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a core setting to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Core settings",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_core_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = value set in pulse.toml · ○ = empty · "
                "Database file, Obsidian vault, and timezone for scheduling."
            )
            showed_legend = True
        pick = _pick_core_setting_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _CORE_SETTING_DEFS if r[0] == pick)
        _sid, label, _emoji, fields = row
        ui.step(label)
        ui.muted_line("Values for this setting (saved in pulse.toml; leave blank to skip).")
        for key, fld_label, default, is_secret in fields:
            current = working_env.get(key, "") or default
            working_env[key] = _prompt_env_field(key, fld_label, current, is_secret)
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


def _configure_integrations_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Credentials (integrations)")
    ui.muted_line("OAuth clients and API keys for data sources. Leave blank to skip.")
    _prompt_env_field_list(
        _CONFIGURE_INTEGRATION_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="integration credentials",
    )


def _model_provider_ready(provider_id: str, env: dict[str, str]) -> bool:
    """True when typical env creds exist for that LLM vendor (Ollama is pulse.toml + optional key)."""

    def g(key: str) -> str:
        return (env.get(key) or "").strip()

    if provider_id == "anthropic":
        return bool(g("ANTHROPIC_API_KEY") or g("PULSE_ANTHROPIC_API_KEY"))
    if provider_id == "openai":
        return bool(g("OPENAI_API_KEY") or g("PULSE_OPENAI_API_KEY"))
    if provider_id == "gemini":
        return bool(g("GEMINI_API_KEY") or g("PULSE_GEMINI_API_KEY"))
    if provider_id == "ollama":
        return False
    return False


def _model_provider_submenu_row_label(
    provider_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _model_provider_ready(provider_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_model_provider_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for pid, short, emoji, _fields in _MODEL_PROVIDER_DEFS:
        disp = _model_provider_submenu_row_label(pid, short, emoji, working_env)
        rows.append((pid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a model provider to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Model providers",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_model_providers_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = API key set in pulse.toml for that vendor · ○ = missing · "
                "Match [llm] / [llm.summarization] / … provider values in pulse.toml."
            )
            showed_legend = True
        pick = _pick_model_provider_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _MODEL_PROVIDER_DEFS if r[0] == pick)
        _pid, label, _emoji, fields = row
        ui.step(label)
        if not fields:
            ui.muted_line(
                "Uses the OpenAI-compatible client. In pulse.toml set provider = \"ollama\", "
                "base_url (e.g. http://127.0.0.1:11434/v1), and a model id under [llm] or a role. "
                "OPENAI_API_KEY can stay blank; Pulse uses a placeholder when unset."
            )
            continue
        ui.muted_line("API keys for this vendor (saved in pulse.toml; leave blank to skip).")
        _prompt_env_field_list(
            fields,
            working_env,
            offer_bulk_keep=toml_path.exists(),
            section_label=f"{label} API keys",
        )
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


def _configure_model_providers_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Model providers")
    ui.muted_line(
        "Provider choice and model ids live in pulse.toml under [llm] / [llm.summarization] / …; "
        "this pass writes vendor API keys into pulse.toml. Leave blank to skip."
    )
    _prompt_env_field_list(
        _CONFIGURE_MODEL_PROVIDER_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="model provider API keys",
    )


def _notification_provider_ready(provider_id: str, env: dict[str, str]) -> bool:
    """● row hint: outbound channel ready, corrections secret set, or companion/FCM partially configured."""

    def g(key: str) -> str:
        return (env.get(key) or "").strip()

    if provider_id == "telegram":
        return bool(g("PULSE_TELEGRAM_BOT_TOKEN") and g("PULSE_TELEGRAM_CHAT_ID"))
    if provider_id == "ntfy":
        return bool(g("PULSE_NTFY_TOPIC"))
    if provider_id == "webhook":
        return bool(g("PULSE_NOTIFICATION_WEBHOOK_URL"))
    if provider_id == "discord":
        return bool(g("PULSE_DISCORD_WEBHOOK_URL"))
    if provider_id == "slack":
        return bool(g("PULSE_SLACK_WEBHOOK_URL"))
    if provider_id == "pushover":
        return bool(g("PULSE_PUSHOVER_USER_KEY") and g("PULSE_PUSHOVER_API_TOKEN"))
    if provider_id == "gotify":
        return bool(g("PULSE_GOTIFY_URL") and g("PULSE_GOTIFY_APP_TOKEN"))
    if provider_id == "smtp":
        if not (g("PULSE_SMTP_HOST") and g("PULSE_SMTP_FROM") and g("PULSE_SMTP_TO")):
            return False
        to_list = [x.strip() for x in g("PULSE_SMTP_TO").split(",") if x.strip()]
        return bool(to_list)
    if provider_id == "corrections":
        return bool(g("PULSE_CORRECTIONS_WEBHOOK_SECRET"))
    if provider_id == "companion":
        return bool(g("PULSE_COMPANION_TOKEN") or g("PULSE_FCM_SERVICE_ACCOUNT_PATH"))
    return False


def _notification_submenu_row_label(
    provider_id: str, short: str, emoji: str, working_env: dict[str, str]
) -> str:
    circle = "●" if _notification_provider_ready(provider_id, working_env) else "○"
    return f"{circle} {emoji} {short}"


def _pick_notification_provider_submenu(
    working_env: dict[str, str],
    *,
    exit_label: str = "← Back",
) -> str | None:
    rows: list[tuple[str, str]] = []
    for pid, short, emoji, _fields in _NOTIFICATION_PROVIDER_DEFS:
        disp = _notification_submenu_row_label(pid, short, emoji, working_env)
        rows.append((pid, disp))
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Pick a notification provider to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Notification providers",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_notifications_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "● = required values set in pulse.toml for that channel · ○ = incomplete · "
                "Several channels can be active; notifications broadcast to all that are ready."
            )
            showed_legend = True
        pick = _pick_notification_provider_submenu(
            working_env, exit_label=submenu_exit_label
        )
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        row = next(r for r in _NOTIFICATION_PROVIDER_DEFS if r[0] == pick)
        _pid, label, _emoji, fields = row
        ui.step(label)
        ui.muted_line("Values for this channel (saved in pulse.toml; leave blank to skip).")
        _prompt_env_field_list(
            fields,
            working_env,
            offer_bulk_keep=toml_path.exists(),
            section_label=f"{label} notifications",
        )
        _save_pulse_settings(toml_path, working_env)
        ui.success(f"Saved {toml_path}")


def _configure_notifications_only(working_env: dict[str, str], toml_path: Path) -> None:
    ui.step("Notifications")
    ui.muted_line("Telegram, webhooks, and SMTP. Leave blank to skip.")
    _prompt_env_field_list(
        _CONFIGURE_NOTIFICATION_FIELDS,
        working_env,
        offer_bulk_keep=toml_path.exists(),
        section_label="notification settings",
    )


_LLM_ROLES_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "gemini", "ollama")
_OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
_WIZARD_DEFAULT_ANTHROPIC_SUMM = "claude-haiku-4-5-20251001"
_WIZARD_DEFAULT_ANTHROPIC_DISC = "claude-sonnet-4-6"


def _configure_llm_roles_wizard(
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    """Prompt for [llm] provider, summarization model, discovery model; merge into pulse.toml."""

    defaults_map: dict[str, tuple[str, str]] = {
        "anthropic": (
            _WIZARD_DEFAULT_ANTHROPIC_SUMM,
            _WIZARD_DEFAULT_ANTHROPIC_DISC,
        ),
        "openai": ("gpt-4.1-mini", "gpt-4.1"),
        "gemini": ("gemini-2.5-flash", "gemini-2.5-pro"),
        "ollama": ("llama3.2", "llama3.2"),
    }

    full = _load_full_pulse_toml(toml_path)
    cur = full.get("llm") if isinstance(full.get("llm"), dict) else {}
    summ_blk = (
        cur.get("summarization") if isinstance(cur.get("summarization"), dict) else {}
    )
    disc_blk = cur.get("discovery") if isinstance(cur.get("discovery"), dict) else {}
    summ_m = (summ_blk.get("model") or "").strip()
    disc_m = (disc_blk.get("model") or "").strip()
    cur_prov = (cur.get("provider") or "").strip().lower()
    if cur_prov not in _LLM_ROLES_PROVIDERS:
        cur_prov = ""

    ui.step("LLM roles in pulse.toml")
    ui.muted_line(
        "Sets [llm] provider plus [llm.summarization] and [llm.discovery] model ids. "
        "API keys live in pulse.toml (Model → Provider API keys). Existing [llm.corrections] is kept."
    )

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]LLM provider[/]")
        for i, p in enumerate(_LLM_ROLES_PROVIDERS, start=1):
            ui.muted_line(f"  {i}) {p}")
        forward_exit = (
            "next" in submenu_exit_label.lower()
            and "back" not in submenu_exit_label.lower()
        )
        non_tty_exit = submenu_exit_label if forward_exit else "Cancel"
        ui.muted_line(f"  0) {non_tty_exit}")
        raw = input(f"Choose [0-{len(_LLM_ROLES_PROVIDERS)}]: ").strip()
        if raw == "0":
            return
        try:
            idx = int(raw)
        except ValueError:
            ui.warning("Invalid choice.")
            return
        if idx < 1 or idx > len(_LLM_ROLES_PROVIDERS):
            ui.warning("Invalid choice.")
            return
        provider = _LLM_ROLES_PROVIDERS[idx - 1]
    else:
        import questionary
        from questionary import Style

        style = Style(
            [
                ("qmark", "fg:default"),
                ("question", "bold"),
                ("answer", "fg:cyan bold"),
                ("pointer", "fg:cyan bold"),
                ("highlighted", "fg:cyan bold"),
            ]
        )
        choices = list(_LLM_ROLES_PROVIDERS) + [submenu_exit_label]
        chosen = questionary.select(
            "LLM provider (one for summarization and discovery)",
            choices=choices,
            qmark="›",
            style=style,
            instruction=" (↑↓ move · Enter to select)",
        ).ask()
        if chosen is None or chosen == submenu_exit_label:
            return
        provider = chosen

    d0, d1 = defaults_map[provider]
    summ_def = summ_m or d0
    disc_def = disc_m or d1

    base_url = ""
    if provider == "ollama":
        existing_bu = cur.get("base_url")
        if isinstance(existing_bu, str):
            base_url = existing_bu.strip()
        bu_default = base_url or _OLLAMA_DEFAULT_BASE_URL
        if not sys.stdin.isatty():
            bu_in = input(f"  OpenAI-compatible base URL [{bu_default}]: ").strip()
            base_url = bu_in or bu_default
        else:
            import questionary
            from questionary import Style

            style = Style(
                [
                    ("qmark", "fg:default"),
                    ("question", "bold"),
                    ("answer", "fg:cyan bold"),
                    ("pointer", "fg:cyan bold"),
                    ("highlighted", "fg:cyan bold"),
                ]
            )
            bu_in = questionary.text(
                "Ollama base URL (OpenAI-compatible)",
                default=bu_default,
                qmark="›",
                style=style,
            ).ask()
            if bu_in is None:
                return
            base_url = (bu_in or bu_default).strip()

    if not sys.stdin.isatty():
        s_in = input(f"  Summarization model [{summ_def}]: ").strip()
        summ = s_in or summ_def
        d_in = input(f"  Discovery model [{disc_def}]: ").strip()
        disc = d_in or disc_def
    else:
        import questionary
        from questionary import Style

        style = Style(
            [
                ("qmark", "fg:default"),
                ("question", "bold"),
                ("answer", "fg:cyan bold"),
                ("pointer", "fg:cyan bold"),
                ("highlighted", "fg:cyan bold"),
            ]
        )
        s_in = questionary.text(
            "Summarization model id",
            default=summ_def,
            qmark="›",
            style=style,
        ).ask()
        if s_in is None:
            return
        summ = s_in.strip() or summ_def
        d_in = questionary.text(
            "Discovery model id",
            default=disc_def,
            qmark="›",
            style=style,
        ).ask()
        if d_in is None:
            return
        disc = d_in.strip() or disc_def

    managed = {"provider", "base_url", "summarization", "discovery", "corrections"}
    new_llm: dict = {}
    for k, v in cur.items():
        if k in managed:
            continue
        new_llm[k] = v
    corr = cur.get("corrections")
    if isinstance(corr, dict) and corr:
        new_llm["corrections"] = dict(corr)

    new_summ = dict(summ_blk)
    new_summ["model"] = summ
    new_disc = dict(disc_blk)
    new_disc["model"] = disc

    new_llm["provider"] = provider
    new_llm["summarization"] = new_summ
    new_llm["discovery"] = new_disc
    if provider == "ollama":
        new_llm["base_url"] = base_url
    elif provider == "openai":
        old_bu = cur.get("base_url")
        if isinstance(old_bu, str) and old_bu.strip():
            new_llm["base_url"] = old_bu.strip()

    full["llm"] = new_llm
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    toml_path.write_text(_serialize_pulse_toml_document(full))
    ui.success(f"Saved {toml_path}")


def _pick_model_hub_section(*, exit_label: str = "← Back") -> str | None:
    rows: list[tuple[str, str]] = list(_MODEL_HUB_ITEMS)
    rows.append(("__back__", exit_label))

    labels = [r[1] for r in rows]
    val_by_label = {r[1]: r[0] for r in rows}

    if not sys.stdin.isatty():
        ui.muted_line("")
        ui.say("[accent]Model — choose what to configure[/]")
        for i, (_, disp) in enumerate(rows, start=1):
            ui.muted_line(f"  {i}) {disp}")
        raw = input(f"Choose [1-{len(rows)}]: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            return "__invalid__"
        if idx < 1 or idx > len(rows):
            return "__invalid__"
        return rows[idx - 1][0]

    import questionary
    from questionary import Style

    style = Style(
        [
            ("qmark", "fg:default"),
            ("question", "bold"),
            ("answer", "fg:cyan bold"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
        ]
    )
    chosen = questionary.select(
        "Model",
        choices=labels,
        qmark="›",
        style=style,
        instruction=" (↑↓ move · Enter to select)",
    ).ask()
    if chosen is None:
        return "__back__"
    return val_by_label[chosen]


def _configure_model_hub(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    submenu_exit_label: str = "← Back",
) -> None:
    showed_legend = False
    while True:
        if not showed_legend:
            ui.muted_line(
                "Provider API keys are stored in pulse.toml; LLM roles set [llm] provider "
                "and summarization / discovery model ids (also in pulse.toml)."
            )
            showed_legend = True
        pick = _pick_model_hub_section(exit_label=submenu_exit_label)
        if pick is None or pick == "__back__":
            break
        if pick == "__invalid__":
            ui.warning("Invalid choice.")
            continue
        if pick == "api_keys":
            ui.step("Provider API keys")
            _configure_model_providers_hub(
                working_env, toml_path, submenu_exit_label=submenu_exit_label
            )
        elif pick == "llm_roles":
            ui.step("LLM roles in pulse.toml")
            _configure_llm_roles_wizard(
                toml_path, submenu_exit_label=submenu_exit_label
            )


def _run_configure_full_wizard(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
) -> None:
    _configure_core_only(working_env)
    _configure_integrations_only(working_env, toml_path)
    _configure_model_providers_only(working_env, toml_path)
    if sys.stdin.isatty():
        llm_ans = input(
            "  Configure [llm] provider and model roles in pulse.toml now? [y/N] "
        ).strip().lower()
        if llm_ans in ("y", "yes"):
            _configure_llm_roles_wizard(toml_path)
    _configure_notifications_only(working_env, toml_path)
    _save_pulse_settings(toml_path, working_env)
    ui.success(f"Saved {toml_path}")

    ui.step("Connector configuration")
    enabled = _configure_connectors_toml(working_env, toml_path)
    ui.success(f"Saved {toml_path}")
    ui.kv_line("Enabled", ", ".join(enabled) or "none")

    if offer_oauth:
        _configure_oauth_prompts(working_env, enabled)

    ui.rule("Configuration complete")
    if offer_oauth:
        ui.say("[accent]Next steps[/]")
        ui.kv_line("Profile + first pull", "[cmd]pulse init[/]")
        ui.kv_line("Server + scheduler", "[cmd]pulse run[/]")


def _default_env_values(paths: PulsePaths) -> dict[str, str]:
    return {
        "PULSE_DATABASE_PATH": str(paths.data_dir / "pulse.db"),
        "PULSE_VAULT_PATH": str(paths.data_dir / "Pulse-Vault"),
        "PULSE_TIMEZONE": "UTC",
    }


def _execute_configure_menu_choice(
    choice: str,
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    """Run one top-level ``pulse configure`` area (same hubs as the interactive menu)."""
    if choice == "core":
        ui.step("Core settings")
        _configure_core_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    elif choice == "connectors":
        ui.step("Connectors")
        _configure_connectors_hub(
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )
    elif choice == "notifications":
        ui.step("Notifications")
        _configure_notifications_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    elif choice == "model":
        ui.step("Model")
        _configure_model_hub(
            working_env, toml_path, submenu_exit_label=submenu_exit_label
        )
    else:
        raise ValueError(f"unknown configure menu choice: {choice!r}")


def _run_configure_sequential_sections(
    working_env: dict[str, str],
    toml_path: Path,
    *,
    offer_oauth: bool,
    submenu_exit_label: str = "← Back",
) -> None:
    """Walk through each main configure area in order (same UIs as ``pulse configure``)."""
    order = _CONFIGURE_SEQUENTIAL_ORDER
    n = len(order)
    ui.muted_line(
        f"Same menus as [cmd]pulse configure[/]: choose [bold]{submenu_exit_label}[/] at the bottom "
        f"when you are done with an area; then the next step ({n} areas) continues automatically."
    )
    for i, key in enumerate(order, start=1):
        title = _CONFIGURE_SECTION_BANNER[key]
        ui.muted_line("")
        ui.say(f"[accent]Setup {i}/{n} · {title}[/]")
        _execute_configure_menu_choice(
            key,
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )


def _configure(
    *,
    offer_oauth: bool = True,
    interactive_menu: bool = True,
    config_dir: Path | None = None,
    menu_walkthrough: bool = False,
    suppress_banner: bool = False,
    submenu_exit_label: str = "← Back",
) -> None:
    paths = resolve_pulse_paths(config_dir=config_dir)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    toml_path = paths.toml_path

    if not suppress_banner:
        ui.banner_tagline()
    ui.rule("Pulse configuration")

    working_env = _pulse_config_to_working_env(load_config(toml_path))

    if menu_walkthrough:
        _run_configure_sequential_sections(
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )
        return

    if not interactive_menu:
        _run_configure_full_wizard(
            working_env, toml_path, offer_oauth=offer_oauth
        )
        return

    while True:
        choice = _pick_configure_menu_action()
        if choice == "__invalid__":
            ui.warning(f"Invalid choice. Enter 0–{len(_CONFIGURE_MENU_ITEMS) - 1}.")
            continue
        if choice == "done":
            ui.rule("Done")
            break
        if choice == "full":
            _run_configure_full_wizard(
                working_env, toml_path, offer_oauth=offer_oauth
            )
            break
        _execute_configure_menu_choice(
            choice,
            working_env,
            toml_path,
            offer_oauth=offer_oauth,
            submenu_exit_label=submenu_exit_label,
        )


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


# Shown during interactive `pulse init` so users can copy it into another chat product.
_LLM_ASSISTANT_EXPORT_PROMPT = """I'm setting up Pulse, a self-hosted tool that pulls together my email, calendar, music, browsing, and similar sources into one place. I need a factual baseline about me so Pulse can make sense of that data (who people are, what I work on, what matters in my life).

From your stored memories and what you've learned about me, export only real-world facts: who I am, what I do, and what I'm involved in. Preserve my wording when you're quoting something I said about myself.

Do not include rules about how you (the assistant) should write, format, reply, or behave — no "always/never" chat instructions, tone preferences for AI, or similar. Skip generic LLM meta-preferences entirely.

## Categories (output in this order):

1. **Identity**: Name (or how I refer to myself), age or life stage if known, where I live or work from, timezone if known, languages, education, family and important relationships, hobbies and interests.

2. **Work**: Current job or role, employer or freelance focus, past roles worth knowing, industries and skill areas that describe what I actually do.

3. **Projects**: Things I've built, lead, or seriously committed to — one entry per project: what it is, status, and any decisions or context that matter. Start each entry with the project name or a short label.

4. **Life context**: Anything else factual that helps interpret my calendar, mail, or activity (e.g. recurring commitments, key people or orgs, travel patterns, side responsibilities). Keep it concrete, not wishlists.

## Format:

Use section headers for each category. Within each category, one fact per line, oldest first when you have a sense of time. Use:

[YYYY-MM-DD] - Fact here.

If no date is known, use [unknown].

## Output:

- Wrap the entire export in a single code block for easy copying.
- After the code block, say whether this is everything you have or if more factual detail might exist."""

# Line the user types alone to finish pasting (TTY); avoids ``stdin.read()`` waiting for EOF after Enter.
_PROFILE_PASTE_END_SENTINEL = "---END---"


def _print_llm_assistant_import_hint() -> None:
    ui.say("")
    ui.say(
        "[accent]Import from another AI[/] [muted](optional)[/]\n"
        "[muted]Copy only the plain text between the rules below — no box borders. "
        "Paste it into ChatGPT, Claude, Gemini, or similar. "
        "Then paste the reply in the terminal as instructed.[/]"
    )
    ui.muted_line("─" * 76)
    ui.console.print(_LLM_ASSISTANT_EXPORT_PROMPT, markup=False, highlight=False, end="")
    if not _LLM_ASSISTANT_EXPORT_PROMPT.endswith("\n"):
        ui.console.print()
    ui.muted_line("─" * 76)


def _read_multiline_profile_from_tty() -> str:
    """Read pasted profile until a sentinel line or EOF (``stdin.read()`` never ends on TTY after one Enter)."""
    ui.muted_line(
        f"When finished pasting, type [bold]{_PROFILE_PASTE_END_SENTINEL}[/] on its own line and press Enter. "
        "Or use Ctrl-D (macOS/Linux) or Ctrl-Z then Enter (Windows) on a new line. "
        "Outer ``` fences are stripped automatically."
    )
    lines: list[str] = []
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            ui.warning("Cancelled.")
            return ""
        if not line:
            break
        if line.rstrip("\r\n") == _PROFILE_PASTE_END_SENTINEL:
            break
        lines.append(line)
    return "".join(lines).strip()


def _read_profile_raw_text(
    *, profile_file: Path | None, profile_text: str | None
) -> str:
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
    _print_llm_assistant_import_hint()
    ui.say(
        "\n[accent]Paste[/] your profile [muted](exported facts or free-form: who you are, work, projects, context for your data).[/]"
    )
    return _read_multiline_profile_from_tty()


def _profile_markdown_without_llm(raw: str) -> str:
    """Wrap raw text when no LLM is configured."""
    return f"# User Profile\n\n## Self description\n\n{raw.strip()}\n"


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


async def _structure_profile_markdown(raw, llm) -> str:
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
    config_dir: Path | None = None,
) -> None:
    from datetime import date, datetime

    from pulse.analysis.vault_memory import VaultMemory
    from pulse.connectors import register_all
    from pulse.connectors.registry import ConnectorRegistry
    from pulse.jobs.runners import run_aggregation_job
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema
    from pulse.store.sync_state import SyncStateRepository

    _quiet_noisy_loggers()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config(config_dir=config_dir)

    from pulse.vault.onboarding import ensure_vault_onboarding

    ensure_vault_onboarding(config.vault_path)

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
        ui.warning(
            "No active connectors. Run [cmd]pulse configure[/] → Connectors to enable sources."
        )
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
    result = asyncio.run(
        run_aggregation_job(day=today, database_path=config.database_path)
    )
    ui.muted_line(result.detail)

    # --- Step 4: Initial discovery (if LLM available) ---
    from pulse.llm.factory import (
        create_providers_from_config,
        discovery_model_for_discovery,
        summarization_model_for_source_summaries,
    )

    _, disc_llm = create_providers_from_config(config)

    if disc_llm is not None:
        ui.step("Running initial discovery")
        from pulse.jobs.runners import run_discovery_job
        from pulse.notifications.factory import build_notification_channel

        channel = build_notification_channel(config)

        try:
            result = asyncio.run(
                run_discovery_job(
                    cadence="weekly",
                    target_date=today,
                    database_path=config.database_path,
                    vault_path=config.vault_path,
                    llm=disc_llm,
                    notification_channel=channel,
                    summarization_model=summarization_model_for_source_summaries(config)
                    or "",
                    discovery_model=discovery_model_for_discovery(config) or "",
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
        ui.muted_line(
            "Skipping discovery (configure [llm.summarization] and/or [llm.discovery])."
        )

    ui.success(
        "Pulse initialized! Run [cmd]pulse run[/] to start the server and scheduler."
    )


def _collect_profile(
    vault,
    config,
    *,
    profile_file: Path | None = None,
    profile_text: str | None = None,
) -> None:
    from pulse.llm.factory import create_providers_from_config

    ui.step("User profile")
    ui.muted_line(
        "Describe yourself in free form, or paste a factual export from another chat; "
        "Pulse will structure it for your vault when an Anthropic model is configured."
    )

    raw = _read_profile_raw_text(profile_file=profile_file, profile_text=profile_text)
    raw = _strip_markdown_fences(raw)
    if not raw:
        ui.warning("No profile text provided; skipping profile write.")
        return

    from pulse.llm.anthropic import AnthropicProvider

    summ_llm, disc_llm = create_providers_from_config(config)
    anthropic_llm = next(
        (x for x in (summ_llm, disc_llm) if isinstance(x, AnthropicProvider)), None
    )
    if anthropic_llm is not None:
        ui.say("[accent]Structuring profile[/] with Anthropic…")
        try:
            profile_content = asyncio.run(
                _structure_profile_markdown(raw, anthropic_llm)
            )
        except Exception as e:
            um = user_message_for_anthropic_exception(e)
            if um:
                ui.warning(f"{um} Saving raw text under a single section instead.")
            else:
                ui.warning(
                    f"LLM error ({e}); saving raw text under a single section instead."
                )
            profile_content = _profile_markdown_without_llm(raw)
    else:
        ui.muted_line(
            "No Anthropic LLM in [llm.summarization] / [llm.discovery]; "
            "saving your text under “Self description” (no LLM pass)."
        )
        profile_content = _profile_markdown_without_llm(raw)

    vault.write_config_file("profile.md", profile_content)
    ui.success("Profile saved.")


def _discover(args) -> None:
    from datetime import date

    from pulse.jobs.runners import run_aggregation_job, run_discovery_job
    from pulse.llm.factory import (
        create_providers_from_config,
        discovery_model_for_discovery,
        summarization_model_for_source_summaries,
    )

    config = load_config()
    target = date.fromisoformat(args.date) if args.date else date.today()

    _, disc_llm = create_providers_from_config(config)
    if disc_llm is None:
        ui.error(
            "No discovery LLM configured. Set [llm.discovery] (or [llm.summarization]) in pulse.toml."
        )
        sys.exit(1)

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
                llm=disc_llm,
                summarization_model=summarization_model_for_source_summaries(config)
                or "",
                discovery_model=discovery_model_for_discovery(config) or "",
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


def _status(config_dir: Path | None = None) -> None:
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


def _insights() -> None:
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

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
                ui.warning(
                    "No patterns discovered yet. Run [cmd]pulse discover[/] first."
                )
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


def _test_telegram() -> None:
    from pulse.domain.notifications import Notification
    from pulse.notifications.telegram import TelegramChannel

    config = load_config()

    if not config.telegram_bot_token or not config.telegram_chat_id:
        ui.error(
            "PULSE_TELEGRAM_BOT_TOKEN and PULSE_TELEGRAM_CHAT_ID must be set in pulse.toml or the environment"
        )
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
        name
        for name in config.connectors
        if name in SCOPES_BY_CONNECTOR and config.connectors[name].enabled
    ]

    if not google_connectors:
        ui.error(
            "No Google connectors enabled in pulse.toml. Enable gmail, calendar, or youtube."
        )
        sys.exit(1)

    scopes = auth_manager.get_required_scopes(google_connectors)
    if show_rule:
        ui.rule("Google OAuth")
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
        ui.rule("Spotify OAuth")
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


def _auth_microsoft(*, show_rule: bool = True) -> None:
    config = load_config()

    if not config.microsoft_client_id or not config.microsoft_client_secret:
        ui.error(
            "PULSE_MICROSOFT_CLIENT_ID and PULSE_MICROSOFT_CLIENT_SECRET must be set."
        )
        sys.exit(1)

    token_path = Path(config.database_path).parent / "microsoft_tokens.json"
    auth_manager = MicrosoftAuthManager(
        client_id=config.microsoft_client_id,
        client_secret=config.microsoft_client_secret,
        token_path=token_path,
        tenant_id=config.microsoft_tenant_id or "common",
    )

    active = [
        name
        for name in ("microsoft_mail", "microsoft_calendar")
        if (c := config.connectors.get(name)) is not None and c.enabled
    ]
    if not active:
        ui.error(
            "No Microsoft 365 connectors enabled in pulse.toml. "
            "Enable microsoft_mail and/or microsoft_calendar."
        )
        sys.exit(1)

    scopes = auth_manager.get_required_scopes(active)
    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(scopes, state)

    if show_rule:
        ui.rule("Microsoft 365 OAuth")
    ui.kv_line("Authorizing for", ", ".join(active))
    ui.muted_line("Scopes: " + " ".join(scopes))
    ui.say("[accent]Opening browser[/] for Microsoft sign-in…")
    ui.muted_line(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            returned_state = query.get("state", [None])[0]
            code = query.get("code", [None])[0]

            if returned_state != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - possible CSRF attack.")
                return

            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorization successful! You can close this tab.")
            else:
                err = query.get(
                    "error_description", query.get("error", ["Unknown error"])
                )
                self.send_response(400)
                self.end_headers()
                msg = (err[0] if err else "No code").encode("utf-8", errors="replace")
                self.wfile.write(msg)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", MICROSOFT_AUTH_PORT), CallbackHandler)
    server.handle_request()

    if not received_code:
        ui.error("No authorization code received.")
        sys.exit(1)

    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("Microsoft 365 authorization complete!")


def _auth_github(*, show_rule: bool = True) -> None:
    config = load_config()
    if not config.github_client_id or not config.github_client_secret:
        ui.error("PULSE_GITHUB_CLIENT_ID and PULSE_GITHUB_CLIENT_SECRET must be set.")
        sys.exit(1)
    gh = config.connectors.get("github")
    if gh is None or not gh.enabled:
        ui.error(
            "Enable [connectors.github] in pulse.toml before running GitHub OAuth."
        )
        sys.exit(1)

    token_path = Path(config.database_path).parent / "github_tokens.json"
    auth_manager = GitHubAuthManager(
        client_id=config.github_client_id,
        client_secret=config.github_client_secret,
        token_path=token_path,
    )
    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(GITHUB_SCOPES, state)
    if show_rule:
        ui.rule("GitHub OAuth")
    ui.say("[accent]Opening browser[/] for GitHub authorization…")
    ui.muted_line(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch.")
                return
            code = query.get("code", [None])[0]
            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK - you can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received.")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", GITHUB_AUTH_PORT), CallbackHandler)
    server.handle_request()
    if not received_code:
        ui.error("No authorization code received.")
        sys.exit(1)
    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("GitHub authorization complete!")


def _auth_gitlab(*, show_rule: bool = True) -> None:
    config = load_config()
    if config.gitlab_token:
        ui.error(
            "PULSE_GITLAB_TOKEN is set — OAuth is not used. Unset it to use GitLab OAuth."
        )
        sys.exit(1)
    if not config.gitlab_client_id or not config.gitlab_client_secret:
        ui.error("PULSE_GITLAB_CLIENT_ID and PULSE_GITLAB_CLIENT_SECRET must be set.")
        sys.exit(1)
    gl = config.connectors.get("gitlab")
    if gl is None or not gl.enabled:
        ui.error(
            "Enable [connectors.gitlab] in pulse.toml before running GitLab OAuth."
        )
        sys.exit(1)

    base = _gitlab_base_url(config)
    token_path = Path(config.database_path).parent / "gitlab_tokens.json"
    auth_manager = GitLabAuthManager(
        client_id=config.gitlab_client_id,
        client_secret=config.gitlab_client_secret,
        token_path=token_path,
        base_url=base,
    )
    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(GITLAB_SCOPES, state)
    if show_rule:
        ui.rule("GitLab OAuth")
    ui.kv_line("GitLab base URL", base)
    ui.say("[accent]Opening browser[/] for GitLab authorization…")
    ui.muted_line(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch.")
                return
            code = query.get("code", [None])[0]
            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK - you can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received.")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", GITLAB_AUTH_PORT), CallbackHandler)
    server.handle_request()
    if not received_code:
        ui.error("No authorization code received.")
        sys.exit(1)
    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("GitLab authorization complete!")


def _auth_plaid(*, show_rule: bool = True) -> None:
    config = load_config()
    if not config.plaid_client_id or not config.plaid_secret:
        ui.error("PULSE_PLAID_CLIENT_ID and PULSE_PLAID_SECRET must be set.")
        sys.exit(1)
    pl = config.connectors.get("plaid")
    if pl is None or not pl.enabled:
        ui.error("Enable [connectors.plaid] in pulse.toml before running Plaid Link.")
        sys.exit(1)
    if show_rule:
        ui.rule("Plaid Link")
    ui.say("[accent]Opening browser[/] for Plaid Link (http://localhost:8893/)…")
    token_path = Path(config.database_path).parent / "plaid_tokens.json"
    try:
        run_plaid_link_flow(config, token_path)
    except RuntimeError as e:
        ui.error(str(e))
        sys.exit(1)
    ui.success("Plaid linked — tokens saved beside your database.")


def _auth_oura(*, show_rule: bool = True) -> None:
    config = load_config()
    if (config.oura_personal_access_token or "").strip():
        ui.error(
            "PULSE_OURA_PERSONAL_ACCESS_TOKEN is set — OAuth is not used. Unset it to use Oura OAuth."
        )
        sys.exit(1)
    if not config.oura_client_id or not config.oura_client_secret:
        ui.error("PULSE_OURA_CLIENT_ID and PULSE_OURA_CLIENT_SECRET must be set.")
        sys.exit(1)
    ou = config.connectors.get("oura")
    if ou is None or not ou.enabled:
        ui.error("Enable [connectors.oura] in pulse.toml before running Oura OAuth.")
        sys.exit(1)

    token_path = Path(config.database_path).parent / "oura_tokens.json"
    auth_manager = OuraAuthManager(
        client_id=config.oura_client_id,
        client_secret=config.oura_client_secret,
        token_path=token_path,
    )
    state = secrets.token_urlsafe(32)
    auth_url = auth_manager._get_auth_url(OURA_SCOPES, state)
    if show_rule:
        ui.rule("Oura OAuth")
    ui.say("[accent]Opening browser[/] for Oura authorization…")
    ui.muted_line(f"If it doesn't open, visit: {auth_url}")
    ui.muted_line(
        f"Register redirect URI [bold]http://localhost:{OURA_AUTH_PORT}/callback[/] on your Oura app."
    )
    webbrowser.open(auth_url)

    received_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch.")
                return
            code = query.get("code", [None])[0]
            if code:
                received_code.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK - you can close this tab.")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received.")

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("localhost", OURA_AUTH_PORT), CallbackHandler)
    server.handle_request()
    if not received_code:
        ui.error("No authorization code received.")
        sys.exit(1)
    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("Oura authorization complete!")

"""Argparse entry point for the `pulse` CLI.

Handler implementations live in :mod:`pulse.app.commands` — this module only
builds the parser and dispatches to them. Keeping it thin makes it easy to add
or reorganize subcommands without touching handler logic.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich_argparse import RichHelpFormatter

from pulse.app.cli_ui import SITE_ACCENT, SITE_CREAM, SITE_MUTED_FG
from pulse.app.commands import configure as configure_cmd
from pulse.app.commands import init_cmd, onboard as onboard_cmd, ops, serve
from pulse.app.commands.auth import (
    auth_github,
    auth_google,
    auth_oura,
    auth_plaid,
    auth_spotify,
    test_telegram,
)

logger = logging.getLogger(__name__)


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
            "Always run every onboard auth/link step that applies (Google, Spotify, "
            "GitHub, Plaid, Oura); exit non-zero if a required step fails"
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

    internal_install_parser = subparsers.add_parser(
        "internal-install",
        help="Rich UI for the web install script (pulseagent.dev/install.sh); not needed otherwise.",
    )
    internal_install_parser.add_argument(
        "phase",
        choices=("ready", "noninteractive"),
        help="ready = after pipx install; noninteractive = explain manual onboard",
    )

    pull_parser = subparsers.add_parser(
        "pull",
        parents=[config_parent],
        help="Run connector pull jobs now (omit sources to pull all enabled)",
    )
    pull_parser.add_argument(
        "sources", nargs="*", help="Connectors to pull (default: all)"
    )

    discover_parser = subparsers.add_parser(
        "discover",
        parents=[config_parent],
        help="Run aggregation for a target day",
    )
    discover_parser.add_argument(
        "--cadence",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Unused (kept for CLI compatibility)",
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
        "status",
        parents=[config_parent],
        help="Show database paths, counts, and connector snapshot",
    )
    subparsers.add_parser(
        "insights",
        parents=[config_parent],
        help="List stored discovery patterns (from the database)",
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
        "logs",
        parents=[config_parent],
        help="Print recent rows from the event store (newest first)",
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
        serve.run_server(args)
    elif args.command == "onboard":
        onboard_cmd.onboard(args)
    elif args.command == "internal-install":
        onboard_cmd.internal_install(args)
    elif args.command == "pull":
        serve.pull(args)
    elif args.command == "discover":
        ops.discover(args)
    elif args.command == "configure":
        configure_cmd.configure(
            offer_oauth=True, config_dir=getattr(args, "config_dir", None)
        )
    elif args.command == "init":
        init_cmd.init_profile(
            profile_file=getattr(args, "profile_file", None),
            profile_text=getattr(args, "profile_text", None),
            config_dir=getattr(args, "config_dir", None),
        )
    elif args.command == "status":
        ops.status(config_dir=getattr(args, "config_dir", None))
    elif args.command == "insights":
        ops.insights()
    elif args.command == "logs":
        ops.logs(args)
    elif args.command == "reset":
        ops.reset(args)
    elif args.command == "test-telegram":
        test_telegram()
    else:
        parser.print_help()
        sys.exit(1)


# Backwards-compat re-exports for existing callers / tests that imported names
# from ``pulse.app.cli`` before the commands/ split. New code should import from
# ``pulse.app.commands.*`` directly.
__all__ = [
    "auth_github",
    "auth_google",
    "auth_oura",
    "auth_plaid",
    "auth_spotify",
    "build_parser",
    "main",
    "test_telegram",
]

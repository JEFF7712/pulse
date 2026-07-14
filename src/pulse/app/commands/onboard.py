"""`pulse onboard` (guided first-run) and `pulse internal-install` (install.sh hook)."""

from __future__ import annotations

import sys
from pathlib import Path

from pulse.app import cli_ui as ui
from pulse.app.commands.auth import (
    auth_github,
    auth_google,
    auth_oura,
    auth_plaid,
    auth_spotify,
)
from pulse.app.commands.configure import configure
from pulse.app.commands.init_cmd import init_profile
from pulse.app.commands.serve import run_server
from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import SCOPES_BY_CONNECTOR


def onboard_should_run_google_auth(config: PulseConfig) -> bool:
    if not config.google_client_id or not config.google_client_secret:
        return False
    google_connectors = [
        name
        for name in config.connectors
        if name in SCOPES_BY_CONNECTOR and config.connectors[name].enabled
    ]
    return bool(google_connectors)


def onboard_should_run_spotify_auth(config: PulseConfig) -> bool:
    if not config.spotify_client_id or not config.spotify_client_secret:
        return False
    spot = config.connectors.get("spotify")
    return spot is not None and spot.enabled


def onboard_should_run_github_auth(config: PulseConfig) -> bool:
    if not config.github_client_id or not config.github_client_secret:
        return False
    gh = config.connectors.get("github")
    return gh is not None and gh.enabled


def onboard_should_run_plaid_link(config: PulseConfig) -> bool:
    if not config.plaid_client_id or not config.plaid_secret:
        return False
    pl = config.connectors.get("plaid")
    return pl is not None and pl.enabled


def onboard_should_run_oura_auth(config: PulseConfig) -> bool:
    if (config.oura_personal_access_token or "").strip():
        return False
    if not config.oura_client_id or not config.oura_client_secret:
        return False
    ou = config.connectors.get("oura")
    return ou is not None and ou.enabled


def onboard_print_prerequisites() -> None:
    ui.rule("Before you start")
    ui.muted_line(
        "Run from the directory where your Pulse config lives (usually ``.config/pulse.toml`` or repo-root ``pulse.toml``)."
    )
    ui.muted_line("Install the CLI first (e.g. pip install -e . or uv sync).")
    ui.muted_line("For Google, Spotify, or GitHub, create OAuth apps as needed.")
    ui.muted_line(
        "Local callbacks: Spotify :8888, GitHub :8891, Plaid Link :8893, Oura :8894."
    )


def internal_install(args) -> None:
    """Rich output for ``scripts/install.sh`` (matches normal CLI styling)."""
    phase = args.phase
    if phase == "ready":
        ui.success("pulse-agent installed with pipx")
        ui.kv_line("Command", "pulse")
        ui.muted_line(
            "If «pulse» is not found, open a new shell or run: "
            '[cmd]export PATH="$HOME/.local/bin:$PATH"[/]'
        )
        ui.rule("Setup")
        ui.step("Interactive onboarding")
        ui.muted_line(
            "Configure models, connectors, OAuth, vault — then the server starts briefly."
        )
    elif phase == "noninteractive":
        ui.warning(
            "Skipping interactive onboarding — no usable terminal (stdin is not a TTY)."
        )
        ui.muted_line(
            "SSH in or open a local terminal on this machine, then run: [cmd]pulse onboard[/]"
        )
        ui.muted_line("Then start the server with: [cmd]pulse run[/]")


def onboard_print_next_steps(host: str, port: int) -> None:
    ui.rule("Next steps")
    ui.muted_line("Starting the server — open the app in a browser on this machine:")
    ui.kv_line("URL", f"http://127.0.0.1:{port}/")
    if host not in ("127.0.0.1", "localhost"):
        ui.muted_line(
            f"Listen address is {host} — use your machine's IP or hostname if you browse from elsewhere."
        )
    ui.step("While Pulse is running")
    ui.muted_line("In another terminal: [cmd]pulse status[/]   [cmd]pulse logs[/]")


def onboard(args) -> None:
    """Interactive first-time setup: configure (same hub menus as ``pulse configure``), OAuth, init, then `pulse run`."""
    ui.banner_tagline()
    ui.rule("pulse onboard")
    onboard_print_prerequisites()
    config_dir = getattr(args, "config_dir", None)
    configure(
        offer_oauth=False,
        menu_walkthrough=True,
        suppress_banner=True,
        submenu_exit_label="→ Next",
        config_dir=config_dir,
    )
    config = load_config(config_dir=config_dir)
    strict = args.strict

    ui.onboard_phase("auth google")
    if strict or onboard_should_run_google_auth(config):
        auth_google(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — no Google OAuth client configured or no enabled Gmail / Calendar / YouTube connector."
        )

    ui.onboard_phase("auth spotify")
    if strict or onboard_should_run_spotify_auth(config):
        auth_spotify(show_rule=False)
    else:
        ui.muted_line(
            "Skipping — Spotify client secrets missing, connector disabled, or spotify not in pulse.toml."
        )

    ui.onboard_phase("auth github")
    if strict or onboard_should_run_github_auth(config):
        auth_github(show_rule=False)
    else:
        ui.muted_line("Skipping — GitHub OAuth not needed or not configured.")

    ui.onboard_phase("plaid link")
    if strict or onboard_should_run_plaid_link(config):
        token_path = Path(config.database_path).parent / "plaid_tokens.json"
        if not token_path.exists():
            try:
                auth_plaid(show_rule=False)
            except RuntimeError as e:
                ui.error(str(e))
                if strict:
                    sys.exit(1)
        else:
            ui.muted_line(f"Plaid already linked ({token_path}); skipping Link.")
    else:
        ui.muted_line("Skipping — Plaid not enabled or credentials missing.")

    ui.onboard_phase("auth oura")
    if onboard_should_run_oura_auth(config):
        token_path = Path(config.database_path).parent / "oura_tokens.json"
        if not token_path.exists():
            auth_oura(show_rule=False)
        else:
            ui.muted_line(f"Oura already authorized ({token_path}); skipping.")
    else:
        ui.muted_line(
            "Skipping — Oura not enabled, using PAT, or OAuth client not configured."
        )

    ui.onboard_phase("init")
    init_profile(
        profile_file=getattr(args, "profile_file", None),
        profile_text=getattr(args, "profile_text", None),
    )
    ui.onboard_phase("run")
    onboard_print_next_steps(args.host, args.port)
    run_server(args)

"""Per-connector OAuth / link / test handlers behind `pulse auth` and `pulse test-telegram`."""

from __future__ import annotations

import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pulse.app import cli_ui as ui
from pulse.app.config_loader import load_config
from pulse.connectors.github_auth import (
    GITHUB_AUTH_PORT,
    GITHUB_SCOPES,
    GitHubAuthManager,
)
from pulse.connectors.google_auth import SCOPES_BY_CONNECTOR, GoogleAuthManager
from pulse.connectors.oura_auth import OURA_AUTH_PORT, OURA_SCOPES, OuraAuthManager
from pulse.connectors.plaid_link import run_plaid_link_flow
from pulse.connectors.spotify_auth import (
    SPOTIFY_OAUTH_HOST,
    SPOTIFY_OAUTH_PORT,
    SPOTIFY_SCOPES,
    SpotifyAuthManager,
)


def test_telegram() -> None:
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


def auth_google(*, show_rule: bool = True) -> None:
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


def auth_spotify(*, show_rule: bool = True) -> None:
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

    # Bind the same literal loopback IP that the redirect URI names. Binding
    # "localhost" can resolve to ::1 while the browser follows the redirect to
    # 127.0.0.1, leaving the callback hitting a socket nothing is listening on.
    server = HTTPServer((SPOTIFY_OAUTH_HOST, SPOTIFY_OAUTH_PORT), CallbackHandler)
    server.handle_request()  # Handle single callback request

    if not received_code:
        ui.error("No authorization code received.")
        sys.exit(1)

    tokens = auth_manager._exchange_code(received_code[0])
    auth_manager.save_tokens(tokens)
    ui.success("Spotify authorization complete!")


def auth_github(*, show_rule: bool = True) -> None:
    config = load_config()
    if not config.github_client_id or not config.github_client_secret:
        ui.error("PULSE_GITHUB_CLIENT_ID and PULSE_GITHUB_CLIENT_SECRET must be set.")
        sys.exit(1)
    gh = config.connectors.get("github")
    if gh is None or not gh.enabled:
        ui.error(
            r"Enable \[connectors.github] in pulse.toml before running GitHub OAuth."
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


def auth_plaid(*, show_rule: bool = True) -> None:
    config = load_config()
    if not config.plaid_client_id or not config.plaid_secret:
        ui.error("PULSE_PLAID_CLIENT_ID and PULSE_PLAID_SECRET must be set.")
        sys.exit(1)
    pl = config.connectors.get("plaid")
    if pl is None or not pl.enabled:
        ui.error(
            r"Enable \[connectors.plaid] in pulse.toml before running Plaid Link."
        )
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


def auth_oura(*, show_rule: bool = True) -> None:
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
        ui.error(
            r"Enable \[connectors.oura] in pulse.toml before running Oura OAuth."
        )
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


# ----------------------------------------------------------------------
# `pulse auth` — direct entry point
# ----------------------------------------------------------------------

_AUTH_RUNNERS = {
    "google": auth_google,
    "github": auth_github,
    "spotify": auth_spotify,
    "plaid": auth_plaid,
    "oura": auth_oura,
}


def _print_auth_status(config) -> None:
    from pulse.app.commands.auth_registry import all_status

    ui.rule("pulse auth")
    for st in all_status(config):
        src = st.source
        mark = {"authorized": "✓", "needs credentials": "✗", "not authorized": "○"}[
            st.state
        ]
        covered = ", ".join(st.enabled_connectors) or "no enabled connectors"
        ui.say(f"  [bold]{mark} {src.name:8}[/] {st.state:18} {src.label}")
        ui.muted_line(f"      serves: {covered}")
        if st.missing_config:
            ui.muted_line(f"      set in pulse.toml: {', '.join(st.missing_config)}")
        if src.redirect_uri:
            ui.muted_line(f"      redirect URI: {src.redirect_uri}")
        if src.notes:
            ui.muted_line(f"      note: {src.notes}")
    ui.muted_line("")
    ui.muted_line("Run 'pulse auth <source>' to authorize one.")


def auth(args) -> None:
    """`pulse auth [source]` — status with no argument, run one flow with an argument."""
    from pulse.app.commands.auth_registry import resolve, source_names, status_for

    config = load_config(config_dir=getattr(args, "config_dir", None))
    requested = getattr(args, "source", None)

    if not requested:
        _print_auth_status(config)
        return

    source = resolve(requested)
    if source is None:
        ui.error(
            f"Unknown source {requested!r}. Choose from: {', '.join(source_names())}."
        )
        sys.exit(1)

    st = status_for(source, config)
    # Check prerequisites before opening a browser: failing after the tab opens is
    # confusing, and the useful message (what to set, what URI to register) is
    # exactly what the user needs before visiting the provider's dashboard.
    if st.missing_config:
        ui.error(
            f"{source.label} needs these set in pulse.toml first: "
            f"{', '.join(st.missing_config)}"
        )
        if source.redirect_uri:
            ui.muted_line(f"Register redirect URI: {source.redirect_uri}")
        sys.exit(1)

    if source.needs_enabled:
        cc = config.connectors.get(source.needs_enabled)
        if cc is None or not cc.enabled:
            ui.error(
                rf"Enable \[connectors.{source.needs_enabled}] in pulse.toml before "
                f"running this flow."
            )
            sys.exit(1)

    if st.authorized:
        ui.warning(f"{source.label} is already authorized ({st.token_path}).")
        ui.muted_line("Continuing will replace the stored tokens.")

    if source.redirect_uri:
        ui.muted_line(f"Redirect URI registered on the provider must be: {source.redirect_uri}")

    _AUTH_RUNNERS[source.name]()

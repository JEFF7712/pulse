import argparse
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pulse.app.config_loader import load_config
from pulse.connectors.google_auth import GoogleAuthManager, SCOPES_BY_CONNECTOR
from pulse.connectors.spotify_auth import SpotifyAuthManager, SPOTIFY_SCOPES, REDIRECT_URI


def main() -> None:
    parser = argparse.ArgumentParser(prog="pulse", description="Pulse CLI")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="provider")
    auth_subparsers.add_parser("google", help="Authorize Google services")
    auth_subparsers.add_parser("spotify", help="Authorize Spotify")

    args = parser.parse_args()

    if args.command == "auth" and args.provider == "google":
        _auth_google()
    elif args.command == "auth" and args.provider == "spotify":
        _auth_spotify()
    else:
        parser.print_help()
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

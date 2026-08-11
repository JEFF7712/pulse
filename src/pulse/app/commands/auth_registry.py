"""What can be authorized, what each one needs, and whether it already is.

Auth used to be reachable only by walking the `pulse configure` menu, which meant a
crash anywhere in that menu took the auth flow with it, and re-authorizing an expired
token required navigating an editor for settings you did not want to change. This
describes the sources declaratively so `pulse auth` can check prerequisites and report
status without launching a browser first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pulse.app.config import PulseConfig


@dataclass(frozen=True, slots=True)
class AuthSource:
    name: str
    label: str
    token_file: str
    # Config fields that must be set before the flow can start.
    requires: tuple[str, ...] = ()
    # Redirect URI the provider's app settings must contain, when it has one.
    redirect_uri: str | None = None
    # Connectors this set of tokens serves.
    covers: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    notes: str = ""
    # Connector must be enabled before the flow is meaningful (Plaid Link).
    needs_enabled: str | None = None


def _sources() -> list[AuthSource]:
    from pulse.connectors.github_auth import GITHUB_REDIRECT_URI
    from pulse.connectors.oura_auth import OURA_AUTH_PORT
    from pulse.connectors.plaid_link import PLAID_LINK_PORT
    from pulse.connectors.spotify_auth import REDIRECT_URI as SPOTIFY_REDIRECT_URI

    return [
        AuthSource(
            name="google",
            label="Google (Gmail, Calendar, YouTube)",
            token_file="google_tokens.json",
            requires=("google_client_id", "google_client_secret"),
            covers=("gmail", "calendar", "youtube"),
            aliases=("gmail", "calendar", "youtube"),
            notes="One token set serves all three Google connectors.",
        ),
        AuthSource(
            name="github",
            label="GitHub",
            token_file="github_tokens.json",
            requires=("github_client_id", "github_client_secret"),
            redirect_uri=GITHUB_REDIRECT_URI,
            covers=("github",),
        ),
        AuthSource(
            name="spotify",
            label="Spotify",
            token_file="spotify_tokens.json",
            requires=("spotify_client_id", "spotify_client_secret"),
            redirect_uri=SPOTIFY_REDIRECT_URI,
            covers=("spotify",),
            notes=(
                "Spotify rejects the hostname 'localhost' as insecure; the redirect "
                "URI must be registered with the literal loopback IP."
            ),
        ),
        AuthSource(
            name="plaid",
            label="Plaid (bank transactions)",
            token_file="plaid_tokens.json",
            requires=("plaid_client_id", "plaid_secret"),
            redirect_uri=f"http://localhost:{PLAID_LINK_PORT}/",
            covers=("plaid",),
            needs_enabled="plaid",
            notes="Sandbox returns fake transactions; real data needs production access.",
        ),
        AuthSource(
            name="oura",
            label="Oura (sleep, readiness, activity)",
            token_file="oura_tokens.json",
            requires=(),
            redirect_uri=f"http://localhost:{OURA_AUTH_PORT}/callback",
            covers=("oura",),
            notes="A personal access token skips OAuth entirely.",
        ),
    ]


AUTH_SOURCES: list[AuthSource] = _sources()


def resolve(name: str) -> AuthSource | None:
    key = (name or "").strip().lower()
    for source in AUTH_SOURCES:
        if key == source.name or key in source.aliases:
            return source
    return None


def source_names() -> list[str]:
    return [s.name for s in AUTH_SOURCES]


@dataclass(slots=True)
class AuthStatus:
    source: AuthSource
    authorized: bool
    missing_config: list[str] = field(default_factory=list)
    enabled_connectors: list[str] = field(default_factory=list)
    token_path: Path | None = None

    @property
    def ready(self) -> bool:
        return not self.missing_config

    @property
    def state(self) -> str:
        if self.authorized:
            return "authorized"
        if self.missing_config:
            return "needs credentials"
        return "not authorized"


def _has_token(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        import json

        blob = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(blob, dict):
        return False
    return bool(
        blob.get("access_token") or blob.get("refresh_token") or blob.get("token")
    )


def status_for(source: AuthSource, config: PulseConfig) -> AuthStatus:
    token_path = Path(config.database_path).parent / source.token_file
    missing = [f for f in source.requires if not getattr(config, f, None)]
    # Oura accepts a personal access token instead of an OAuth client.
    if source.name == "oura" and config.oura_personal_access_token:
        missing = []
    enabled = [
        c
        for c in source.covers
        if (config.connectors.get(c) and config.connectors[c].enabled)
    ]
    return AuthStatus(
        source=source,
        authorized=_has_token(token_path),
        missing_config=missing,
        enabled_connectors=enabled,
        token_path=token_path,
    )


def all_status(config: PulseConfig) -> list[AuthStatus]:
    return [status_for(s, config) for s in AUTH_SOURCES]

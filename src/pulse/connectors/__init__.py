from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector
    from pulse.connectors.youtube import YouTubeConnector
    from pulse.connectors.spotify import SpotifyConnector
    from pulse.connectors.spotify_auth import SpotifyAuthManager
    from pulse.connectors.github_auth import GitHubAuthManager
    from pulse.connectors.github import GitHubConnector
    from pulse.connectors.plaid_connector import PlaidConnector
    from pulse.connectors.browser import BrowserHistoryConnector

    # Build shared Google auth manager if credentials are configured
    auth_manager: GoogleAuthManager | None = None
    if config.google_client_id and config.google_client_secret:
        token_path = Path(config.database_path).parent / "google_tokens.json"
        auth_manager = GoogleAuthManager(
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            token_path=token_path,
        )

    registry.register_pull("gmail", lambda: GmailConnector(auth_manager=auth_manager))
    registry.register_pull(
        "calendar", lambda: GoogleCalendarConnector(auth_manager=auth_manager)
    )
    registry.register_pull(
        "youtube", lambda: YouTubeConnector(auth_manager=auth_manager)
    )

    # Spotify
    spotify_auth: SpotifyAuthManager | None = None
    if config.spotify_client_id and config.spotify_client_secret:
        token_path = Path(config.database_path).parent / "spotify_tokens.json"
        spotify_auth = SpotifyAuthManager(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            token_path=token_path,
        )
    registry.register_pull(
        "spotify", lambda: SpotifyConnector(auth_manager=spotify_auth)
    )

    gh_auth: GitHubAuthManager | None = None
    if config.github_client_id and config.github_client_secret:
        gh_token = Path(config.database_path).parent / "github_tokens.json"
        gh_auth = GitHubAuthManager(
            client_id=config.github_client_id,
            client_secret=config.github_client_secret,
            token_path=gh_token,
        )
    registry.register_pull("github", lambda: GitHubConnector(auth_manager=gh_auth))

    plaid_cc = config.connectors.get("plaid")
    plaid_raw = plaid_cc.model_dump(mode="python") if plaid_cc else {}
    plaid_omit = bool(
        plaid_raw.get("omit_amounts_in_summary")
        or plaid_raw.get("omit_amounts_in_digest", False)
    )
    plaid_token_path = Path(config.database_path).parent / "plaid_tokens.json"
    registry.register_pull(
        "plaid",
        lambda: PlaidConnector(
            config=config,
            token_path=plaid_token_path,
            omit_amounts_in_summary=plaid_omit,
        ),
    )

    # Browser history
    browser_config = config.connectors.get("browser")
    browser_type = (
        getattr(browser_config, "browser", "chrome") if browser_config else "chrome"
    )
    db_path = getattr(browser_config, "db_path", None) if browser_config else None
    registry.register_pull(
        "browser",
        lambda: BrowserHistoryConnector(
            browser=browser_type,
            db_path=db_path,
        ),
    )

    from pulse.connectors.oura_auth import OuraAuthManager
    from pulse.connectors.oura import OuraConnector

    oura_auth: OuraAuthManager | None = None
    if (
        config.oura_client_id
        and config.oura_client_secret
        and not (config.oura_personal_access_token or "").strip()
    ):
        oura_tok = Path(config.database_path).parent / "oura_tokens.json"
        oura_auth = OuraAuthManager(
            client_id=config.oura_client_id,
            client_secret=config.oura_client_secret,
            token_path=oura_tok,
        )

    oura_pat = (config.oura_personal_access_token or "").strip() or None
    registry.register_pull(
        "oura",
        lambda: OuraConnector(
            auth_manager=oura_auth,
            personal_access_token=oura_pat,
        ),
    )

from pathlib import Path

from pulse.app.config import ConnectorConfig, PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def _urls_from_connector_config(cc: ConnectorConfig | None) -> list[str]:
    if cc is None:
        return []
    raw = cc.model_dump(mode="python").get("urls")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(u).strip() for u in raw if u and str(u).strip()]
    return []


def register_all(registry: ConnectorRegistry, config: PulseConfig) -> None:
    from pulse.connectors.gmail import GmailConnector
    from pulse.connectors.calendar import GoogleCalendarConnector
    from pulse.connectors.youtube import YouTubeConnector
    from pulse.connectors.spotify import SpotifyConnector
    from pulse.connectors.spotify_auth import SpotifyAuthManager
    from pulse.connectors.browser import BrowserHistoryConnector
    from pulse.connectors.feeds import FeedConnector

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
    registry.register_pull("calendar", lambda: GoogleCalendarConnector(auth_manager=auth_manager))
    registry.register_pull("youtube", lambda: YouTubeConnector(auth_manager=auth_manager))

    # Spotify
    spotify_auth: SpotifyAuthManager | None = None
    if config.spotify_client_id and config.spotify_client_secret:
        token_path = Path(config.database_path).parent / "spotify_tokens.json"
        spotify_auth = SpotifyAuthManager(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            token_path=token_path,
        )
    registry.register_pull("spotify", lambda: SpotifyConnector(auth_manager=spotify_auth))

    # Browser history
    browser_config = config.connectors.get("browser")
    browser_type = getattr(browser_config, "browser", "chrome") if browser_config else "chrome"
    db_path = getattr(browser_config, "db_path", None) if browser_config else None
    registry.register_pull("browser", lambda: BrowserHistoryConnector(
        browser=browser_type, db_path=db_path,
    ))

    feeds_cfg = config.connectors.get("feeds")
    feed_urls = _urls_from_connector_config(feeds_cfg)
    registry.register_pull(
        "feeds",
        lambda u=feed_urls: FeedConnector(urls=u),
    )

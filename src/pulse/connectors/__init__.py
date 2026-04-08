from pathlib import Path

from pulse.app.config import ConnectorConfig, PulseConfig
from pulse.connectors.google_auth import GoogleAuthManager
from pulse.connectors.registry import ConnectorRegistry


def _notion_database_ids(cc: ConnectorConfig | None) -> list[str]:
    if cc is None:
        return []
    raw = cc.model_dump(mode="python").get("database_ids")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


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
    from pulse.connectors.microsoft_auth import MicrosoftAuthManager
    from pulse.connectors.microsoft_mail import MicrosoftMailConnector
    from pulse.connectors.microsoft_calendar import MicrosoftCalendarConnector
    from pulse.connectors.github_auth import GitHubAuthManager
    from pulse.connectors.github import GitHubConnector
    from pulse.connectors.gitlab_auth import GitLabAuthManager
    from pulse.connectors.gitlab import GitLabConnector
    from pulse.connectors.plaid_connector import PlaidConnector
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

    ms_auth: MicrosoftAuthManager | None = None
    if config.microsoft_client_id and config.microsoft_client_secret:
        ms_token = Path(config.database_path).parent / "microsoft_tokens.json"
        ms_auth = MicrosoftAuthManager(
            client_id=config.microsoft_client_id,
            client_secret=config.microsoft_client_secret,
            token_path=ms_token,
            tenant_id=config.microsoft_tenant_id or "common",
        )

    def _microsoft_calendar_factory() -> MicrosoftCalendarConnector:
        cc = config.connectors.get("microsoft_calendar")
        cid = "primary"
        if cc is not None:
            raw = cc.model_dump(mode="python").get("calendar_id")
            if isinstance(raw, str) and raw.strip():
                cid = raw.strip()
        return MicrosoftCalendarConnector(auth_manager=ms_auth, calendar_id=cid)

    registry.register_pull(
        "microsoft_mail",
        lambda: MicrosoftMailConnector(auth_manager=ms_auth),
    )
    registry.register_pull("microsoft_calendar", _microsoft_calendar_factory)

    gh_auth: GitHubAuthManager | None = None
    if config.github_client_id and config.github_client_secret:
        gh_token = Path(config.database_path).parent / "github_tokens.json"
        gh_auth = GitHubAuthManager(
            client_id=config.github_client_id,
            client_secret=config.github_client_secret,
            token_path=gh_token,
        )
    registry.register_pull("github", lambda: GitHubConnector(auth_manager=gh_auth))

    gl_base = "https://gitlab.com"
    gl_cc = config.connectors.get("gitlab")
    if gl_cc is not None:
        raw_base = gl_cc.model_dump(mode="python").get("gitlab_base_url")
        if isinstance(raw_base, str) and raw_base.strip():
            gl_base = raw_base.strip().rstrip("/")

    gl_auth: GitLabAuthManager | None = None
    if (
        not config.gitlab_token
        and config.gitlab_client_id
        and config.gitlab_client_secret
    ):
        gl_tok_path = Path(config.database_path).parent / "gitlab_tokens.json"
        gl_auth = GitLabAuthManager(
            client_id=config.gitlab_client_id,
            client_secret=config.gitlab_client_secret,
            token_path=gl_tok_path,
            base_url=gl_base,
        )

    def _gitlab_factory() -> GitLabConnector:
        return GitLabConnector(
            base_url=gl_base,
            personal_token=config.gitlab_token,
            auth_manager=None if config.gitlab_token else gl_auth,
        )

    registry.register_pull("gitlab", _gitlab_factory)

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

    from pulse.connectors.companion import CompanionConnector
    from pulse.connectors.linear import LinearConnector
    from pulse.connectors.notion import NotionConnector

    registry.register_pull(
        "linear",
        lambda: LinearConnector(api_key=config.linear_api_key),
    )

    from pulse.connectors.oura_auth import OuraAuthManager
    from pulse.connectors.oura import OuraConnector

    notion_cc = config.connectors.get("notion")
    notion_db_ids = _notion_database_ids(notion_cc)
    registry.register_pull(
        "notion",
        lambda: NotionConnector(
            token=config.notion_token,
            database_ids=notion_db_ids,
        ),
    )

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

    registry.register_push("companion", CompanionConnector)

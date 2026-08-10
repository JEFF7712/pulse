from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    poll_interval: str = "15m"


class SemanticConfig(BaseModel):
    enabled: bool = False
    model: str = "minishlab/potion-base-32M"


_DEFAULT_DISCOVERY_PROMPT = (
    "Find things about me that I do not already know. Start with "
    "pulse_longitudinal_profile for structure over months — composition drift, whether "
    "my interests rotate rather than accumulate, sleep phase, what holds my attention "
    "versus what I only touch in fragments, and what quietly stopped. Read "
    "pulse_pattern_list first so you do not re-report a known finding, and "
    "pulse_vault_read('04-Config/profile.md') for what I believe about myself; the gap "
    "between that and the data is often the finding. Use pulse_query_events to check any "
    "hypothesis. Do not tell me what I did recently — I remember. Record with "
    "pulse_pattern_upsert only a finding I could not have seen myself. If nothing clears "
    "that bar, record nothing and stop; that is a normal outcome, not a failure."
)


class DiscoveryConfig(BaseModel):
    """Discovery of long-horizon structure the user cannot see about themselves."""

    enabled: bool = False
    command: list[str] = ["claude", "-p"]
    prompt: str = _DEFAULT_DISCOVERY_PROMPT
    at: str = "09:00"  # local HH:MM in config timezone
    timeout_seconds: int = 900
    # Structure over months does not change daily, and re-deriving it every morning
    # only rediscovers what is already on file. Weekly is the useful floor.
    interval_days: int = 7
    # How far back the profile reaches. A year lets rotation and seasonality show;
    # a quarter is the practical minimum for any of it to exist.
    history_days: int = 400


class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    ntfy_topic: str | None = None
    ntfy_base_url: str | None = None
    notification_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    slack_webhook_url: str | None = None
    pushover_user_key: str | None = None
    pushover_api_token: str | None = None
    gotify_url: str | None = None
    gotify_app_token: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    notify_on_job_failure: bool = False
    job_failure_alert_cooldown: str = "6h"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str | None = None
    oura_client_id: str | None = None
    oura_client_secret: str | None = None
    oura_personal_access_token: str | None = None
    connectors: dict[str, ConnectorConfig] = {}
    semantic: SemanticConfig | None = None
    discovery: DiscoveryConfig | None = None


# Backward compatibility alias
Settings = PulseConfig

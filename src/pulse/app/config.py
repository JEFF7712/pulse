from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    poll_interval: str = "15m"


class SemanticConfig(BaseModel):
    enabled: bool = False
    model: str = "minishlab/potion-base-32M"


_DEFAULT_DISCOVERY_PROMPT = (
    "Look for patterns in my Pulse data that are not already recorded. Start with "
    "pulse_change_surface to see what actually changed, then pulse_pattern_list to see "
    "what is already known. Use pulse_query_events to investigate anything that looks "
    "worth understanding. Record a finding with pulse_pattern_upsert only if it is new, "
    "grounded in specific events, and would not be obvious to me. If nothing clears that "
    "bar, record nothing and stop — that is a normal outcome, not a failure."
)


class DiscoveryConfig(BaseModel):
    """Pattern discovery. The agent is woken only when the data actually moved."""

    enabled: bool = False
    command: list[str] = ["claude", "-p"]
    prompt: str = _DEFAULT_DISCOVERY_PROMPT
    at: str = "09:00"  # local HH:MM in config timezone; when the *check* runs
    timeout_seconds: int = 900
    # A pattern needs repetition to exist, so the window is a week, not a day.
    window_days: int = 7
    baseline_days: int = 56


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

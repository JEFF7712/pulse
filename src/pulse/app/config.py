from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    poll_interval: str = "15m"


class SemanticConfig(BaseModel):
    enabled: bool = False
    model: str = "minishlab/potion-base-32M"


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


# Backward compatibility alias
Settings = PulseConfig

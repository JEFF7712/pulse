from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    poll_interval: str = "15m"


class LLMRoleConfig(BaseModel):
    """Per-role LLM settings. Omit `provider` to inherit `[llm] provider` in pulse.toml."""

    provider: str | None = None  # "anthropic" | "openai" | "gemini" | "ollama"
    model: str
    base_url: str | None = None


class LLMConfig(BaseModel):
    """Optional defaults for all roles: set `provider` once, then only `model` per role."""

    provider: str | None = None
    base_url: str | None = None
    summarization: LLMRoleConfig | None = None
    discovery: LLMRoleConfig | None = None
    corrections: LLMRoleConfig | None = None


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
    corrections_webhook_secret: str | None = None
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
    notify_on_corrections_backlog: bool = False
    corrections_backlog_alert_cooldown: str = "12h"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant_id: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    gitlab_client_id: str | None = None
    gitlab_client_secret: str | None = None
    gitlab_token: str | None = None
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str | None = None
    oura_client_id: str | None = None
    oura_client_secret: str | None = None
    oura_personal_access_token: str | None = None
    notion_token: str | None = None
    linear_api_key: str | None = None
    fcm_service_account_path: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    llm: LLMConfig | None = None
    connectors: dict[str, ConnectorConfig] = {}


# Backward compatibility alias
Settings = PulseConfig

from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    poll_interval: str = "15m"


class LLMRoleConfig(BaseModel):
    provider: str  # "anthropic" | "openai" | "gemini" | "ollama"
    model: str
    base_url: str | None = None


class LLMConfig(BaseModel):
    summarization: LLMRoleConfig | None = None
    discovery: LLMRoleConfig | None = None
    corrections: LLMRoleConfig | None = None


class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
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
    anthropic_api_key: str | None = None
    summarization_model: str = "claude-haiku-4-5-20251001"
    discovery_model: str = "claude-sonnet-4-6"
    llm: LLMConfig | None = None
    connectors: dict[str, ConnectorConfig] = {}


# Backward compatibility alias
Settings = PulseConfig

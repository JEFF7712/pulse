from pydantic import BaseModel


class Settings(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

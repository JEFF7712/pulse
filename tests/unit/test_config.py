from pulse.app.config import Settings


def test_settings_defaults_match_scaffold_expectations():
    settings = Settings()

    assert settings.database_path == "data/pulse.db"
    assert settings.vault_path == "Pulse-Vault"
    assert settings.timezone == "UTC"
    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
    assert settings.google_client_id is None
    assert settings.google_client_secret is None

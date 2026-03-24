from pulse.app.config import Settings
from pulse.app.dependencies import get_settings


def test_settings_defaults_match_scaffold_expectations():
    settings = Settings()

    assert settings.database_path == "data/pulse.db"
    assert settings.vault_path == "Pulse-Vault"
    assert settings.timezone == "UTC"
    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
    assert settings.google_client_id is None
    assert settings.google_client_secret is None


def test_get_settings_reads_pulse_prefixed_environment_variables(monkeypatch):
    monkeypatch.setenv("PULSE_DATABASE_PATH", "/tmp/pulse-test.db")
    monkeypatch.setenv("PULSE_TIMEZONE", "America/New_York")

    settings = get_settings()

    assert settings.database_path == "/tmp/pulse-test.db"
    assert settings.timezone == "America/New_York"

from pulse.app.config import (
    PulseConfig,
    ConnectorConfig,
    Settings,
)


def test_pulse_config_defaults_match_original_settings():
    config = PulseConfig()
    assert config.database_path == "data/pulse.db"
    assert config.vault_path == "Pulse-Vault"
    assert config.timezone == "UTC"
    assert config.telegram_bot_token is None
    assert config.telegram_chat_id is None
    assert config.google_client_id is None
    assert config.google_client_secret is None
    assert config.connectors == {}


def test_settings_alias_is_pulse_config():
    assert Settings is PulseConfig


def test_connector_config_defaults():
    cc = ConnectorConfig()
    assert cc.enabled is False
    assert cc.poll_interval == "15m"


def test_connector_config_accepts_extra_fields():
    cc = ConnectorConfig(enabled=True, poll_interval="30m", custom_key="value")
    assert cc.custom_key == "value"


def test_pulse_config_with_connectors():
    config = PulseConfig(
        connectors={
            "gmail": ConnectorConfig(enabled=True, poll_interval="10m"),
            "calendar": ConnectorConfig(enabled=False),
        }
    )
    assert config.connectors["gmail"].enabled is True
    assert config.connectors["gmail"].poll_interval == "10m"
    assert config.connectors["calendar"].enabled is False


def test_get_settings_reads_pulse_prefixed_environment_variables(monkeypatch):
    from pulse.app.dependencies import get_settings

    monkeypatch.setenv("PULSE_DATABASE_PATH", "/tmp/pulse-test.db")
    monkeypatch.setenv("PULSE_TIMEZONE", "America/New_York")
    settings = get_settings()
    assert settings.database_path == "/tmp/pulse-test.db"
    assert settings.timezone == "America/New_York"

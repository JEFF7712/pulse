from pulse.app.config import (
    PulseConfig,
    ConnectorConfig,
    Settings,
    LLMRoleConfig,
    LLMConfig,
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
    assert cc.enabled is True
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


def test_pulse_config_parses_llm_config():
    from pulse.app.config import PulseConfig, LLMRoleConfig, LLMConfig

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(
                provider="ollama",
                model="llama3.3",
                base_url="http://localhost:11434/v1",
            ),
            discovery=LLMRoleConfig(
                provider="anthropic",
                model="claude-sonnet-4-6",
            ),
        )
    )
    assert config.llm.summarization.provider == "ollama"
    assert config.llm.summarization.model == "llama3.3"
    assert config.llm.summarization.base_url == "http://localhost:11434/v1"
    assert config.llm.discovery.provider == "anthropic"
    assert config.llm.discovery.model == "claude-sonnet-4-6"
    assert config.llm.discovery.base_url is None


def test_pulse_config_llm_default_provider_and_models_only():
    """`[llm] provider` with per-role `model` only (same vendor, different models)."""
    from pulse.app.config import PulseConfig, LLMRoleConfig, LLMConfig

    config = PulseConfig(
        llm=LLMConfig(
            provider="anthropic",
            summarization=LLMRoleConfig(model="claude-haiku-4-5-20251001"),
            discovery=LLMRoleConfig(model="claude-opus-4-6"),
        )
    )
    assert config.llm.provider == "anthropic"
    assert config.llm.summarization.provider is None
    assert config.llm.summarization.model == "claude-haiku-4-5-20251001"
    assert config.llm.discovery.model == "claude-opus-4-6"


def test_pulse_config_parses_corrections_llm_role():
    config = PulseConfig(
        llm=LLMConfig(
            corrections=LLMRoleConfig(
                provider="openai",
                model="gpt-5.4-mini",
                base_url="https://api.openai.com/v1",
            )
        )
    )

    assert config.llm is not None
    assert config.llm.corrections is not None
    assert config.llm.corrections.provider == "openai"
    assert config.llm.corrections.model == "gpt-5.4-mini"
    assert config.llm.corrections.base_url == "https://api.openai.com/v1"


def test_pulse_config_llm_defaults_to_none():
    config = PulseConfig()
    assert config.llm is None

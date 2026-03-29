import pytest

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.app.config_loader import load_config, PulseConfigNotFoundError


def test_load_config_from_toml(tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text("""
[connectors.gmail]
enabled = true
poll_interval = "10m"

[connectors.youtube]
enabled = false
poll_interval = "1h"
""")
    config = load_config(config_path=toml_file)
    assert config.connectors["gmail"].enabled is True
    assert config.connectors["gmail"].poll_interval == "10m"
    assert config.connectors["youtube"].enabled is False


def test_load_config_omitted_connector_enabled_defaults_false(tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text("""
[connectors.gmail]
poll_interval = "10m"
""")
    config = load_config(config_path=toml_file)
    assert config.connectors["gmail"].enabled is False
    assert config.connectors["gmail"].poll_interval == "10m"


def test_load_config_env_overrides_defaults(monkeypatch, tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text("")
    monkeypatch.setenv("PULSE_DATABASE_PATH", "/custom/db.sqlite")
    monkeypatch.setenv("PULSE_TIMEZONE", "US/Eastern")
    config = load_config(config_path=toml_file)
    assert config.database_path == "/custom/db.sqlite"
    assert config.timezone == "US/Eastern"


def test_load_config_returns_defaults_when_no_toml(tmp_path):
    missing_path = tmp_path / "nonexistent.toml"
    config = load_config(config_path=missing_path)
    assert config.database_path == "data/pulse.db"
    assert config.connectors == {}


def test_load_config_uses_data_dir_defaults_when_paths_are_not_set(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "pulse.toml").write_text("")
    monkeypatch.setenv("PULSE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    config = load_config()

    assert config.database_path == str((tmp_path / "xdg-data" / "pulse" / "pulse.db").resolve())
    assert config.vault_path == str((tmp_path / "xdg-data" / "pulse" / "Pulse-Vault").resolve())


def test_load_config_can_require_existing_config_files(tmp_path):
    with pytest.raises(PulseConfigNotFoundError) as exc:
        load_config(config_dir=tmp_path / "missing", require_files=True)

    assert "pulse configure" in str(exc.value)
    assert "PULSE_CONFIG_DIR" in str(exc.value)

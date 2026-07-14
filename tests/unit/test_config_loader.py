import os

import pytest

from pulse.app.config import PulseConfig, ConnectorConfig
from pulse.app.config_loader import (
    default_pulse_config_path,
    load_config,
    PulseConfigNotFoundError,
)


@pytest.fixture(autouse=True)
def _clear_pulse_related_env(monkeypatch):
    """Strip Pulse-related env vars so host exports do not affect load_config tests."""
    for k in list(os.environ.keys()):
        if k.startswith("PULSE_"):
            monkeypatch.delenv(k, raising=False)


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


def test_load_config_uses_data_dir_defaults_when_paths_are_not_set(
    tmp_path, monkeypatch
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "pulse.toml").write_text("")
    monkeypatch.setenv("PULSE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    config = load_config()

    assert config.database_path == str(
        (tmp_path / "xdg-data" / "pulse" / "pulse.db").resolve()
    )
    assert config.vault_path == str(
        (tmp_path / "xdg-data" / "pulse" / "Pulse-Vault").resolve()
    )


def test_load_config_can_require_existing_config_files(tmp_path):
    with pytest.raises(PulseConfigNotFoundError) as exc:
        load_config(config_dir=tmp_path / "missing", require_files=True)

    assert "pulse configure" in str(exc.value)
    assert "PULSE_CONFIG_DIR" in str(exc.value)


def test_load_config_root_scalars_from_toml(tmp_path):
    toml_file = tmp_path / "pulse.toml"
    toml_file.write_text(
        """
database_path = "custom.db"
telegram_bot_token = "tok"

[connectors.gmail]
enabled = false
poll_interval = "15m"
"""
    )
    config = load_config(config_path=toml_file)
    assert config.database_path == "custom.db"
    assert config.telegram_bot_token == "tok"
    assert config.connectors["gmail"].enabled is False


def test_load_config_resolves_relative_storage_paths_against_config_dir(
    tmp_path, monkeypatch
):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "pulse.toml").write_text(
        """
database_path = "data/pulse.db"
vault_path = "Pulse-Vault"
"""
    )
    monkeypatch.setenv("PULSE_CONFIG_DIR", str(config_dir))

    config = load_config()

    assert config.database_path == str((config_dir / "data" / "pulse.db").resolve())
    assert config.vault_path == str((config_dir / "Pulse-Vault").resolve())


def test_default_pulse_config_path_prefers_dot_config(tmp_path):
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "pulse.toml").write_text(
        'timezone = "UTC"\n', encoding="utf-8"
    )
    (tmp_path / "pulse.toml").write_text(
        'timezone = "Europe/London"\n', encoding="utf-8"
    )
    assert (
        default_pulse_config_path(cwd=tmp_path) == tmp_path / ".config" / "pulse.toml"
    )


def test_default_pulse_config_path_repo_root_pulse_toml(tmp_path):
    (tmp_path / "pulse.toml").write_text('timezone = "US/Eastern"\n', encoding="utf-8")
    assert default_pulse_config_path(cwd=tmp_path) == tmp_path / "pulse.toml"


def test_default_pulse_config_path_new_install_target(tmp_path):
    assert (
        default_pulse_config_path(cwd=tmp_path) == tmp_path / ".config" / "pulse.toml"
    )


def test_default_pulse_config_path_pulse_config_file(monkeypatch, tmp_path):
    custom = tmp_path / "my" / "pulse.toml"
    custom.parent.mkdir(parents=True)
    custom.write_text('timezone = "UTC"\n', encoding="utf-8")
    monkeypatch.setenv("PULSE_CONFIG_FILE", str(custom))
    assert default_pulse_config_path(cwd=tmp_path) == custom


def test_default_pulse_config_path_pulse_config_dir(monkeypatch, tmp_path):
    d = tmp_path / "cfg"
    d.mkdir()
    f = d / "pulse.toml"
    f.write_text('timezone = "UTC"\n', encoding="utf-8")
    monkeypatch.setenv("PULSE_CONFIG_DIR", str(d))
    assert default_pulse_config_path(cwd=tmp_path) == f

import pytest

from pathlib import Path

from pulse.app.paths import PulsePaths
from pulse.app import cli
from pulse.app.commands import configure as configure_cmd
from pulse.app.commands import ops


def test_default_env_values_use_resolved_data_dir(tmp_path):
    paths = PulsePaths(
        config_dir=(tmp_path / "config").resolve(),
        data_dir=(tmp_path / "data").resolve(),
        toml_path=(tmp_path / "config" / "pulse.toml").resolve(),
    )

    values = configure_cmd.default_env_values(paths)

    assert values["PULSE_DATABASE_PATH"] == str((tmp_path / "data" / "pulse.db").resolve())
    assert values["PULSE_VAULT_PATH"] == str((tmp_path / "data" / "Pulse-Vault").resolve())


def test_build_parser_accepts_config_dir_for_run() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")


def test_build_parser_accepts_config_dir_for_configure() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["configure", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")


def test_status_shows_actionable_message_when_config_missing(tmp_path, capsys):
    with pytest.raises(SystemExit):
        ops.status(config_dir=tmp_path / "missing")

    out = capsys.readouterr().out
    assert "pulse configure" in out
    assert "PULSE_CONFIG_DIR" in out

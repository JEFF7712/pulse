from pathlib import Path

from pulse.app.config_loader import load_config
from pulse.app.paths import resolve_pulse_paths


def test_resolve_pulse_paths_prefers_explicit_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    paths = resolve_pulse_paths(config_dir=tmp_path / "chosen")

    assert paths.config_dir == (tmp_path / "chosen").resolve()
    assert paths.toml_path == paths.config_dir / "pulse.toml"
    assert paths.data_dir == (tmp_path / "xdg-data" / "pulse").resolve()


def test_resolve_pulse_paths_uses_legacy_cwd_when_config_files_exist(tmp_path):
    (tmp_path / "pulse.toml").write_text("")
    paths = resolve_pulse_paths(cwd=tmp_path)
    assert paths.config_dir == tmp_path.resolve()

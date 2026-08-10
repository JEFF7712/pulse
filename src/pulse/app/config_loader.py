import os
import tomllib
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.app.paths import resolve_pulse_paths


def default_pulse_config_path(*, cwd: Path | None = None) -> Path:
    """Path to the main Pulse config file (TOML).

    Resolution (first match wins):

    1. ``PULSE_CONFIG_FILE`` — absolute or relative path to the TOML file.
    2. ``PULSE_CONFIG_DIR`` / ``pulse.toml`` — config directory (e.g. XDG-style layout).
    3. ``<cwd>/.config/pulse.toml`` if that file exists.
    4. ``<cwd>/pulse.toml`` if that file exists (repository-root fallback).
    5. Otherwise ``<cwd>/.config/pulse.toml`` (default for new installs; parent dir created on write).

    ``cwd`` defaults to :func:`pathlib.Path.cwd`.
    """
    base = cwd or Path.cwd()
    env_file = (os.environ.get("PULSE_CONFIG_FILE") or "").strip()
    if env_file:
        return Path(env_file).expanduser()
    env_dir = (os.environ.get("PULSE_CONFIG_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser() / "pulse.toml"
    dot_config = base / ".config" / "pulse.toml"
    root_toml = base / "pulse.toml"
    if dot_config.is_file():
        return dot_config
    if root_toml.is_file():
        return root_toml
    return dot_config


class PulseConfigNotFoundError(FileNotFoundError):
    pass


_PROACTIVE_REMOVED = (
    "[proactive] was replaced by [discovery]. The scheduled daily review is gone: "
    "Pulse now runs a deterministic change check first and only wakes an agent when "
    "the data actually moved, notifying you when a new pattern is recorded rather "
    "than every morning. Rename the section to [discovery] (command, prompt, at and "
    "timeout_seconds carry over; window_days and baseline_days are new), or delete it "
    "to turn the feature off."
)


def _reject_removed_sections(file_values: dict) -> None:
    if "proactive" in file_values:
        raise ValueError(_PROACTIVE_REMOVED)


def _env_vars_for_config(environ: dict[str, str]) -> dict:
    """Extract PULSE_* keys from an env-like mapping, returning config field names."""
    result = {}
    for field_name in PulseConfig.model_fields:
        if field_name == "connectors":
            continue
        value = environ.get(f"PULSE_{field_name.upper()}")
        if value is not None:
            result[field_name] = value
    return result


def _resolve_relative_storage_paths(merged: dict, *, base_dir: Path) -> None:
    for field_name in ("database_path", "vault_path"):
        raw_value = merged.get(field_name)
        if raw_value is None:
            continue
        path = Path(raw_value).expanduser()
        if path.is_absolute():
            merged[field_name] = str(path.resolve())
            continue
        merged[field_name] = str((base_dir / path).resolve())


def load_config(
    config_path: Path | None = None,
    config_dir: Path | None = None,
    require_files: bool = False,
) -> PulseConfig:
    # When a direct config_path is supplied (legacy/test usage), skip path resolution
    # and fall back to the old hardcoded defaults for database_path and vault_path.
    if config_path is not None:
        file_values: dict = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                file_values = tomllib.load(f)

        _reject_removed_sections(file_values)
        env_values = _env_vars_for_config(os.environ)
        merged = {**file_values, **env_values}
        return PulseConfig(**merged)

    # Install-safe path: resolve config directory, read pulse.toml, overlay env vars.
    paths = resolve_pulse_paths(config_dir=config_dir)

    if require_files and not paths.toml_path.exists():
        raise PulseConfigNotFoundError(
            f"No Pulse config found in {paths.config_dir}. Run 'pulse configure' or set PULSE_CONFIG_DIR."
        )

    file_values = {}
    if paths.toml_path.exists():
        with open(paths.toml_path, "rb") as f:
            file_values = tomllib.load(f)

    _reject_removed_sections(file_values)
    env_values = _env_vars_for_config(os.environ)

    defaults = {
        "database_path": str(paths.data_dir / "pulse.db"),
        "vault_path": str(paths.data_dir / "Pulse-Vault"),
        "timezone": "UTC",
    }
    merged = {**defaults, **file_values, **env_values}
    _resolve_relative_storage_paths(merged, base_dir=paths.config_dir)

    return PulseConfig(**merged)

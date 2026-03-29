import os
import tomllib
from pathlib import Path

from dotenv import dotenv_values

from pulse.app.config import PulseConfig
from pulse.app.paths import resolve_pulse_paths


class PulseConfigNotFoundError(FileNotFoundError):
    pass


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


def load_config(
    config_path: Path | None = None,
    config_dir: Path | None = None,
    require_files: bool = False,
) -> PulseConfig:
    # When a direct config_path is supplied (legacy/test usage), skip path resolution
    # and fall back to the old hardcoded defaults for database_path and vault_path.
    # load_dotenv() is intentionally omitted here: all production callers use the
    # install-safe path (no config_path), which handles .env loading via dotenv_values().
    if config_path is not None:
        file_values: dict = {}
        if config_path.exists():
            with open(config_path, "rb") as f:
                file_values = tomllib.load(f)

        env_values = _env_vars_for_config(os.environ)
        merged = {**file_values, **env_values}
        return PulseConfig(**merged)

    # Install-safe path resolution path.
    # Use dotenv_values() rather than load_dotenv() so that .env file values
    # are merged into the config without permanently mutating os.environ (which
    # can leak across tests and between invocations).
    paths = resolve_pulse_paths(config_dir=config_dir)

    if require_files and not paths.env_path.exists() and not paths.toml_path.exists():
        raise PulseConfigNotFoundError(
            f"No Pulse config found in {paths.config_dir}. Run 'pulse configure' or set PULSE_CONFIG_DIR."
        )

    dot_env_values = _env_vars_for_config(dotenv_values(paths.env_path))

    file_values = {}
    if paths.toml_path.exists():
        with open(paths.toml_path, "rb") as f:
            file_values = tomllib.load(f)

    env_values = _env_vars_for_config(os.environ)

    defaults = {
        "database_path": str(paths.data_dir / "pulse.db"),
        "vault_path": str(paths.data_dir / "Pulse-Vault"),
        "timezone": "UTC",
    }
    merged = {**defaults, **dot_env_values, **file_values, **env_values}
    return PulseConfig(**merged)

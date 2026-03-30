import os
import tomllib
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.app.paths import resolve_pulse_paths

# Vendor env names (no PULSE_ prefix) used by many tools; fill config when unset in file / PULSE_*.
_VENDOR_API_KEY_ENV = (
    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    ("OPENAI_API_KEY", "openai_api_key"),
    ("GEMINI_API_KEY", "gemini_api_key"),
)


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


def _apply_vendor_env(merged: dict) -> None:
    """Fill vendor API key fields from bare env var names when still empty."""
    for env_name, field_name in _VENDOR_API_KEY_ENV:
        current = merged.get(field_name)
        if current is not None and str(current).strip():
            continue
        if (v := os.environ.get(env_name)) is not None and str(v).strip():
            merged[field_name] = v


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

        env_values = _env_vars_for_config(os.environ)
        merged = {**file_values, **env_values}
        _apply_vendor_env(merged)
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

    env_values = _env_vars_for_config(os.environ)

    defaults = {
        "database_path": str(paths.data_dir / "pulse.db"),
        "vault_path": str(paths.data_dir / "Pulse-Vault"),
        "timezone": "UTC",
    }
    merged = {**defaults, **file_values, **env_values}
    _apply_vendor_env(merged)

    return PulseConfig(**merged)

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class PulsePaths:
    config_dir: Path
    data_dir: Path
    toml_path: Path


def resolve_pulse_paths(config_dir: Path | None = None, cwd: Path | None = None) -> PulsePaths:
    cwd = (cwd or Path.cwd()).resolve()
    explicit = config_dir or os.environ.get("PULSE_CONFIG_DIR")
    if explicit is not None:
        resolved_config = Path(explicit).expanduser().resolve()
    elif (cwd / "pulse.toml").exists():
        resolved_config = cwd
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        resolved_config = (xdg_config / "pulse").resolve()

    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    data_dir = (xdg_data / "pulse").resolve()
    return PulsePaths(
        config_dir=resolved_config,
        data_dir=data_dir,
        toml_path=resolved_config / "pulse.toml",
    )

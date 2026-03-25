import os
import tomllib
from pathlib import Path

from pulse.app.config import PulseConfig


def load_config(config_path: Path | None = None) -> PulseConfig:
    if config_path is None:
        config_path = Path("pulse.toml")

    file_values: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            file_values = tomllib.load(f)

    env_values = {
        field_name: value
        for field_name in PulseConfig.model_fields
        if field_name != "connectors"
        and (value := os.environ.get(f"PULSE_{field_name.upper()}")) is not None
    }

    merged = {**file_values, **env_values}
    return PulseConfig(**merged)

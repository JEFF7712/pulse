import os

from pulse.app.config import Settings


def get_settings() -> Settings:
    values = {
        field_name: value
        for field_name in Settings.model_fields
        if (value := os.environ.get(f"PULSE_{field_name.upper()}")) is not None
    }
    return Settings(**values)

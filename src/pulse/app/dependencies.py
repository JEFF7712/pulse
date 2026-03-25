from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config

# Keep backward compat
from pulse.app.config import Settings  # noqa: F401


def get_config() -> PulseConfig:
    return load_config()


# Backward compatibility alias
def get_settings() -> PulseConfig:
    return get_config()

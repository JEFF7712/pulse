"""`pulse configure` must never damage config it does not manage.

It rewrites the whole document from a parsed dict, so any section it fails to model
correctly is silently destroyed on save — and the damage only surfaces later, when
Pulse refuses to start.
"""

import tomllib
from pathlib import Path

from pulse.app.commands.configure.toml_io import (
    _pulse_config_to_working_env,
    _save_pulse_settings,
)
from pulse.app.config_loader import load_config

ORIGINAL = '''# Pulse configuration
database_path = "data/pulse.db"
vault_path = "Pulse-Vault"
timezone = "America/Chicago"
telegram_bot_token = "tok"
telegram_chat_id = "123"

[connectors.gmail]
enabled = true
poll_interval = "15m"

[connectors.spotify]
enabled = true
poll_interval = "30m"

[semantic]
enabled = true
model = "/home/user/models/potion-base-32M"

[discovery]
enabled = true
command = ["agent", "-p", "--model", "cursor-grok-4.5-high"]
at = "09:00"
timeout_seconds = 900
interval_days = 7
history_days = 400
prompt = """Line one.

Line two with a "quoted" bit and a \\\\ backslash."""
'''


def _resave(tmp_path: Path) -> Path:
    """Run the exact save path `pulse configure` uses."""
    toml_path = tmp_path / "pulse.toml"
    toml_path.write_text(ORIGINAL)
    config = load_config(config_path=toml_path)
    _save_pulse_settings(toml_path, _pulse_config_to_working_env(config))
    return toml_path


def test_sub_model_sections_survive_a_configure_save(tmp_path: Path):
    """The regression: [semantic] and [discovery] were flattened to root scalars
    holding `str(model)` — the Python repr — which then failed to load at all."""
    toml_path = _resave(tmp_path)
    raw = toml_path.read_text()

    assert "[semantic]" in raw
    assert "[discovery]" in raw
    # the repr signature that used to be written
    assert "enabled=True" not in raw
    assert 'semantic = "' not in raw
    assert 'discovery = "' not in raw


def test_saved_document_parses_and_keeps_every_value(tmp_path: Path):
    toml_path = _resave(tmp_path)
    parsed = tomllib.loads(toml_path.read_text())

    assert parsed["semantic"] == {
        "enabled": True,
        "model": "/home/user/models/potion-base-32M",
    }
    disc = parsed["discovery"]
    assert disc["command"] == ["agent", "-p", "--model", "cursor-grok-4.5-high"]
    assert disc["interval_days"] == 7
    assert disc["history_days"] == 400
    assert disc["at"] == "09:00"


def test_a_multiline_prompt_survives_verbatim(tmp_path: Path):
    """A raw newline is illegal in a TOML basic string; unescaped it produced a
    document that would not parse back."""
    toml_path = _resave(tmp_path)
    reloaded = load_config(config_path=toml_path)

    assert reloaded.discovery is not None
    prompt = reloaded.discovery.prompt
    assert prompt.startswith("Line one.")
    assert "\n" in prompt
    assert '"quoted"' in prompt
    assert "\\ backslash" in prompt


def test_config_still_loads_after_save(tmp_path: Path):
    toml_path = _resave(tmp_path)
    reloaded = load_config(config_path=toml_path)

    assert reloaded.semantic is not None and reloaded.semantic.enabled is True
    assert reloaded.discovery is not None and reloaded.discovery.enabled is True
    assert reloaded.connectors["spotify"].enabled is True
    assert reloaded.telegram_chat_id == "123"


def test_saving_twice_is_stable(tmp_path: Path):
    """A round trip that drifts would corrupt config a little on every visit."""
    toml_path = _resave(tmp_path)
    once = toml_path.read_text()
    config = load_config(config_path=toml_path)
    _save_pulse_settings(toml_path, _pulse_config_to_working_env(config))

    assert toml_path.read_text() == once


def test_nested_field_names_are_derived_from_the_model(tmp_path: Path):
    """Hard-coding the list would let a newly added sub-model reintroduce the bug."""
    from pulse.app.commands.configure.constants import (
        _PULSE_NESTED_FIELD_NAMES,
        _PULSE_ROOT_FIELD_NAMES,
    )

    assert "semantic" in _PULSE_NESTED_FIELD_NAMES
    assert "discovery" in _PULSE_NESTED_FIELD_NAMES
    assert not (_PULSE_NESTED_FIELD_NAMES & _PULSE_ROOT_FIELD_NAMES)
    assert "telegram_chat_id" in _PULSE_ROOT_FIELD_NAMES

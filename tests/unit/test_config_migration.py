import pytest

from pulse.app.config_loader import load_config


def test_removed_proactive_section_fails_loudly(tmp_path):
    """Silently ignoring the old section would leave the user believing their daily
    review was still configured while nothing ran."""
    cfg = tmp_path / "pulse.toml"
    cfg.write_text(
        '[proactive]\nenabled = true\ncommand = ["claude", "-p"]\nat = "08:00"\n'
    )

    with pytest.raises(ValueError) as exc:
        load_config(config_path=cfg)

    message = str(exc.value)
    assert "[discovery]" in message
    assert "window_days" in message


def test_discovery_section_loads(tmp_path):
    cfg = tmp_path / "pulse.toml"
    cfg.write_text(
        '[discovery]\nenabled = true\ncommand = ["claude", "-p"]\n'
        'at = "09:00"\nwindow_days = 14\n'
    )

    config = load_config(config_path=cfg)

    assert config.discovery is not None
    assert config.discovery.enabled is True
    assert config.discovery.window_days == 14
    assert config.discovery.baseline_days == 56  # default


def test_config_without_discovery_is_valid(tmp_path):
    cfg = tmp_path / "pulse.toml"
    cfg.write_text('timezone = "UTC"\n')
    assert load_config(config_path=cfg).discovery is None

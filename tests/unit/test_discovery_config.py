from pulse.app.config import DiscoveryConfig, PulseConfig


def test_discovery_defaults_off():
    cfg = PulseConfig()
    assert cfg.discovery is None or cfg.discovery.enabled is False


def test_discovery_config_fields():
    dc = DiscoveryConfig(enabled=True, command=["claude", "-p"], at="09:30")
    assert dc.enabled is True
    assert dc.command == ["claude", "-p"]
    assert dc.at == "09:30"


def test_discovery_defaults():
    d = DiscoveryConfig()
    assert d.command == ["claude", "-p"]
    assert d.at == "09:00"
    # a pattern needs repetition, so the default window is a week, not a day
    assert d.window_days == 7
    assert d.baseline_days == 56
    assert "pulse_change_surface" in d.prompt
    assert "pulse_pattern_upsert" in d.prompt

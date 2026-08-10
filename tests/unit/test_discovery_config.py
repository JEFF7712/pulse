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
    # structure over months does not change daily; weekly is the useful floor
    assert d.interval_days == 7
    assert d.history_days == 400
    assert "pulse_longitudinal_profile" in d.prompt
    assert "pulse_pattern_upsert" in d.prompt
    # the whole point: do not read the day back to the user
    assert "do not already know" in d.prompt.lower()

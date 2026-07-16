from pulse.app.config import PulseConfig, ProactiveConfig


def test_proactive_defaults_off():
    cfg = PulseConfig()
    assert cfg.proactive is None or cfg.proactive.enabled is False


def test_proactive_config_fields():
    pc = ProactiveConfig(enabled=True, command=["claude", "-p"], at="09:30")
    assert pc.enabled is True
    assert pc.command == ["claude", "-p"]
    assert pc.at == "09:30"
    # defaults
    d = ProactiveConfig()
    assert d.command == ["claude", "-p"]
    assert d.at == "08:00"
    assert "review" in d.prompt.lower()

from pulse.app.config import PulseConfig, ProactiveConfig
from pulse.jobs.scheduler import build_scheduler


def test_proactive_job_registered_when_enabled():
    cfg = PulseConfig(proactive=ProactiveConfig(enabled=True, at="07:15"))
    sched = build_scheduler(config=cfg)
    assert sched.get_job("proactive") is not None


def test_proactive_job_absent_when_disabled():
    sched = build_scheduler(config=PulseConfig())
    assert sched.get_job("proactive") is None

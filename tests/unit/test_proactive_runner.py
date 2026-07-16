import asyncio
from pulse.app.config import PulseConfig, ProactiveConfig
from pulse.jobs.proactive import run_proactive_review


class _RecordingChannel:
    def __init__(self):
        self.sent = []

    def send(self, notification):
        self.sent.append(notification)
        return True


def test_run_proactive_invokes_command_and_delivers(tmp_path):
    async def fake_runner(argv, timeout):
        assert argv[:2] == ["echo-agent", "-p"]
        assert "review" in argv[-1].lower()
        return "You slept 4h and shipped 12 commits — consider resting."

    channel = _RecordingChannel()
    config = PulseConfig(
        proactive=ProactiveConfig(enabled=True, command=["echo-agent", "-p"])
    )
    result = asyncio.run(
        run_proactive_review(config, channel=channel, runner=fake_runner)
    )
    assert result is True
    assert len(channel.sent) == 1
    assert "shipped 12 commits" in channel.sent[0].body


def test_run_proactive_noops_when_disabled():
    config = PulseConfig(proactive=ProactiveConfig(enabled=False))
    called = False

    async def fake_runner(argv, timeout):
        nonlocal called
        called = True
        return "x"

    result = asyncio.run(
        run_proactive_review(config, channel=_RecordingChannel(), runner=fake_runner)
    )
    assert result is False and called is False


def test_run_proactive_noops_on_empty_agent_output():
    async def fake_runner(argv, timeout):
        return "   "

    channel = _RecordingChannel()
    config = PulseConfig(proactive=ProactiveConfig(enabled=True))
    result = asyncio.run(
        run_proactive_review(config, channel=channel, runner=fake_runner)
    )
    assert result is False and channel.sent == []

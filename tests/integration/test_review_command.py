import asyncio

from pulse.app.commands.ops import _run_review
from pulse.app.config import ProactiveConfig, PulseConfig


class _RecordingChannel:
    def __init__(self):
        self.sent = []

    def send(self, notification):
        self.sent.append(notification)
        return True


def test_run_review_delivers_even_when_schedule_disabled():
    """On-demand review ignores the schedule enabled gate."""

    async def fake_runner(argv, timeout):
        assert argv[:2] == ["echo-agent", "-p"]
        return "Notable: you skipped lunch three days running."

    channel = _RecordingChannel()
    config = PulseConfig(
        proactive=ProactiveConfig(enabled=False, command=["echo-agent", "-p"])
    )
    delivered, message = asyncio.run(
        _run_review(config, channel=channel, runner=fake_runner)
    )
    assert delivered is True
    assert "skipped lunch" in message
    assert len(channel.sent) == 1


def test_run_review_defaults_proactive_when_none():
    async def fake_runner(argv, timeout):
        return "Nothing notable."

    channel = _RecordingChannel()
    config = PulseConfig(proactive=None)
    delivered, message = asyncio.run(
        _run_review(config, channel=channel, runner=fake_runner)
    )
    assert delivered is True
    assert len(channel.sent) == 1


def test_run_review_errors_on_empty_command():
    async def fake_runner(argv, timeout):
        return "should not run"

    channel = _RecordingChannel()
    config = PulseConfig(proactive=ProactiveConfig(enabled=True, command=[]))
    delivered, message = asyncio.run(
        _run_review(config, channel=channel, runner=fake_runner)
    )
    assert delivered is False
    assert "command" in message.lower()
    assert channel.sent == []

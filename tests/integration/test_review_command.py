import asyncio

from pulse.app.commands.ops import _run_review
from pulse.app.config import DiscoveryConfig, PulseConfig

PATTERN = """---
pulse: true
type: pattern
slug: credit-transfer
---

# Pattern: Credit Transfer Underway

**Status:** active
**Confidence:** 0.6
**First seen:** 2026-08-09
**Last updated:** 2026-08-09

## Observation
Parchment transcript ordering appeared alongside Moraine Valley self-service.

## Evidence Log
- 38 visits to parchment.com

## Trend
stable

## User Notes
_None yet._
"""


class _RecordingChannel:
    def __init__(self):
        self.sent = []

    def send(self, notification):
        self.sent.append(notification)
        return True


def _config(tmp_path, **kw):
    patterns = tmp_path / "02-Insights" / "patterns"
    patterns.mkdir(parents=True, exist_ok=True)
    kw.setdefault("command", ["echo-agent", "-p"])
    return PulseConfig(
        vault_path=str(tmp_path),
        database_path=str(tmp_path / "pulse.db"),
        discovery=DiscoveryConfig(**kw),
    )


def _writer(tmp_path, slug="credit-transfer", content=PATTERN):
    """A fake agent that records a pattern, the way a real one would via MCP."""

    async def runner(argv, timeout):
        assert argv[:2] == ["echo-agent", "-p"]
        (tmp_path / "02-Insights" / "patterns" / f"{slug}.md").write_text(content)
        return "some prose the user should never see"

    return runner


def test_on_demand_review_runs_even_when_the_schedule_is_off(tmp_path):
    channel = _RecordingChannel()
    config = _config(tmp_path, enabled=False)

    recorded, message = asyncio.run(
        _run_review(config, channel=channel, runner=_writer(tmp_path))
    )

    assert recorded is True
    assert len(channel.sent) == 1
    assert "Credit Transfer Underway" in channel.sent[0].body


def test_notification_describes_the_pattern_not_the_agent_prose(tmp_path):
    """The whole point of the rewrite: the push reports what was recorded, so an
    agent that rambles without recording anything produces silence."""
    channel = _RecordingChannel()
    config = _config(tmp_path, enabled=True)

    asyncio.run(_run_review(config, channel=channel, runner=_writer(tmp_path)))

    body = channel.sent[0].body
    assert "some prose the user should never see" not in body
    assert "Parchment transcript ordering" in body


def test_agent_that_records_nothing_sends_nothing(tmp_path):
    async def chatty_runner(argv, timeout):
        return "Today you sent 5 emails and had 3 meetings. Productive day!"

    channel = _RecordingChannel()
    config = _config(tmp_path, enabled=True)

    recorded, message = asyncio.run(
        _run_review(config, channel=channel, runner=chatty_runner)
    )

    assert recorded is False
    assert channel.sent == []
    assert "No new patterns" in message


def test_rerunning_an_unchanged_pattern_sends_nothing(tmp_path):
    """A second pass that re-writes the same finding is not a new insight."""
    channel = _RecordingChannel()
    config = _config(tmp_path, enabled=True)

    asyncio.run(_run_review(config, channel=channel, runner=_writer(tmp_path)))
    assert len(channel.sent) == 1

    recorded, _ = asyncio.run(
        _run_review(config, channel=channel, runner=_writer(tmp_path))
    )
    assert recorded is False
    assert len(channel.sent) == 1


def test_defaults_are_used_when_discovery_is_unset(tmp_path):
    patterns = tmp_path / "02-Insights" / "patterns"
    patterns.mkdir(parents=True, exist_ok=True)
    config = PulseConfig(
        vault_path=str(tmp_path),
        database_path=str(tmp_path / "pulse.db"),
        discovery=None,
    )

    async def runner(argv, timeout):
        assert argv[0] == "claude"  # default command
        return ""

    recorded, _ = asyncio.run(
        _run_review(config, channel=_RecordingChannel(), runner=runner)
    )
    assert recorded is False


def test_errors_on_empty_command(tmp_path):
    async def runner(argv, timeout):
        raise AssertionError("should not run")

    channel = _RecordingChannel()
    config = _config(tmp_path, enabled=True, command=[])

    recorded, message = asyncio.run(_run_review(config, channel=channel, runner=runner))
    assert recorded is False
    assert "command" in message.lower()
    assert channel.sent == []

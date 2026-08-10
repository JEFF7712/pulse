import asyncio
from datetime import UTC, date, datetime, timedelta

import aiosqlite

from pulse.app.config import DiscoveryConfig, PulseConfig
from pulse.domain.events import Event
from pulse.jobs.discovery import run_discovery
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema

PATTERN = """---
pulse: true
type: pattern
slug: gpu-research
---

# Pattern: GPU Hardware Research

**Status:** active
**Confidence:** 0.5
**First seen:** 2026-08-09
**Last updated:** 2026-08-09

## Observation
Repeated visits to NVIDIA RTX PRO 6000 Blackwell workstation pages.

## Evidence Log
- 2 visits to nvidia.com

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


def _visit(i, domain, when):
    return Event(
        id=f"browser:{domain}:{i}",
        timestamp=when,
        source="browser",
        event_type="browsing.visit",
        data={"url": f"https://{domain}/p{i}", "title": "page"},
    )


async def _seed(db_path, events):
    async with aiosqlite.connect(db_path) as db:
        await bootstrap_schema(db)
        if events:
            await EventRepository(db).upsert_events(events)


def _config(tmp_path, **kw):
    (tmp_path / "02-Insights" / "patterns").mkdir(parents=True, exist_ok=True)
    kw.setdefault("command", ["echo-agent"])
    kw.setdefault("enabled", True)
    return PulseConfig(
        vault_path=str(tmp_path),
        database_path=str(tmp_path / "pulse.db"),
        timezone="UTC",
        discovery=DiscoveryConfig(**kw),
    )


def _writer(tmp_path, content=PATTERN, slug="gpu-research"):
    async def runner(argv, timeout):
        (tmp_path / "02-Insights" / "patterns" / f"{slug}.md").write_text(content)
        return "prose"

    return runner


WINDOW_END = date(2026, 8, 9)


def _quiet_store(tmp_path):
    """A store where the window looks exactly like the baseline."""
    base = datetime(2026, 6, 8, 9, tzinfo=UTC)
    events = [_visit(i, "github.com", base + timedelta(days=i)) for i in range(63)]
    asyncio.run(_seed(tmp_path / "pulse.db", events))


def _changed_store(tmp_path):
    """A store where a brand-new domain shows up in the window."""
    base = datetime(2026, 6, 8, 9, tzinfo=UTC)
    events = [_visit(i, "github.com", base + timedelta(days=i)) for i in range(56)]
    win = datetime(2026, 8, 5, 9, tzinfo=UTC)
    events += [
        _visit(100 + i, "parchment.com", win + timedelta(hours=i)) for i in range(6)
    ]
    asyncio.run(_seed(tmp_path / "pulse.db", events))


def test_a_quiet_week_still_runs_but_stays_silent(tmp_path):
    """Findings here are structural and months old, so an uneventful week is no
    reason to skip. Silence has to come from the output gate, not from an input gate,
    or a real long-horizon shift would be missed whenever the week happened to be dull."""
    _quiet_store(tmp_path)
    called = False

    async def runner(argv, timeout):
        nonlocal called
        called = True
        return "nothing structural to report"

    channel = _RecordingChannel()
    changes = asyncio.run(
        run_discovery(
            _config(tmp_path),
            channel=channel,
            runner=runner,
            window_end=WINDOW_END,
        )
    )

    assert called is True
    assert changes.is_empty()
    assert channel.sent == []


def test_changed_window_wakes_the_agent_and_notifies(tmp_path):
    _changed_store(tmp_path)
    channel = _RecordingChannel()

    changes = asyncio.run(
        run_discovery(
            _config(tmp_path),
            channel=channel,
            runner=_writer(tmp_path),
            window_end=WINDOW_END,
        )
    )

    assert changes.created == ["gpu-research"]
    assert len(channel.sent) == 1
    assert "GPU Hardware Research" in channel.sent[0].body
    assert channel.sent[0].category == "discovery"


def test_agent_prose_without_a_recorded_pattern_notifies_nothing(tmp_path):
    _changed_store(tmp_path)

    async def chatty(argv, timeout):
        return "You browsed a lot today. Consider taking a break!"

    channel = _RecordingChannel()
    changes = asyncio.run(
        run_discovery(
            _config(tmp_path),
            channel=channel,
            runner=chatty,
            window_end=WINDOW_END,
        )
    )

    assert changes.is_empty()
    assert channel.sent == []


def test_force_bypasses_the_change_gate(tmp_path):
    _quiet_store(tmp_path)
    channel = _RecordingChannel()

    changes = asyncio.run(
        run_discovery(
            _config(tmp_path),
            channel=channel,
            runner=_writer(tmp_path),
            force=True,
            window_end=WINDOW_END,
        )
    )

    assert changes.created == ["gpu-research"]


def test_disabled_discovery_does_nothing(tmp_path):
    _changed_store(tmp_path)
    called = False

    async def runner(argv, timeout):
        nonlocal called
        called = True
        return ""

    changes = asyncio.run(
        run_discovery(
            _config(tmp_path, enabled=False),
            channel=_RecordingChannel(),
            runner=runner,
            window_end=WINDOW_END,
        )
    )
    assert called is False
    assert changes.is_empty()


def test_agent_failure_is_contained(tmp_path):
    _changed_store(tmp_path)

    async def failing(argv, timeout):
        raise RuntimeError("agent exited 1")

    channel = _RecordingChannel()
    changes = asyncio.run(
        run_discovery(
            _config(tmp_path),
            channel=channel,
            runner=failing,
            window_end=WINDOW_END,
        )
    )
    assert changes.is_empty()
    assert channel.sent == []


def test_second_run_with_the_same_finding_is_silent(tmp_path):
    _changed_store(tmp_path)
    channel = _RecordingChannel()
    cfg = _config(tmp_path)

    asyncio.run(
        run_discovery(
            cfg, channel=channel, runner=_writer(tmp_path), window_end=WINDOW_END
        )
    )
    asyncio.run(
        run_discovery(
            cfg, channel=channel, runner=_writer(tmp_path), window_end=WINDOW_END
        )
    )

    assert len(channel.sent) == 1


def test_notification_title_distinguishes_new_from_updated(tmp_path):
    _changed_store(tmp_path)
    channel = _RecordingChannel()
    cfg = _config(tmp_path)

    asyncio.run(
        run_discovery(
            cfg, channel=channel, runner=_writer(tmp_path), window_end=WINDOW_END
        )
    )
    assert "new pattern" in channel.sent[0].title

    grown = PATTERN.replace(
        "- 2 visits to nvidia.com",
        "- 2 visits to nvidia.com\n- marketplace.nvidia.com added",
    )
    asyncio.run(
        run_discovery(
            cfg,
            channel=channel,
            runner=_writer(tmp_path, content=grown),
            window_end=WINDOW_END,
        )
    )
    assert len(channel.sent) == 2
    assert "updated" in channel.sent[1].title

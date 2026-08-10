"""Discovery: look for structure the user cannot see, notify only on real findings.

The original daily review pushed prose about the day, which the user had just lived and
already remembered. Gating it on "did anything change this week" fixed the volume but
not the substance: a week-scale change is still something they did days ago, so
reporting it is the same restatement wearing a different hat. Recent is not unknown.

So this runs against long-horizon structure — composition drift over months, whether
interests rotate rather than accumulate, circadian phase, what actually holds attention,
what quietly stopped — on a weekly cadence, with no gate on recent activity. A quiet week
is not a reason to skip, and a busy one is no evidence anything is newly knowable.

What keeps the user from being spammed is the novelty gate on the *output*: the
notification is derived from what the agent recorded in the vault, not from what it said.
An agent that produces pages of prose and records nothing produces silence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pulse.analysis.pattern_gate import PatternChanges, diff_patterns, snapshot_patterns
from pulse.analysis.vault_memory import VaultMemory
from pulse.app.config import PulseConfig
from pulse.domain.notifications import Notification, NotificationChannel

logger = logging.getLogger(__name__)


async def _default_runner(argv: list[str], timeout: int) -> str:
    """Run the agent command, return its stdout. Raises on nonzero exit/timeout."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"agent command exited {proc.returncode}: {err.decode(errors='replace')[:500]}"
        )
    return out.decode(errors="replace")


def _today(config: PulseConfig) -> date:
    return datetime.now(ZoneInfo(config.timezone)).date()


def _format_notification(
    changes: PatternChanges, snaps: dict, vault_path: str
) -> Notification:
    lines: list[str] = []
    for slug in changes.created:
        snap = snaps.get(slug)
        title = snap.title if snap else slug
        lines.append(f"NEW: {title}")
        if snap and snap.observation:
            lines.append(f"  {_first_sentence(snap.observation)}")
    for slug in changes.updated:
        snap = snaps.get(slug)
        title = snap.title if snap else slug
        lines.append(f"UPDATED: {title}")
        if snap and snap.observation:
            lines.append(f"  {_first_sentence(snap.observation)}")

    count = len(changes.created) + len(changes.updated)
    title = f"{count} new pattern{'s' if count != 1 else ''}"
    if not changes.created and changes.updated:
        title = f"{count} pattern{'s' if count != 1 else ''} updated"
    return Notification(title=title, body="\n".join(lines), category="discovery")


def _first_sentence(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    for end in (". ", "! ", "? "):
        idx = flat.find(end)
        if 0 < idx < limit:
            return flat[: idx + 1]
    return flat[:limit]


async def run_discovery(
    config: PulseConfig,
    *,
    channel: NotificationChannel | None,
    runner=_default_runner,
    force: bool = False,
    window_end: date | None = None,
) -> PatternChanges:
    """Run one discovery pass. Returns what patterns changed (empty when none did).

    There is deliberately no pre-run gate on recent activity. The findings worth
    surfacing are structural and months old, so a quiet week is not a reason to skip:
    the profile can shift while nothing notable happens, and something happening is no
    evidence that anything is newly *knowable*. What protects the user from noise is
    the novelty gate on the output, not a gate on the input.
    """
    dc = config.discovery
    if dc is None or not dc.enabled:
        return PatternChanges()
    if not dc.command:
        return PatternChanges()

    vault = VaultMemory(config.vault_path)
    before = snapshot_patterns(vault.read_patterns())

    try:
        await runner([*dc.command, dc.prompt], dc.timeout_seconds)
    except Exception:
        logger.exception("discovery agent command failed")
        return PatternChanges()

    after = snapshot_patterns(vault.read_patterns())
    changes = diff_patterns(before, after)

    if changes.is_empty():
        logger.info("discovery: agent recorded no new patterns, nothing to send")
        return changes

    if channel is None:
        logger.info(
            "discovery: %s changed but no notification channel", changes.all_slugs()
        )
        return changes

    try:
        channel.send(_format_notification(changes, after, config.vault_path))
    except Exception:
        logger.exception("failed to deliver discovery notification")
    return changes

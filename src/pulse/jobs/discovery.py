"""Pattern discovery: wake an agent only when something changed, notify only on findings.

The old proactive review fired on a fixed daily schedule with a cold agent and one day
of data, and it notified with whatever prose came back. That guarantees a message every
day, and a day is too short a window for a pattern to exist in, so the message was
necessarily a restatement of the day.

This inverts both halves:

* **Trigger** — a deterministic change surface runs first. No change, no agent, no
  notification, no tokens. Silence is the default and costs nothing.
* **Content** — the notification is derived from what the agent *recorded in the vault*,
  not from what it said. If it wrote no new pattern, the user hears nothing, however
  much prose it produced.
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
    """Run one discovery pass. Returns what changed (empty when nothing did).

    ``force`` skips the change-surface gate, for on-demand runs where the user has
    explicitly asked for a pass regardless of whether anything moved.
    """
    dc = config.discovery
    if dc is None or not dc.enabled:
        return PatternChanges()

    day = window_end or _today(config)

    if not force:
        surface = await _load_surface(config, day, dc)
        if surface is None or surface.is_empty():
            logger.info("discovery: no change surface for %s, skipping agent", day)
            return PatternChanges()
        logger.info("discovery: %d signals on %s", surface.signal_count(), day)

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


async def _load_surface(config: PulseConfig, day: date, dc):
    from pulse.services.change_detection import detect_changes
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    try:
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            return await detect_changes(
                db,
                window_end=day,
                timezone=config.timezone,
                window_days=dc.window_days,
                baseline_days=dc.baseline_days,
            )
    except Exception:
        logger.exception("discovery: change detection failed")
        return None

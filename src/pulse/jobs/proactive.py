from __future__ import annotations

import asyncio
import logging

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
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"agent command exited {proc.returncode}: {err.decode(errors='replace')[:500]}"
        )
    return out.decode(errors="replace")


async def run_proactive_review(
    config: PulseConfig,
    *,
    channel: NotificationChannel | None,
    runner=_default_runner,
) -> bool:
    """Invoke the configured agent to review recent data and deliver the result.

    Returns True if a notification was sent, else False (disabled/no output/no channel).
    """
    pc = config.proactive
    if pc is None or not pc.enabled:
        return False
    if channel is None:
        logger.info("proactive review enabled but no notification channel configured")
        return False

    argv = [*pc.command, pc.prompt]
    try:
        output = await runner(argv, pc.timeout_seconds)
    except Exception:
        logger.exception("proactive agent command failed")
        return False

    body = (output or "").strip()
    if not body:
        return False

    notification = Notification(
        title="Pulse review",
        body=body,
        category="proactive",
    )
    try:
        channel.send(notification)
    except Exception:
        logger.exception("failed to deliver proactive review")
        return False
    return True

"""Shared SQLite state for rate-limited operations alerts (job failures)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger(__name__)


async def is_past_cooldown(
    db: aiosqlite.Connection, job_key: str, cooldown: timedelta, now: datetime
) -> bool:
    """Return True if no prior alert or last alert is older than ``cooldown``."""
    cur = await db.execute(
        "SELECT alerted_at FROM job_failure_alert_state WHERE job_key = ?",
        (job_key,),
    )
    row = await cur.fetchone()
    if not row or not row[0]:
        return True
    try:
        last = datetime.fromisoformat(row[0])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < cooldown:
            logger.debug(
                "Skipping alert for %s (cooldown until %s)",
                job_key,
                last + cooldown,
            )
            return False
    except (TypeError, ValueError):
        logger.warning("Bad alerted_at for job_key=%s; sending alert anyway", job_key)
    return True


async def record_cooldown_fire(
    db: aiosqlite.Connection, job_key: str, now: datetime
) -> None:
    await db.execute(
        """
        INSERT INTO job_failure_alert_state (job_key, alerted_at)
        VALUES (?, ?)
        ON CONFLICT(job_key) DO UPDATE SET alerted_at = excluded.alerted_at
        """,
        (job_key, now.isoformat()),
    )
    await db.commit()

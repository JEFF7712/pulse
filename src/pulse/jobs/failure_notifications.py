"""Optional rate-limited push when scheduled jobs fail (discovery, aggregation, pulls)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pulse.domain.notifications import Notification
from pulse.jobs.intervals import parse_interval
from pulse.notifications.factory import build_notification_channel
from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema

if TYPE_CHECKING:
    from pulse.app.config import PulseConfig

logger = logging.getLogger(__name__)


def _job_failure_body(exc: Exception) -> str:
    from pulse.llm.anthropic_errors import user_message_for_anthropic_exception

    hint = user_message_for_anthropic_exception(exc)
    if hint:
        return hint
    msg = str(exc).strip() or type(exc).__name__
    if len(msg) > 1200:
        msg = msg[:1197] + "..."
    return msg


def _cooldown_delta(config: PulseConfig) -> timedelta:
    raw = (config.job_failure_alert_cooldown or "6h").strip()
    try:
        return parse_interval(raw)
    except ValueError:
        logger.warning(
            "Invalid job_failure_alert_cooldown %r; using 6h",
            raw,
        )
        return parse_interval("6h")


async def notify_scheduled_job_failure(
    config: PulseConfig,
    job_key: str,
    exc: Exception,
) -> None:
    """Send operations notification if enabled, channel exists, and cooldown elapsed."""
    if not config.notify_on_job_failure:
        return

    channel = build_notification_channel(config)
    if channel is None:
        logger.debug(
            "notify_on_job_failure is true but no notification channels are configured; "
            "skipping alert for %s",
            job_key,
        )
        return

    cooldown = _cooldown_delta(config)
    now = datetime.now(timezone.utc)

    async with connect_db(config.database_path) as db:
        await bootstrap_schema(db)
        cur = await db.execute(
            "SELECT alerted_at FROM job_failure_alert_state WHERE job_key = ?",
            (job_key,),
        )
        row = await cur.fetchone()
        if row and row[0]:
            try:
                last = datetime.fromisoformat(row[0])
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now - last < cooldown:
                    logger.debug(
                        "Skipping job failure alert for %s (cooldown until %s)",
                        job_key,
                        last + cooldown,
                    )
                    return
            except (TypeError, ValueError):
                logger.warning(
                    "Bad alerted_at for job_key=%s; sending alert anyway", job_key
                )

        title = f"Pulse: {job_key} failed"
        body = _job_failure_body(exc)
        notification = Notification(
            title=title,
            body=body,
            category="operations",
            priority="high",
        )
        try:
            channel.send(notification)
        except Exception:
            logger.exception("Failed to send job failure notification for %s", job_key)
            return

        await db.execute(
            """
            INSERT INTO job_failure_alert_state (job_key, alerted_at)
            VALUES (?, ?)
            ON CONFLICT(job_key) DO UPDATE SET alerted_at = excluded.alerted_at
            """,
            (job_key, now.isoformat()),
        )
        await db.commit()

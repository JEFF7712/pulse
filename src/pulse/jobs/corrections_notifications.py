"""Optional rate-limited alert when correction applications need human attention."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pulse.domain.notifications import Notification
from pulse.jobs.alert_cooldown import is_past_cooldown, record_cooldown_fire
from pulse.jobs.intervals import parse_interval
from pulse.notifications.factory import build_notification_channel
from pulse.store.correction_applications import CorrectionApplicationRepository
from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema

if TYPE_CHECKING:
    from pulse.app.config import PulseConfig

logger = logging.getLogger(__name__)

_CORRECTIONS_BACKLOG_JOB_KEY = "corrections_backlog"
_ATTENTION_STATUSES = ("needs_review", "failed")


def _corrections_cooldown_delta(config: PulseConfig):
    raw = (config.corrections_backlog_alert_cooldown or "12h").strip()
    try:
        return parse_interval(raw)
    except ValueError:
        logger.warning(
            "Invalid corrections_backlog_alert_cooldown %r; using 12h",
            raw,
        )
        return parse_interval("12h")


async def notify_corrections_backlog_if_needed(config: PulseConfig) -> None:
    """After a healthy aggregation run, optionally alert on needs_review / failed backlog."""
    if not config.notify_on_corrections_backlog:
        return

    channel = build_notification_channel(config)
    if channel is None:
        logger.debug(
            "notify_on_corrections_backlog is true but no notification channels configured"
        )
        return

    cooldown = _corrections_cooldown_delta(config)
    now = datetime.now(timezone.utc)

    async with connect_db(config.database_path) as db:
        await bootstrap_schema(db)
        repo = CorrectionApplicationRepository(db)
        count = await repo.count_with_status_in(_ATTENTION_STATUSES)
        if count == 0:
            return

        if not await is_past_cooldown(db, _CORRECTIONS_BACKLOG_JOB_KEY, cooldown, now):
            return

        title = f"Pulse: {count} correction backlog item(s)"
        body = (
            f"{count} row(s) in correction_applications with status "
            f"{', '.join(_ATTENTION_STATUSES)}. Review in the Pulse UI, MCP "
            f"(`pulse_correct`), or the database."
        )
        notification = Notification(
            title=title,
            body=body,
            category="operations",
            priority="normal",
        )
        try:
            channel.send(notification)
        except Exception:
            logger.exception("Failed to send corrections backlog notification")
            return

        await record_cooldown_fire(db, _CORRECTIONS_BACKLOG_JOB_KEY, now)

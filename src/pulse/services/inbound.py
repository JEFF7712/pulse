"""One place where an inbound chat message becomes an action.

Both the webhook and the long-poller land here, so a reply behaves identically
whichever way it reached Pulse.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pulse.app.config import PulseConfig

logger = logging.getLogger(__name__)


def _today(config: PulseConfig) -> str:
    try:
        return datetime.now(ZoneInfo(config.timezone)).date().isoformat()
    except Exception:  # pragma: no cover - bad tz in config
        return datetime.now().date().isoformat()


async def handle_inbound_text(config: PulseConfig, text: str) -> str | None:
    """Resolve an inbound message against pending fact proposals.

    Returns None when the message was not a decision. That is the ordinary case on a
    chat channel — most messages are just messages — and it must not read as an error.
    """
    from pulse.services.fact_confirmation import apply_reply
    from pulse.store.db import connect_db
    from pulse.store.schema import bootstrap_schema

    try:
        async with connect_db(config.database_path) as db:
            await bootstrap_schema(db)
            return await apply_reply(
                db,
                vault_path=config.vault_path,
                text=text,
                today=_today(config),
            )
    except Exception:
        logger.exception("failed to handle inbound message")
        return None

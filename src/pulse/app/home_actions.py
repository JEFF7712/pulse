import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pulse.app.config import PulseConfig
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.notifications import Notification
from pulse.jobs.runners import run_aggregation_job, run_discovery_job
from pulse.llm.factory import (
    create_providers_from_config,
    discovery_model_for_discovery,
    summarization_model_for_source_summaries,
)
from pulse.llm.anthropic_errors import user_message_for_anthropic_exception
from pulse.notifications.factory import build_notification_channel
from pulse.notifications.telegram import TelegramChannel
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema
from pulse.store.sync_state import SyncStateRepository

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionResult:
    """Redirect target for home actions; `hint` adds an extra line on the homepage for errors."""

    query_key: str
    token: str
    hint: str | None = None


async def run_pull_action(
    settings: PulseConfig,
    registry: ConnectorRegistry | None,
) -> ActionResult:
    if registry is None:
        return ActionResult(query_key="notice", token="pull-skipped")

    active_connectors = registry.get_pull_connectors()
    if not active_connectors:
        return ActionResult(query_key="notice", token="pull-skipped")

    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            sync_state = SyncStateRepository(db)

            for connector, _connector_config in active_connectors:
                source = connector.get_source_name()
                cursor = await sync_state.load(source)
                since = datetime.fromisoformat(cursor) if cursor else None
                events = await connector.pull(since=since)
                if not events:
                    continue

                await event_repo.upsert_events(events)
                if hasattr(connector, "get_sync_timestamp"):
                    sync_timestamp = connector.get_sync_timestamp()
                else:
                    sync_timestamp = max(event.timestamp for event in events)
                await sync_state.save(source, sync_timestamp.isoformat())
    except Exception:
        logger.exception("Pull action failed")
        return ActionResult(query_key="error", token="pull-failed")

    return ActionResult(query_key="notice", token="pull-complete")


async def run_discovery_action(settings: PulseConfig) -> ActionResult:
    _, disc_llm = create_providers_from_config(settings)
    if disc_llm is None:
        return ActionResult(query_key="error", token="discovery-not-configured")

    target_day = _resolve_current_day(settings)
    notification_channel = build_notification_channel(settings)
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        await run_aggregation_job(
            day=target_day,
            database_path=settings.database_path,
            timezone=settings.timezone,
        )
        await run_discovery_job(
            cadence="daily",
            target_date=target_day,
            database_path=settings.database_path,
            vault_path=settings.vault_path,
            llm=disc_llm,
            timezone=settings.timezone,
            notification_channel=notification_channel,
            summarization_model=summarization_model_for_source_summaries(settings)
            or "",
            discovery_model=discovery_model_for_discovery(settings) or "",
        )
    except Exception as e:
        logger.exception("Discovery action failed")
        return ActionResult(
            query_key="error",
            token="discovery-failed",
            hint=user_message_for_anthropic_exception(e),
        )

    return ActionResult(query_key="notice", token="discovery-complete")


def run_test_telegram_action(settings: PulseConfig) -> ActionResult:
    channel = _build_telegram_channel(settings)
    if channel is None:
        return ActionResult(query_key="error", token="telegram-not-configured")

    try:
        channel.send(
            Notification(
                title="Pulse Test",
                body="If you're reading this, Telegram notifications are working!",
                category="test",
                priority="low",
            )
        )
    except Exception:
        logger.exception("Telegram test action failed")
        return ActionResult(query_key="error", token="telegram-test-failed")

    return ActionResult(query_key="notice", token="telegram-test-sent")


def _resolve_current_day(settings: PulseConfig) -> date:
    if ZoneInfo is None:
        return date.today()
    return datetime.now(ZoneInfo(settings.timezone)).date()


def _build_telegram_channel(settings: PulseConfig) -> TelegramChannel | None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return None

    return TelegramChannel(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

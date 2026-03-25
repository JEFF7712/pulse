from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status

from pulse.app.config import PulseConfig
from pulse.app.config_loader import load_config
from pulse.app.dependencies import get_settings
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.notifications import extract_reply_context
from pulse.services.corrections import CorrectionService
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema

# Backward compat alias
Settings = PulseConfig


def _extract_context_id(reply_to_message: dict[str, Any]) -> str | None:
    reply_text = reply_to_message.get("text")
    if not isinstance(reply_text, str):
        return None

    return extract_reply_context(reply_text)


def create_app(
    settings: PulseConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> FastAPI:
    app = FastAPI()

    settings_dependency = get_settings

    if settings is not None:

        def get_static_settings() -> PulseConfig:
            return settings

        settings_dependency = get_static_settings

    @app.get("/health")
    def health(
        _settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/telegram", status_code=status.HTTP_202_ACCEPTED)
    async def telegram_webhook(
        payload: dict[str, Any],
        s: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> dict[str, str]:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise HTTPException(status_code=400, detail="Missing message payload.")

        reply_text = message.get("text")
        if not isinstance(reply_text, str) or not reply_text.strip():
            raise HTTPException(status_code=400, detail="Missing reply text.")

        reply_to_message = message.get("reply_to_message")
        if not isinstance(reply_to_message, dict):
            raise HTTPException(status_code=400, detail="Missing reply target.")

        context_id = _extract_context_id(reply_to_message)
        if context_id is None:
            raise HTTPException(status_code=400, detail="Missing reply context.")

        async with connect_db(s.database_path) as db:
            await bootstrap_schema(db)
            repository = CorrectionRepository(db)
            service = CorrectionService(repository)
            await service.record_reply(
                context_id=context_id, message_text=reply_text.strip()
            )

        return {"status": "accepted"}

    # Wire push connector webhook routes
    if registry is not None:
        for push_conn, cc in registry.get_push_connectors():
            _register_push_route(app, push_conn, settings_dependency)

    return app


def _register_push_route(
    app: FastAPI, push_conn, settings_dependency
) -> None:
    path = push_conn.get_webhook_path()

    async def handler(
        request: Request,
        s: Annotated[PulseConfig, Depends(settings_dependency)],
        _conn=push_conn,
    ):
        payload = await request.json()
        events = await _conn.handle_webhook(payload)
        if events:
            async with connect_db(s.database_path) as db:
                await bootstrap_schema(db)
                event_repo = EventRepository(db)
                await event_repo.upsert_events(events)
        return {"status": "ok", "events_received": len(events)}

    app.add_api_route(path, handler, methods=["POST"])

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.domain.notifications import extract_reply_context
from pulse.services.corrections import CorrectionService
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.schema import bootstrap_schema


def _extract_context_id(reply_to_message: dict[str, Any]) -> str | None:
    reply_text = reply_to_message.get("text")
    if not isinstance(reply_text, str):
        return None

    return extract_reply_context(reply_text)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    settings_dependency = get_settings

    if settings is not None:

        def get_static_settings() -> Settings:
            return settings

        settings_dependency = get_static_settings

    @app.get("/health")
    def health(
        _settings: Annotated[Settings, Depends(settings_dependency)],
    ) -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/telegram", status_code=status.HTTP_202_ACCEPTED)
    async def telegram_webhook(
        payload: dict[str, Any],
        settings: Annotated[Settings, Depends(settings_dependency)],
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

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            repository = CorrectionRepository(db)
            service = CorrectionService(repository)
            await service.record_reply(
                context_id=context_id, message_text=reply_text.strip()
            )

        return {"status": "accepted"}

    return app

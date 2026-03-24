from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings
from pulse.connectors.google_auth import GoogleOAuth, build_authorization_url
from pulse.domain.notifications import extract_reply_context
from pulse.jobs.scheduler import build_scheduler
from pulse.services.corrections import CorrectionService
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.oauth import OAuthTokenRepository
from pulse.store.schema import bootstrap_schema


def _extract_context_id(reply_to_message: dict[str, Any]) -> str | None:
    reply_text = reply_to_message.get("text")
    if not isinstance(reply_text, str):
        return None

    return extract_reply_context(reply_text)


def create_app(
    settings: Settings | None = None,
    scheduler_factory: Callable[[], Any] = build_scheduler,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scheduler = scheduler_factory()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()

    app = FastAPI(lifespan=lifespan)
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

    # In-memory state store for CSRF protection
    _pending_oauth_states: set[str] = set()

    @app.get("/auth/google")
    async def auth_google(
        settings: Annotated[Settings, Depends(settings_dependency)],
    ):
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=503, detail="Google OAuth not configured.")

        url, state = build_authorization_url(
            client_id=settings.google_client_id,
            redirect_uri=settings.google_redirect_uri,
        )
        _pending_oauth_states.add(state)
        return RedirectResponse(url=url, status_code=307)

    @app.get("/auth/google/callback")
    async def auth_google_callback(
        code: str,
        state: str,
        settings: Annotated[Settings, Depends(settings_dependency)],
    ):
        if state not in _pending_oauth_states:
            raise HTTPException(status_code=400, detail="Invalid OAuth state.")
        _pending_oauth_states.discard(state)

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            token_repo = OAuthTokenRepository(db)
            async with httpx.AsyncClient() as http_client:
                oauth = GoogleOAuth(
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    redirect_uri=settings.google_redirect_uri,
                    token_repo=token_repo,
                    http_client=http_client,
                )
                await oauth.exchange_code(code)

        return {"status": "authorized"}

    return app

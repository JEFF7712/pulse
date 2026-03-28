from typing import Annotated, Any
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from pulse.app.api import build_api_router
from pulse.app.auth import build_require_companion_token
from pulse.app.config import PulseConfig
from pulse.app.dependencies import get_settings
from pulse.app.home_actions import (
    ActionResult,
    run_digest_action,
    run_discovery_action,
    run_pull_action,
    run_test_telegram_action,
)
from pulse.app.homepage import HomepageNotice, HomepageStatus, render_homepage
from pulse.connectors.registry import ConnectorRegistry
from pulse.domain.notifications import extract_reply_context
from pulse.jobs.scheduler import build_scheduler
from pulse.services.corrections import build_correction_service
from pulse.store.correction_applications import CorrectionApplicationRepository
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema

# Backward compat alias
Settings = PulseConfig

_NOTICE_MESSAGES = {
    "pull-skipped": "pull skipped",
    "pull-complete": "pull complete",
    "digest-complete": "digest complete",
    "discovery-complete": "discovery complete",
    "telegram-test-sent": "telegram test sent",
}

_ERROR_MESSAGES = {
    "pull-failed": "pull failed",
    "digest-failed": "digest failed",
    "discovery-not-configured": "discovery not configured",
    "discovery-failed": "discovery failed",
    "telegram-not-configured": "telegram not configured",
    "telegram-test-failed": "telegram test failed",
}


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

    @app.get("/", response_class=HTMLResponse)
    def home(
        current_settings: Annotated[PulseConfig, Depends(settings_dependency)],
        notice: str | None = None,
        error: str | None = None,
        hint: str | None = None,
    ) -> str:
        homepage_status = _build_homepage_status(current_settings, registry)
        hint_clean = hint[:700] if hint else None
        homepage_notice = _build_homepage_notice(
            notice=notice, error=error, hint=hint_clean
        )
        return render_homepage(homepage_status, notice=homepage_notice)

    @app.post("/actions/pull")
    async def run_pull(
        current_settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> RedirectResponse:
        result = await run_pull_action(current_settings, registry)
        return _redirect_home(result)

    @app.post("/actions/digest")
    async def run_digest(
        current_settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> RedirectResponse:
        result = await run_digest_action(current_settings)
        return _redirect_home(result)

    @app.post("/actions/discover")
    async def run_discover(
        current_settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> RedirectResponse:
        result = await run_discovery_action(current_settings)
        return _redirect_home(result)

    @app.post("/actions/test-telegram")
    def test_telegram(
        current_settings: Annotated[PulseConfig, Depends(settings_dependency)],
    ) -> RedirectResponse:
        result = run_test_telegram_action(current_settings)
        return _redirect_home(result)

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
            correction_applications = CorrectionApplicationRepository(db)
            service = build_correction_service(
                repository,
                config=s,
                correction_applications=correction_applications,
                vault_path=s.vault_path,
            )
            await service.record_reply(
                context_id=context_id, message_text=reply_text.strip()
            )

        return {"status": "accepted"}

    # Wire push connector webhook routes
    if registry is not None:
        for push_conn in registry.get_all_push_connector_instances():
            _register_push_route(app, push_conn, settings_dependency)

    # Wire companion app API
    auth_dep = build_require_companion_token(settings_dependency)
    api_router = build_api_router(settings_dependency, auth_dep)
    app.include_router(api_router)

    return app


def _register_push_route(app: FastAPI, push_conn, settings_dependency) -> None:
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


def _build_homepage_status(
    settings: PulseConfig,
    registry: ConnectorRegistry | None,
) -> HomepageStatus:
    scheduler = build_scheduler(registry=registry, config=settings)

    return HomepageStatus(
        database_path=settings.database_path,
        vault_path=settings.vault_path,
        timezone=settings.timezone,
        scheduler_job_count=len(scheduler.get_jobs()),
        pull_connectors=len(registry.get_pull_connectors()) if registry else 0,
        push_connectors=len(registry.get_push_connectors()) if registry else 0,
    )


def _redirect_home(result: ActionResult) -> RedirectResponse:
    url = f"/?{result.query_key}={result.token}"
    if result.hint:
        url += "&hint=" + quote_plus(result.hint[:500])
    return RedirectResponse(url=url, status_code=303)


def _build_homepage_notice(
    *, notice: str | None, error: str | None, hint: str | None = None
):
    if error is not None and error in _ERROR_MESSAGES:
        message = _ERROR_MESSAGES[error]
        if hint:
            message = f"{message}\n\n{hint}"
        return HomepageNotice(tone="error", message=message)

    if notice is not None and notice in _NOTICE_MESSAGES:
        return HomepageNotice(tone="success", message=_NOTICE_MESSAGES[notice])

    return None

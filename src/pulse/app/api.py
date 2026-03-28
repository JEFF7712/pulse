# src/pulse/app/api.py
"""REST API router for the companion app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status

from pulse.app.config import PulseConfig
from pulse.services.corrections import build_correction_service
from pulse.store.correction_applications import CorrectionApplicationRepository
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.device_tokens import DeviceTokenRepository
from pulse.store.schema import bootstrap_schema


def build_api_router(
    get_settings: Callable[[], PulseConfig],
    auth_dependency: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api", dependencies=[auth_dependency])

    @router.get("/digests/latest")
    async def get_latest_digest() -> dict[str, str]:
        settings = get_settings()
        daily_dir = Path(settings.vault_path) / "01-Daily"
        if not daily_dir.exists():
            raise HTTPException(status_code=404, detail="No digests found.")
        files = sorted(daily_dir.glob("*.md"), reverse=True)
        if not files:
            raise HTTPException(status_code=404, detail="No digests found.")
        date_slug = files[0].stem
        return {
            "date": date_slug,
            "markdown": files[0].read_text(encoding="utf-8"),
        }

    @router.get("/digests/{date_slug}")
    async def get_digest(date_slug: str) -> dict[str, str]:
        settings = get_settings()
        path = Path(settings.vault_path) / "01-Daily" / f"{date_slug}.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Digest not found.")
        return {"date": date_slug, "markdown": path.read_text(encoding="utf-8")}

    @router.post("/corrections", status_code=status.HTTP_202_ACCEPTED)
    async def post_correction(body: dict[str, str]) -> dict[str, str]:
        settings = get_settings()
        context_id = body.get("context_id", "")
        message_text = body.get("message_text", "")
        if not context_id or not message_text:
            raise HTTPException(
                status_code=400, detail="context_id and message_text required."
            )

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            service = build_correction_service(
                CorrectionRepository(db),
                config=settings,
                correction_applications=CorrectionApplicationRepository(db),
                vault_path=settings.vault_path,
            )
            correction = await service.record_correction(context_id, message_text)

        return {"status": "accepted", "correction_id": correction.id}

    @router.post("/device-token")
    async def post_device_token(body: dict[str, str]) -> dict[str, str]:
        settings = get_settings()
        token = body.get("token", "")
        platform = body.get("platform", "")
        if not token or not platform:
            raise HTTPException(
                status_code=400, detail="token and platform required."
            )

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)
            await repo.upsert(token, platform)

        return {"status": "registered"}

    return router

# src/pulse/app/api.py
"""REST API router for the companion app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from pulse.app.config import PulseConfig
from pulse.app.corrections_webhook import normalize_correction_payload
from pulse.services.corrections import build_correction_service
from pulse.store.analytics import AnalyticsRepository
from pulse.store.correction_applications import CorrectionApplicationRepository
from pulse.store.corrections import CorrectionRepository
from pulse.store.db import connect_db
from pulse.store.device_tokens import DeviceTokenRepository
from pulse.store.schema import bootstrap_schema


def _safe_vault_file(vault_root: Path, vault_rel: str) -> Path:
    """Resolve a vault-relative path under vault_root (no traversal)."""
    rel = Path(vault_rel)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid vault path.",
        )
    root = vault_root.resolve()
    full = (root / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid vault path.",
        ) from exc
    return full


def _safe_insight_id(insight_id: str) -> str:
    cleaned = insight_id.strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid insight id.",
        )
    return cleaned


def build_api_router(
    get_settings: Callable[[], PulseConfig],
    auth_dependency: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api", dependencies=[auth_dependency])

    @router.get("/insights")
    async def get_insights_list(
        status: str | None = Query(
            default=None, description="Filter by insight status"
        ),
    ) -> list[dict[str, Any]]:
        settings = get_settings()
        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            return await analytics.list_insights(status=status)

    @router.get("/insights/{insight_id}")
    async def get_insight_with_body(insight_id: str) -> dict[str, Any]:
        settings = get_settings()
        iid = _safe_insight_id(insight_id)
        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            row = await analytics.get_insight(iid)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight not found.",
            )
        path = _safe_vault_file(Path(settings.vault_path), row["vault_path"])
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pattern file missing on disk.",
            )
        markdown = path.read_text(encoding="utf-8")
        return {**row, "markdown": markdown}

    @router.post("/corrections", status_code=status.HTTP_202_ACCEPTED)
    async def post_correction(body: dict[str, str]) -> dict[str, str]:
        settings = get_settings()
        context_id, message_text = normalize_correction_payload(body)

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
            raise HTTPException(status_code=400, detail="token and platform required.")

        async with connect_db(settings.database_path) as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)
            await repo.upsert(token, platform)

        return {"status": "registered"}

    return router

# src/pulse/app/auth.py
"""Token-based auth for the companion app and webhook."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from pulse.app.config import PulseConfig


def verify_companion_token(
    settings: PulseConfig,
    x_pulse_token: str | None,
    authorization: str | None,
) -> None:
    expected = settings.companion_token

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Companion API is not configured.",
        )

    token = x_pulse_token
    if token is None and authorization is not None:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            token = credentials

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing companion token.",
        )

    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )


def build_require_companion_token(
    get_settings: Callable[[], PulseConfig],
) -> Any:
    """Build a FastAPI dependency for companion token auth."""

    async def _verify(
        settings: PulseConfig = Depends(get_settings),
        x_pulse_token: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        verify_companion_token(settings, x_pulse_token, authorization)

    return Depends(_verify)

# src/pulse/app/auth.py
"""Token-based auth for the companion app API."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from pulse.app.config import PulseConfig


def build_require_companion_token(
    get_settings: Callable[[], PulseConfig],
) -> Any:
    """Build a FastAPI dependency that verifies the X-Pulse-Token header."""

    async def _verify(
        x_pulse_token: Annotated[str | None, Header()] = None,
    ) -> None:
        settings = get_settings()
        expected = settings.companion_token

        if not expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Companion API is not configured.",
            )

        if x_pulse_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Pulse-Token header.",
            )

        if not hmac.compare_digest(x_pulse_token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token.",
            )

    return Depends(_verify)

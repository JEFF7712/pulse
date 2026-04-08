"""Authentication for POST /webhooks/corrections (Bearer or HMAC-SHA256 body)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException, Request, status


def verify_corrections_webhook(request: Request, body: bytes, secret: str) -> None:
    """Raise HTTPException(401) if the request is not authorized."""
    if not _authorized(request, body, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


def parse_corrections_webhook_payload(body: bytes) -> tuple[str, str]:
    """Parse JSON body; raise HTTPException(400) on error."""
    try:
        payload: Any = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON.",
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be a JSON object.",
        )
    return normalize_correction_payload(payload)


def normalize_correction_payload(payload: Any) -> tuple[str, str]:
    """Return normalized (context_id, message_text) for correction payloads."""
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be a JSON object.",
        )
    context_id = payload.get("context_id")
    message_text = payload.get("message_text")
    if message_text is None:
        message_text = payload.get("message")
    if not isinstance(context_id, str) or not context_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing context_id.",
        )
    if not isinstance(message_text, str) or not message_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing message_text (or legacy message).",
        )
    return context_id.strip(), message_text.strip()


def _authorized(request: Request, body: bytes, secret: str) -> bool:
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        return _constant_time_str_eq(token, secret)

    sig = request.headers.get("x-pulse-signature") or ""
    if sig.startswith("sha256="):
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig[7:], expected)
    return False


def _constant_time_str_eq(a: str, b: str) -> bool:
    """Timing-safe string compare (avoids ValueError on length mismatch)."""
    a_b = a.encode("utf-8")
    b_b = b.encode("utf-8")
    if len(a_b) != len(b_b):
        hmac.compare_digest(b"constanttime", b"constanttime")
        return False
    return hmac.compare_digest(a_b, b_b)

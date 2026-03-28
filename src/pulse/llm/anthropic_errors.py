"""Map Anthropic SDK exceptions to short operator-facing hints."""

from __future__ import annotations

import anthropic


def _api_error_text(exc: anthropic.APIError) -> str:
    parts = [exc.message.strip()] if getattr(exc, "message", None) else []
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            m = err.get("message")
            if isinstance(m, str) and m.strip() and m.strip() not in parts:
                parts.append(m.strip())
    return " ".join(parts) if parts else ""


def _looks_like_billing_or_credits(text: str) -> bool:
    t = text.lower()
    return any(
        w in t
        for w in (
            "credit",
            "billing",
            "balance",
            "payment",
            "purchase",
            "quota",
            "exceeded your",
            "spend limit",
        )
    )


def _for_one(exc: BaseException) -> str | None:
    if isinstance(exc, anthropic.AuthenticationError):
        return (
            "Anthropic rejected your API key (401). Check PULSE_ANTHROPIC_API_KEY "
            "and that the key is active at console.anthropic.com."
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return (
            "Anthropic denied access (403). Your key may lack permission for this model "
            "or the account may be restricted."
        )
    if isinstance(exc, anthropic.NotFoundError):
        detail = _api_error_text(exc)
        base = (
            "Anthropic returned 404 — often an invalid model id. "
            "Check `[llm.*]` model values in pulse.toml (legacy PULSE_ANTHROPIC_API_KEY uses fixed defaults)."
        )
        return f"{base} API said: {detail}" if detail else base
    if isinstance(exc, anthropic.RateLimitError):
        return (
            "Anthropic rate limit (429). Wait a few minutes or reduce how often discovery/digest runs; "
            "see usage limits on your Anthropic plan."
        )
    if isinstance(exc, anthropic.APITimeoutError):
        return "Anthropic request timed out. Check your network and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach Anthropic’s API (connection error). Check network and DNS."

    if isinstance(exc, anthropic.APIStatusError):
        text = _api_error_text(exc)
        code = getattr(exc, "status_code", None)
        if isinstance(exc, anthropic.BadRequestError):
            if _looks_like_billing_or_credits(text) or _looks_like_billing_or_credits(
                getattr(exc, "message", "") or ""
            ):
                return (
                    "Anthropic billing or usage limit issue. Add credits, raise spend limits, "
                    "or check plan eligibility at console.anthropic.com."
                )
            return f"Anthropic rejected the request (400): {text or exc.message}"
        if code == 402 or _looks_like_billing_or_credits(text) or _looks_like_billing_or_credits(
            getattr(exc, "message", "") or ""
        ):
            return (
                "Anthropic billing or usage limit issue. Add credits, raise spend limits, "
                "or check plan eligibility at console.anthropic.com."
            )
        if code == 529:
            return "Anthropic is overloaded (529). Retry in a few minutes."
        if code in (500, 503, 504):
            return "Anthropic had a server-side error. Try again later."
        return f"Anthropic API error ({code}): {text or exc.message}"

    if isinstance(exc, anthropic.AnthropicError):
        return f"Anthropic API error: {exc.message}"

    return None


def user_message_for_anthropic_exception(exc: BaseException) -> str | None:
    """Return a short user-facing hint, or None if this is not a known Anthropic error."""
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = _for_one(cur)
        if msg is not None:
            return msg
        cur = cur.__cause__
    return None

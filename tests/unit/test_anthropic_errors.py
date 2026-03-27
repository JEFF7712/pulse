import httpx

import anthropic
from pulse.llm.anthropic_errors import user_message_for_anthropic_exception


def _status_exc(
    cls: type[anthropic.APIStatusError],
    *,
    status: int,
    message: str = "x",
    body: dict | None = None,
) -> anthropic.APIStatusError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status, request=req)
    return cls(message, response=resp, body=body)


def test_user_message_rate_limit() -> None:
    exc = _status_exc(anthropic.RateLimitError, status=429)
    msg = user_message_for_anthropic_exception(exc)
    assert msg is not None
    assert "429" in msg or "rate limit" in msg.lower()


def test_user_message_auth() -> None:
    exc = _status_exc(anthropic.AuthenticationError, status=401)
    msg = user_message_for_anthropic_exception(exc)
    assert msg is not None
    assert "API key" in msg


def test_user_message_not_found_model() -> None:
    exc = _status_exc(
        anthropic.NotFoundError,
        status=404,
        body={"error": {"message": "model: foo"}},
    )
    msg = user_message_for_anthropic_exception(exc)
    assert msg is not None
    assert "404" in msg or "model" in msg.lower()


def test_user_message_billing_keywords_in_body() -> None:
    exc = _status_exc(
        anthropic.BadRequestError,
        status=400,
        body={"error": {"message": "You have exceeded your credit balance"}},
    )
    msg = user_message_for_anthropic_exception(exc)
    assert msg is not None
    assert "billing" in msg.lower() or "credit" in msg.lower()


def test_user_message_unknown_exception_returns_none() -> None:
    assert user_message_for_anthropic_exception(RuntimeError("nope")) is None


def test_user_message_follows_exception_cause() -> None:
    inner = _status_exc(anthropic.RateLimitError, status=429)
    outer = RuntimeError("wrapper")
    outer.__cause__ = inner
    msg = user_message_for_anthropic_exception(outer)
    assert msg is not None
    assert "rate limit" in msg.lower()

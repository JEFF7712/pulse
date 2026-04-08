import pytest
from fastapi import HTTPException

from pulse.app.corrections_webhook import parse_corrections_webhook_payload


def test_parse_corrections_webhook_payload_valid() -> None:
    body = b'{"context_id": "2026-03-27", "message": "Fix the summary."}'
    cid, msg = parse_corrections_webhook_payload(body)
    assert cid == "2026-03-27"
    assert msg == "Fix the summary."


def test_parse_corrections_webhook_payload_strips_whitespace() -> None:
    body = b'{"context_id": "  pat:x  ", "message": "  hi  "}'
    cid, msg = parse_corrections_webhook_payload(body)
    assert cid == "pat:x"
    assert msg == "hi"


def test_parse_corrections_webhook_payload_prefers_message_text_when_both_present() -> (
    None
):
    body = (
        b'{"context_id": "2026-03-27", '
        b'"message_text": "Use this value.", '
        b'"message": "Do not use this value."}'
    )
    cid, msg = parse_corrections_webhook_payload(body)
    assert cid == "2026-03-27"
    assert msg == "Use this value."


def test_parse_corrections_webhook_payload_invalid_json() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_corrections_webhook_payload(b"not json")
    assert exc.value.status_code == 400


def test_parse_corrections_webhook_payload_not_object() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_corrections_webhook_payload(b'"string"')
    assert exc.value.status_code == 400


def test_parse_corrections_webhook_payload_missing_fields() -> None:
    with pytest.raises(HTTPException):
        parse_corrections_webhook_payload(b'{"context_id": ""}')
    with pytest.raises(HTTPException) as exc:
        parse_corrections_webhook_payload(b'{"context_id": "x", "message": ""}')
    assert exc.value.detail == "Missing message_text (or legacy message)."
    with pytest.raises(HTTPException):
        parse_corrections_webhook_payload(b'{"context_id": "x"}')

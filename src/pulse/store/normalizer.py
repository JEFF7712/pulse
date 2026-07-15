"""EventNormalizer — deterministic, lossless noise-stripping applied at ingest.

Tier-1 of the read pipeline: remove content that is pure noise (URL tracking
parameters, zero-width characters) so every downstream query and digest works on
clean data without re-doing the work. Signal is never removed; this is not
summarization.
"""

from __future__ import annotations

from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pulse.domain.events import Event

# Query params that identify marketing/analytics campaigns, never page content.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_reader",
        "utm_name",
        "gclid",
        "fbclid",
        "msclkid",
        "dclid",
        "gbraid",
        "wbraid",
        "yclid",
        "mc_eid",
        "mc_cid",
        "_hsenc",
        "_hsmi",
        "igshid",
        "mkt_tok",
        "vero_id",
        "oly_enc_id",
        "oly_anon_id",
        "ref_src",
        "spm",
    }
)

_ZERO_WIDTH = str.maketrans({"​": None, "‌": None, "‍": None, "﻿": None})


def clean_url(value: str) -> str:
    """Strip tracking query params from a URL. Non-URLs are returned unchanged."""
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


def _clean_str(value: str) -> str:
    cleaned = value.translate(_ZERO_WIDTH)
    if cleaned.startswith(("http://", "https://")):
        cleaned = clean_url(cleaned)
    return cleaned


def _clean(value: object) -> object:
    if isinstance(value, str):
        return _clean_str(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


class EventNormalizer:
    """Lossless deterministic cleaner run over an event's data/metadata at ingest."""

    def normalize(self, event: Event) -> Event:
        return replace(
            event,
            data=_clean(event.data),
            metadata=_clean(event.metadata),
        )

from __future__ import annotations

PATTERN_STATUS_CHOICES = (
    "emerging",
    "active",
    "strengthening",
    "confirmed",
    "weakening",
    "inactive",
    "invalidated",
)
ALLOWED_PATTERN_STATUSES = frozenset(PATTERN_STATUS_CHOICES)


def normalize_pattern_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in ALLOWED_PATTERN_STATUSES:
        raise ValueError("Pattern status is not in the allowed set")
    return normalized

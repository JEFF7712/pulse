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

# Statuses meaning "this is no longer happening". A closed pattern must not block a
# new finding as a duplicate: a behaviour that stopped and then came back is news,
# and a months-old closed pattern should never gag the agent about the present.
CLOSED_PATTERN_STATUSES = frozenset({"inactive", "invalidated"})


def is_closed_status(status: str) -> bool:
    return status.strip().lower() in CLOSED_PATTERN_STATUSES


def normalize_pattern_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in ALLOWED_PATTERN_STATUSES:
        raise ValueError("Pattern status is not in the allowed set")
    return normalized

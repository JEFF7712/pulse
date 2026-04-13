"""Parse human-readable intervals for poll intervals and alert cooldowns."""

from __future__ import annotations

import re
from datetime import timedelta


def parse_interval(interval_str: str) -> timedelta:
    match = re.fullmatch(r"(\d+)\s*(m|h|d|s)", interval_str.strip())
    if not match:
        raise ValueError(f"Invalid interval format: '{interval_str}'")
    value = int(match.group(1))
    unit = match.group(2)
    units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return timedelta(**{units[unit]: value})

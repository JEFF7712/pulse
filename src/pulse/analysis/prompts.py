"""Prompt templates and response parsing for the Pulse insight engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pulse.domain.pattern_statuses import PATTERN_STATUS_CHOICES

_PATTERN_STATUS_CHOICES = " | ".join(PATTERN_STATUS_CHOICES)

SYSTEM_PROMPT = """You are Pulse's insight engine, analyzing personal data for cross-source patterns.

## Role
Analyze the user's personal data streams (calendar, email, browsing, music, etc.) to surface meaningful cross-source insights about behavior, habits, and trends.

## Rules
- Only report interesting or actionable findings — skip noise
- Update existing patterns with new evidence rather than duplicating them
- Use only the bounded pattern statuses in the schema below
- Be specific: include concrete data points, counts, and time references
- Actively look for cross-source connections (e.g., browsing topics after meetings, music mood shifts after heavy email days)

## Rejection Criteria — Do NOT Report
- That the user uses email, calendar, or browsing regularly — that is baseline, not a pattern
- Simple activity counts without context ("user received 50 emails")
- Patterns that only involve a single source with no temporal trend or deviation
- Anything already captured in the active patterns below unless you have NEW evidence

## What Qualifies as a Pattern
A pattern MUST involve at least one of:
1. A cross-source connection (e.g., "browsing shifts to relaxation content after days with 4+ hours of meetings")
2. A temporal trend that is increasing, decreasing, or cyclical over time
3. A meaningful deviation from established baselines (e.g., "email volume 3x normal this week")

## Output JSON Schema

```json
{
  "new_patterns": [
    {
      "title": "Short descriptive name",
      "observation": "Detailed description of what was found",
      "confidence": 0.0,
      "evidence": ["specific data point 1", "specific data point 2"],
      "trend": "increasing | decreasing | stable | new"
    }
  ],
  "updated_patterns": [
    {
      "slug": "existing-pattern-slug",
      "status": "PLACEHOLDER_PATTERN_STATUSES",
      "confidence": 0.0,
      "update_note": "What changed or was reinforced",
      "new_evidence": ["new data point 1"],
      "trend": "increasing | decreasing | stable"
    }
  ],
  "notifications": [
    {
      "title": "Notification title",
      "body": "Notification body text",
      "priority": "high | medium | low",
      "pattern_slug": "pattern-slug-if-this-notification-is-about-a-pattern | null"
    }
  ],
  "baseline_updates": "Updated baseline description or null"
}
```

Output only the JSON object. Do not include any explanation or markdown formatting outside the JSON.""".replace(
    "PLACEHOLDER_PATTERN_STATUSES", _PATTERN_STATUS_CHOICES
)


def build_discovery_prompt(
    cadence: str,
    date_range: str,
    event_summary: str,
    active_patterns: str,
    baselines: str,
    user_profile: str,
) -> dict[str, str]:
    """Build a discovery prompt dict with system and user prompts.

    Args:
        cadence: Analysis cadence — "daily", "weekly", or "monthly"
        date_range: Human-readable date range string
        event_summary: Summary of events for the period
        active_patterns: Current active pattern descriptions (empty string if none)
        baselines: Known baseline descriptions (empty string if none)
        user_profile: User preference / profile notes (may be empty)

    Returns:
        Dict with "system_prompt" and "user_prompt" keys.
    """
    patterns_section = (
        active_patterns.strip() if active_patterns.strip() else "No active patterns yet"
    )
    baselines_section = (
        baselines.strip() if baselines.strip() else "No baselines established yet"
    )

    cadence_instruction = _cadence_instruction(cadence)

    user_prompt = f"""## Current Data ({date_range})

{event_summary}

## Your Active Patterns

{patterns_section}

## Known Baselines

{baselines_section}

## User Profile

{user_profile if user_profile.strip() else "No profile information provided."}

---

{cadence_instruction}"""

    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
    }


def _cadence_instruction(cadence: str) -> str:
    if cadence == "daily":
        return (
            "Focus on what is notable or unusual today compared to the user's normal patterns. "
            "Highlight anything that stands out from a typical day."
        )
    elif cadence == "weekly":
        return (
            "Look for cross-source patterns that emerged across the week. "
            "Connect dots between different data streams over the 7-day period."
        )
    elif cadence == "monthly":
        return (
            "Analyze long-term trends and pattern evolution over the month. "
            "Identify which patterns are strengthening, weakening, or newly emerging."
        )
    else:
        return f"Analyze the data for the {cadence} period and surface meaningful insights."


@dataclass(slots=True)
class NewPattern:
    title: str
    observation: str
    confidence: float | str
    evidence: list[str] = field(default_factory=list)
    trend: str = ""


@dataclass(slots=True)
class UpdatedPattern:
    slug: str
    status: str
    confidence: float | str
    update_note: str
    new_evidence: list[str] = field(default_factory=list)
    trend: str = ""


@dataclass(slots=True)
class NotificationItem:
    title: str
    body: str
    priority: str
    pattern_slug: str | None = None


@dataclass(slots=True)
class DiscoveryResponse:
    new_patterns: list[NewPattern] = field(default_factory=list)
    updated_patterns: list[UpdatedPattern] = field(default_factory=list)
    notifications: list[NotificationItem] = field(default_factory=list)
    baseline_updates: str | None = None


def _parse_confidence(value: object) -> float | str:
    """Return value as-is if it's already a string label, otherwise coerce to float."""
    if isinstance(value, str):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_dict_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str)]


def _as_str(value: object, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    return value.strip()


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = stripped.index("\n") if "\n" in stripped else len(stripped)
        stripped = stripped[first_newline + 1 :]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def parse_discovery_response(raw: str) -> DiscoveryResponse:
    """Parse a raw LLM JSON response string into a DiscoveryResponse.

    On malformed or missing JSON, returns an empty DiscoveryResponse rather
    than raising.
    """
    try:
        cleaned = _strip_code_fences(raw)
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return DiscoveryResponse()
    if not isinstance(data, dict):
        return DiscoveryResponse()

    new_patterns = [
        NewPattern(
            title=_as_str(p.get("title")),
            observation=_as_str(p.get("observation")),
            confidence=_parse_confidence(p.get("confidence", 0.0)),
            evidence=_as_str_list(p.get("evidence")),
            trend=_as_str(p.get("trend")),
        )
        for p in _as_dict_list(data.get("new_patterns"))
    ]

    updated_patterns = [
        UpdatedPattern(
            slug=_as_str(p.get("slug")),
            status=_as_str(p.get("status")),
            confidence=_parse_confidence(p.get("confidence", 0.0)),
            update_note=_as_str(p.get("update_note")),
            new_evidence=_as_str_list(p.get("new_evidence")),
            trend=_as_str(p.get("trend")),
        )
        for p in _as_dict_list(data.get("updated_patterns"))
    ]

    notifications = [
        NotificationItem(
            title=_as_str(n.get("title")),
            body=_as_str(n.get("body")),
            priority=_as_str(n.get("priority"), "low") or "low",
            pattern_slug=_as_str(n.get("pattern_slug")) or None,
        )
        for n in _as_dict_list(data.get("notifications"))
    ]

    baseline_updates = data.get("baseline_updates")
    if not isinstance(baseline_updates, str):
        baseline_updates = None
    else:
        baseline_updates = baseline_updates.strip() or None

    return DiscoveryResponse(
        new_patterns=new_patterns,
        updated_patterns=updated_patterns,
        notifications=notifications,
        baseline_updates=baseline_updates,
    )

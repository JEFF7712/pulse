"""Prompt templates and response parsing for the Pulse insight engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

SYSTEM_PROMPT = """You are Pulse's insight engine, analyzing personal data for cross-source patterns.

## Role
Analyze the user's personal data streams (calendar, email, browsing, music, health, etc.) to surface meaningful cross-source insights about behavior, habits, and trends.

## Rules
- Only report interesting or actionable findings — skip noise
- Update existing patterns with new evidence rather than duplicating them
- Mark patterns as invalidated if the data no longer supports them
- Be specific: include concrete data points, counts, and time references
- Actively look for cross-source connections (e.g., sleep affecting productivity, stress correlating with browsing habits)
- Output valid JSON matching the schema below — nothing else

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
      "status": "confirmed | weakening | invalidated",
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
      "priority": "high | medium | low"
    }
  ],
  "baseline_updates": "Updated baseline description or null"
}
```

Output only the JSON object. Do not include any explanation or markdown formatting outside the JSON."""


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
    patterns_section = active_patterns.strip() if active_patterns.strip() else "No active patterns yet"
    baselines_section = baselines.strip() if baselines.strip() else "No baselines established yet"

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
    confidence: float
    evidence: list[str] = field(default_factory=list)
    trend: str = ""


@dataclass(slots=True)
class UpdatedPattern:
    slug: str
    status: str
    confidence: float
    update_note: str
    new_evidence: list[str] = field(default_factory=list)
    trend: str = ""


@dataclass(slots=True)
class NotificationItem:
    title: str
    body: str
    priority: str


@dataclass(slots=True)
class DiscoveryResponse:
    new_patterns: list[NewPattern] = field(default_factory=list)
    updated_patterns: list[UpdatedPattern] = field(default_factory=list)
    notifications: list[NotificationItem] = field(default_factory=list)
    baseline_updates: str | None = None


def parse_discovery_response(raw: str) -> DiscoveryResponse:
    """Parse a raw LLM JSON response string into a DiscoveryResponse.

    On malformed or missing JSON, returns an empty DiscoveryResponse rather
    than raising.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return DiscoveryResponse()

    new_patterns = [
        NewPattern(
            title=p.get("title", ""),
            observation=p.get("observation", ""),
            confidence=float(p.get("confidence", 0.0)),
            evidence=list(p.get("evidence", [])),
            trend=p.get("trend", ""),
        )
        for p in data.get("new_patterns", [])
    ]

    updated_patterns = [
        UpdatedPattern(
            slug=p.get("slug", ""),
            status=p.get("status", ""),
            confidence=float(p.get("confidence", 0.0)),
            update_note=p.get("update_note", ""),
            new_evidence=list(p.get("new_evidence", [])),
            trend=p.get("trend", ""),
        )
        for p in data.get("updated_patterns", [])
    ]

    notifications = [
        NotificationItem(
            title=n.get("title", ""),
            body=n.get("body", ""),
            priority=n.get("priority", "low"),
        )
        for n in data.get("notifications", [])
    ]

    baseline_updates = data.get("baseline_updates", None)

    return DiscoveryResponse(
        new_patterns=new_patterns,
        updated_patterns=updated_patterns,
        notifications=notifications,
        baseline_updates=baseline_updates,
    )

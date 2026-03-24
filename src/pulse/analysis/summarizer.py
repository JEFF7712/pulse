from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = (
    "You are a personal assistant summarizing one day's activity for a single user. "
    "Return markdown with these exact section headers: "
    "## Timeline, ## Email Highlights, ## Spending, ## Health, ## Media, ## Insights. "
    "Use bullet points, not paragraphs. Be concise. "
    "In the Insights section, identify patterns, anomalies, or notable observations "
    "(e.g., 'Unusually busy morning — 4 meetings before noon', 'No emails after 6pm')."
)


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def __init__(self, llm=None) -> None:
        self._llm = llm

    async def summarize(self, day: date, events: list[Event]) -> DailySummary:
        if self._llm is not None:
            return await self._summarize_with_llm(day, events)
        return self._summarize_raw(day, events)

    async def _summarize_with_llm(self, day: date, events: list[Event]) -> DailySummary:
        event_lines = "\n".join(
            f"- [{e.timestamp:%H:%M}] {e.source}/{e.event_type}: {_event_text(e)}"
            for e in sorted(events, key=lambda item: item.timestamp)
        )
        user_prompt = f"Date: {day.isoformat()}\n\nEvents:\n{event_lines}"

        try:
            llm_response = await self._llm.complete(
                system_prompt=SUMMARIZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return self._parse_llm_response(day, llm_response)
        except Exception:
            logger.warning("LLM call failed; falling back to raw summarization.", exc_info=True)
            return self._summarize_raw(day, events)

    def _parse_llm_response(self, day: date, response: str) -> DailySummary:
        sections: dict[str, list[str]] = {}
        current_section: str | None = None

        for line in response.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped.removeprefix("## ").strip()
                sections.setdefault(current_section, [])
            elif current_section and stripped.startswith("- "):
                sections[current_section].append(stripped.removeprefix("- ").strip())

        insights = sections.get("Insights")

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=sections.get("Timeline", []),
            email_highlights=sections.get("Email Highlights", []),
            spending_items=sections.get("Spending", []),
            health_items=sections.get("Health", []),
            media_items=sections.get("Media", []),
            tags=[],
            insights_items=insights,
        )
        return DailySummary(day=day, markdown=markdown)

    def _summarize_raw(self, day: date, events: list[Event]) -> DailySummary:
        timeline_items: list[str] = []
        email_highlights: list[str] = []

        for event in sorted(events, key=lambda item: item.timestamp):
            if event.event_type == "calendar.event":
                timeline_items.append(_event_text(event, "title"))
                continue
            if event.event_type == "email.received":
                email_highlights.append(_event_text(event, "subject"))
                continue
            timeline_items.append(_event_text(event))

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=timeline_items,
            email_highlights=email_highlights,
            spending_items=[],
            health_items=[],
            media_items=[],
            tags=[],
        )
        return DailySummary(day=day, markdown=markdown)


def _event_text(event: Event, preferred_key: str | None = None) -> str:
    if preferred_key is not None:
        value = event.data.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return event.event_type

from dataclasses import dataclass
from datetime import date

from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def summarize(self, day: date, events: list[Event]) -> DailySummary:
        timeline_items: list[str] = []
        email_highlights: list[str] = []
        media_items: list[str] = []
        browsing_items: list[str] = []

        for event in sorted(events, key=lambda item: item.timestamp):
            if event.event_type == "calendar.event":
                timeline_items.append(_event_text(event, "title"))
            elif event.event_type == "email.received":
                email_highlights.append(_event_text(event, "subject"))
            elif event.event_type == "media.spotify.play":
                track = event.data.get("track_name", "Unknown")
                artist = event.data.get("artist", "Unknown")
                media_items.append(f"Listened to {track} by {artist}")
            elif event.event_type in (
                "media.youtube.activity",
                "media.youtube.like",
            ):
                media_items.append(_event_text(event, "title"))
            elif event.event_type == "browsing.visit":
                title = event.data.get("title") or event.data.get("url", "")
                browsing_items.append(title)
            else:
                timeline_items.append(_event_text(event))

        markdown = render_daily_digest(
            date_label=day.isoformat(),
            timeline_items=timeline_items,
            email_highlights=email_highlights,
            spending_items=[],
            health_items=[],
            media_items=media_items,
            browsing_items=browsing_items,
            tags=[],
        )

        return DailySummary(day=day, markdown=markdown)


def _event_text(event: Event, preferred_key: str | None = None) -> str:
    if preferred_key is not None:
        value = event.data.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return event.event_type

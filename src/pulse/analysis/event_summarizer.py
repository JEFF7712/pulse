from collections import defaultdict

from pulse.domain.events import Event


class EventSummarizer:
    def summarize(
        self,
        date_range: str,
        stats: list[dict],
        events: list[Event],
        baselines: list[dict] | None = None,
    ) -> str:
        if not stats:
            return ""

        # Build baseline lookup: (source, event_type) -> baseline dict
        baseline_map: dict[tuple[str, str], dict] = {}
        if baselines:
            for b in baselines:
                baseline_map[(b["source"], b["event_type"])] = b

        # Group stats by source
        stats_by_source: dict[str, list[dict]] = defaultdict(list)
        for stat in stats:
            stats_by_source[stat["source"]].append(stat)

        # Group events by source
        events_by_source: dict[str, list[Event]] = defaultdict(list)
        for event in events:
            events_by_source[event.source].append(event)

        sections: list[str] = []

        for source in sorted(stats_by_source):
            lines: list[str] = [f"## {source} ({date_range})"]

            for stat in stats_by_source[source]:
                event_type = stat["event_type"]
                count = stat["count"]
                line = f"- {event_type}: {count} events"

                key = (source, event_type)
                if key in baseline_map:
                    b = baseline_map[key]
                    avg = b["avg_daily"]
                    if avg > 0:
                        pct = abs((count - avg) / avg) * 100
                        direction = "up" if count >= avg else "down"
                        line += f" (baseline avg {avg:.1f}/day, {direction} {pct:.0f}%)"

                lines.append(line)

            # Highlights from events for this source
            source_events = events_by_source.get(source, [])
            highlights = self._extract_highlights(source_events)
            if highlights:
                lines.append("Highlights:")
                for h in highlights:
                    lines.append(f"  - {h}")

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def _extract_highlights(self, events: list[Event], max_highlights: int = 5) -> list[str]:
        results: list[str] = []
        for event in events:
            if len(results) >= max_highlights:
                break
            highlight = self._highlight_for_event(event)
            if highlight:
                results.append(highlight)
        return results

    def _highlight_for_event(self, event: Event) -> str | None:
        data = event.data
        et = event.event_type

        if et == "email.received":
            subject = data.get("subject", "")
            sender = data.get("from", "")
            return f'"{subject}" from {sender}'

        if et == "media.spotify.play":
            track = data.get("track_name", "")
            artist = data.get("artist", "")
            return f"{track} by {artist}"

        if et == "calendar.event":
            return data.get("title") or None

        if et == "browsing.visit":
            return data.get("title") or data.get("url") or None

        if et in ("media.youtube.activity", "media.youtube.like"):
            return data.get("title") or None

        # Generic fallback
        return data.get("title") or data.get("subject") or data.get("name") or None

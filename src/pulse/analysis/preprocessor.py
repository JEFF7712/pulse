"""EventPreprocessor — clusters raw events into structured summaries."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from pulse.domain.events import Event


@dataclass(slots=True)
class TopicCluster:
    domain: str
    titles: list[str]
    visit_count: int
    estimated_minutes: float
    first_visit: datetime
    last_visit: datetime


@dataclass(slots=True)
class EmailThread:
    subject: str
    message_count: int
    senders: list[str]
    is_active: bool  # 3+ messages = active conversation


@dataclass(slots=True)
class CalendarBlock:
    title: str
    start: datetime
    duration_minutes: float
    back_to_back: bool


@dataclass(slots=True)
class MediaSession:
    source: str  # "spotify" or "youtube"
    items: list[str]  # track names or video titles
    duration_minutes: float
    first_item: datetime
    last_item: datetime


@dataclass(slots=True)
class TimeBlock:
    block: int  # 0-11 (2-hour blocks: 0=00:00-02:00, 6=12:00-14:00)
    sources: dict[str, int] = field(default_factory=dict)  # source -> count


@dataclass(slots=True)
class DevActivity:
    title: str
    provider: str
    action: str
    repo: str
    timestamp: datetime
    url: str


@dataclass(slots=True)
class FinanceDaySummary:
    transaction_count: int
    total_outflow: float
    merchant_counts: list[tuple[str, int]]
    merchant_spend: list[tuple[str, float]]
    omit_amounts: bool


_DEV_EVENT_TYPES = frozenset({
    "dev.push",
    "dev.issue",
    "dev.pull_request",
    "dev.comment",
    "dev.repo_activity",
})


@dataclass(slots=True)
class PreprocessedDay:
    browsing_clusters: list[TopicCluster] = field(default_factory=list)
    email_threads: list[EmailThread] = field(default_factory=list)
    calendar_blocks: list[CalendarBlock] = field(default_factory=list)
    media_sessions: list[MediaSession] = field(default_factory=list)
    dev_activities: list[DevActivity] = field(default_factory=list)
    finance_summary: FinanceDaySummary | None = None
    time_blocks: list[TimeBlock] = field(default_factory=list)
    raw_stats: dict[str, int] = field(default_factory=dict)


class EventPreprocessor:
    def preprocess(self, events: list[Event]) -> PreprocessedDay:
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        by_type: dict[str, list[Event]] = defaultdict(list)
        source_counts: dict[str, int] = defaultdict(int)

        for event in sorted_events:
            by_type[event.event_type].append(event)
            source_counts[event.source] += 1

        finance_events = by_type.get("finance.transaction", [])

        return PreprocessedDay(
            browsing_clusters=self._cluster_browsing(by_type.get("browsing.visit", [])),
            email_threads=self._group_email_threads(by_type.get("email.received", [])),
            calendar_blocks=self._build_calendar_blocks(by_type.get("calendar.event", [])),
            media_sessions=self._build_media_sessions(sorted_events),
            dev_activities=self._build_dev_activities(sorted_events),
            finance_summary=self._build_finance_summary(finance_events),
            time_blocks=self._build_time_blocks(sorted_events),
            raw_stats=dict(source_counts),
        )

    def _cluster_browsing(self, events: list[Event]) -> list[TopicCluster]:
        by_domain: dict[str, list[Event]] = defaultdict(list)

        for event in events:
            url = event.data.get("url", "")
            try:
                domain = urlparse(url).netloc
            except Exception:
                domain = "unknown"
            if domain:
                by_domain[domain].append(event)

        clusters = []
        for domain, domain_events in by_domain.items():
            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique_titles: list[str] = []
            for e in domain_events:
                url = e.data.get("url", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    title = e.data.get("title", "")
                    if title:
                        unique_titles.append(title)

            # Estimate time: sum gaps between consecutive visits (cap at 30 min each)
            timestamps = sorted(e.timestamp for e in domain_events)
            total_minutes = 0.0
            for i in range(1, len(timestamps)):
                gap = (timestamps[i] - timestamps[i - 1]).total_seconds() / 60
                total_minutes += min(gap, 30)
            # Add minimum 1 minute for single visits
            if total_minutes == 0:
                total_minutes = 1.0

            clusters.append(TopicCluster(
                domain=domain,
                titles=unique_titles,
                visit_count=len(seen_urls),
                estimated_minutes=round(total_minutes, 1),
                first_visit=timestamps[0],
                last_visit=timestamps[-1],
            ))

        # Sort by visit count descending
        clusters.sort(key=lambda c: c.visit_count, reverse=True)
        return clusters

    def _group_email_threads(self, events: list[Event]) -> list[EmailThread]:
        threads: dict[str, list[Event]] = defaultdict(list)

        for event in events:
            subject = event.data.get("subject", "")
            # Normalize: strip Re:/Fwd: prefixes
            normalized = subject
            for prefix in ("Re: ", "RE: ", "Fwd: ", "FWD: ", "Fw: "):
                while normalized.startswith(prefix):
                    normalized = normalized[len(prefix):]
            normalized = normalized.strip() or "(no subject)"
            threads[normalized].append(event)

        result = []
        for subject, thread_events in threads.items():
            senders = list(dict.fromkeys(
                (e.data.get("from") or e.data.get("sender") or "").strip()
                for e in thread_events
                if (e.data.get("from") or e.data.get("sender"))
            ))
            result.append(EmailThread(
                subject=subject,
                message_count=len(thread_events),
                senders=senders,
                is_active=len(thread_events) >= 3,
            ))

        # Active threads first, then by message count
        result.sort(key=lambda t: (not t.is_active, -t.message_count))
        return result

    def _build_calendar_blocks(self, events: list[Event]) -> list[CalendarBlock]:
        blocks = []
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        for i, event in enumerate(sorted_events):
            title = event.data.get("title", "Untitled")
            start = event.timestamp
            # Check if next event starts within 15 min of this one's start
            back_to_back = False
            if i + 1 < len(sorted_events):
                gap = (sorted_events[i + 1].timestamp - start).total_seconds() / 60
                back_to_back = gap <= 15

            blocks.append(CalendarBlock(
                title=title,
                start=start,
                duration_minutes=30.0,  # Default; calendar API doesn't give end time
                back_to_back=back_to_back,
            ))

        return blocks

    def _build_media_sessions(self, events: list[Event]) -> list[MediaSession]:
        media_events = [
            e for e in events
            if e.event_type in (
                "media.spotify.play",
                "media.youtube.activity",
                "media.youtube.like",
            )
        ]
        if not media_events:
            return []

        # Group into sessions: consecutive plays within 30-min gap
        sessions: list[MediaSession] = []
        current: list[Event] = [media_events[0]]

        for event in media_events[1:]:
            gap = (event.timestamp - current[-1].timestamp).total_seconds() / 60
            if gap <= 30 and event.source == current[0].source:
                current.append(event)
            else:
                sessions.append(self._session_from_events(current))
                current = [event]

        if current:
            sessions.append(self._session_from_events(current))

        return sessions

    def _session_from_events(self, events: list[Event]) -> MediaSession:
        source = "spotify" if events[0].source == "spotify" else "youtube"
        items = []
        for e in events:
            if source == "spotify":
                track = e.data.get("track_name", "Unknown")
                artist = e.data.get("artist", "")
                items.append(f"{track} by {artist}" if artist else track)
            else:
                items.append(e.data.get("title", "Unknown"))

        timestamps = [e.timestamp for e in events]
        duration = (max(timestamps) - min(timestamps)).total_seconds() / 60
        if duration == 0:
            duration = 3.0  # Single track/video

        return MediaSession(
            source=source,
            items=items,
            duration_minutes=round(duration, 1),
            first_item=min(timestamps),
            last_item=max(timestamps),
        )

    def _build_time_blocks(self, events: list[Event]) -> list[TimeBlock]:
        block_map: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for event in events:
            block = event.timestamp.hour // 2
            block_map[block][event.source] += 1

        return [
            TimeBlock(block=b, sources=dict(sources))
            for b, sources in sorted(block_map.items())
        ]

    def _build_dev_activities(self, events: list[Event]) -> list[DevActivity]:
        rows: list[DevActivity] = []
        for e in events:
            if e.event_type not in _DEV_EVENT_TYPES:
                continue
            rows.append(
                DevActivity(
                    title=str(e.data.get("title", "")),
                    provider=str(e.data.get("provider", e.source)),
                    action=str(e.data.get("action", e.event_type)),
                    repo=str(e.data.get("repo", "")),
                    timestamp=e.timestamp,
                    url=str(e.data.get("url", "")),
                )
            )
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return rows[:40]

    def _build_finance_summary(self, events: list[Event]) -> FinanceDaySummary | None:
        if not events:
            return None
        omit_amounts = any(bool(e.data.get("omit_amount_in_digest")) for e in events)
        by_merchant: dict[str, list[float]] = defaultdict(list)
        for e in events:
            name = str(e.data.get("name") or e.data.get("merchant_name") or "Unknown")
            amt = e.data.get("amount")
            try:
                f = float(amt) if amt is not None else 0.0
            except (TypeError, ValueError):
                f = 0.0
            if f > 0:
                by_merchant[name].append(f)
        merchant_spend = [(m, sum(vals)) for m, vals in by_merchant.items()]
        merchant_spend.sort(key=lambda x: x[1], reverse=True)
        merchant_counts = [(m, len(vals)) for m, vals in by_merchant.items()]
        merchant_counts.sort(key=lambda x: x[1], reverse=True)
        total = sum(sum(v) for v in by_merchant.values())
        return FinanceDaySummary(
            transaction_count=len(events),
            total_outflow=total,
            merchant_counts=merchant_counts[:10],
            merchant_spend=merchant_spend[:10],
            omit_amounts=omit_amounts,
        )

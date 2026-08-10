"""EventPreprocessor — clusters raw events into structured summaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from pulse.analysis.signal import (
    BULK_CATEGORIES,
    HIGH_SIGNAL_CATEGORIES,
    is_bulk_email,
)
from pulse.domain.event_types import DEV_EVENT_TYPES
from pulse.domain.events import Event

# Browsing time-estimation (sessionization). A gap between consecutive visits to a
# domain shorter than the session threshold is treated as continuous browsing; a
# larger gap is a return visit and counts only a small fixed dwell.
_SESSION_GAP_MINUTES = 10.0
_DWELL_MINUTES = 1.0


def _maybe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    is_promotional: bool = False  # bulk/marketing/social — low signal


def _thread_is_promotional(thread_events: list[Event], senders: list[str]) -> bool:
    categories = [
        str(e.data.get("category")) for e in thread_events if e.data.get("category")
    ]
    if categories:
        if not set(categories).isdisjoint(HIGH_SIGNAL_CATEGORIES):
            return False
        if not set(categories).isdisjoint(BULK_CATEGORIES):
            return True
    return is_bulk_email(categories[0] if categories else None, senders)


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


@dataclass(slots=True)
class HealthDay:
    day: str
    sleep_score: int | None = None
    sleep_duration_seconds: int | None = None
    time_in_bed_seconds: int | None = None
    sleep_efficiency: int | None = None
    deep_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    readiness_score: int | None = None
    activity_score: int | None = None
    steps: int | None = None
    active_calories: int | None = None
    equivalent_walking_distance_meters: int | None = None


@dataclass(slots=True)
class HealthWorkout:
    title: str
    start: datetime
    duration_minutes: float
    calories: int | None
    intensity: str | None


@dataclass(slots=True)
class PreprocessedDay:
    browsing_clusters: list[TopicCluster] = field(default_factory=list)
    email_threads: list[EmailThread] = field(default_factory=list)
    calendar_blocks: list[CalendarBlock] = field(default_factory=list)
    media_sessions: list[MediaSession] = field(default_factory=list)
    dev_activities: list[DevActivity] = field(default_factory=list)
    finance_summary: FinanceDaySummary | None = None
    health_days: list[HealthDay] = field(default_factory=list)
    health_workouts: list[HealthWorkout] = field(default_factory=list)
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
            calendar_blocks=self._build_calendar_blocks(
                by_type.get("calendar.event", [])
            ),
            media_sessions=self._build_media_sessions(sorted_events),
            dev_activities=self._build_dev_activities(sorted_events),
            finance_summary=self._build_finance_summary(finance_events),
            health_days=self._build_health_days(
                by_type.get("health.sleep", []),
                by_type.get("health.readiness", []),
                by_type.get("health.activity", []),
            ),
            health_workouts=self._build_health_workouts(
                by_type.get("health.workout", []),
            ),
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

            # Estimate on-site time by sessionizing visits. Browser history only has
            # visit timestamps, not dwell time. A gap within a session (short) is
            # continuous browsing and counts as-is; a gap larger than the session
            # threshold means the user left and returned later, so it counts only a
            # small fixed dwell — otherwise revisits spread across the day inflate the
            # estimate (e.g. 12 hourly lookups reading as hours instead of minutes).
            timestamps = sorted(e.timestamp for e in domain_events)
            total_minutes = _DWELL_MINUTES  # dwell for the final (or only) visit
            for i in range(1, len(timestamps)):
                gap = (timestamps[i] - timestamps[i - 1]).total_seconds() / 60
                if gap <= _SESSION_GAP_MINUTES:
                    total_minutes += gap
                else:
                    total_minutes += _DWELL_MINUTES

            clusters.append(
                TopicCluster(
                    domain=domain,
                    titles=unique_titles,
                    visit_count=len(seen_urls),
                    estimated_minutes=round(total_minutes, 1),
                    first_visit=timestamps[0],
                    last_visit=timestamps[-1],
                )
            )

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
                    normalized = normalized[len(prefix) :]
            normalized = normalized.strip() or "(no subject)"
            threads[normalized].append(event)

        result = []
        for subject, thread_events in threads.items():
            senders = list(
                dict.fromkeys(
                    (e.data.get("from") or e.data.get("sender") or "").strip()
                    for e in thread_events
                    if (e.data.get("from") or e.data.get("sender"))
                )
            )
            result.append(
                EmailThread(
                    subject=subject,
                    message_count=len(thread_events),
                    senders=senders,
                    is_active=len(thread_events) >= 3,
                    is_promotional=_thread_is_promotional(thread_events, senders),
                )
            )

        # Real correspondence first, then active threads, then by message count.
        result.sort(key=lambda t: (t.is_promotional, not t.is_active, -t.message_count))
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

            blocks.append(
                CalendarBlock(
                    title=title,
                    start=start,
                    duration_minutes=30.0,  # Default; calendar API doesn't give end time
                    back_to_back=back_to_back,
                )
            )

        return blocks

    def _build_media_sessions(self, events: list[Event]) -> list[MediaSession]:
        media_events = [
            e
            for e in events
            if e.event_type
            in (
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
            if e.event_type not in DEV_EVENT_TYPES:
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

    def _build_health_days(
        self,
        sleep_events: list[Event],
        readiness_events: list[Event],
        activity_events: list[Event],
    ) -> list[HealthDay]:
        sleep_by_day: dict[str, Event] = {}
        for e in sleep_events:
            day = e.data.get("day")
            if isinstance(day, str) and day:
                sleep_by_day[day] = e
        readiness_by_day: dict[str, Event] = {}
        for e in readiness_events:
            day = e.data.get("day")
            if isinstance(day, str) and day:
                readiness_by_day[day] = e
        activity_by_day: dict[str, Event] = {}
        for e in activity_events:
            day = e.data.get("day")
            if isinstance(day, str) and day:
                activity_by_day[day] = e
        all_days = sorted(
            set(sleep_by_day) | set(readiness_by_day) | set(activity_by_day),
            reverse=True,
        )
        out: list[HealthDay] = []
        for d in all_days[:14]:
            se = sleep_by_day.get(d)
            re = readiness_by_day.get(d)
            ae = activity_by_day.get(d)
            out.append(
                HealthDay(
                    day=d,
                    sleep_score=_maybe_int(se.data.get("score") if se else None),
                    sleep_duration_seconds=_maybe_int(
                        se.data.get("total_sleep_seconds") if se else None
                    ),
                    time_in_bed_seconds=_maybe_int(
                        se.data.get("time_in_bed_seconds") if se else None
                    ),
                    sleep_efficiency=_maybe_int(
                        se.data.get("efficiency") if se else None
                    ),
                    deep_sleep_seconds=_maybe_int(
                        se.data.get("deep_sleep_seconds") if se else None
                    ),
                    rem_sleep_seconds=_maybe_int(
                        se.data.get("rem_sleep_seconds") if se else None
                    ),
                    light_sleep_seconds=_maybe_int(
                        se.data.get("light_sleep_seconds") if se else None
                    ),
                    readiness_score=_maybe_int(re.data.get("score") if re else None),
                    activity_score=_maybe_int(ae.data.get("score") if ae else None),
                    steps=_maybe_int(ae.data.get("steps") if ae else None),
                    active_calories=_maybe_int(
                        ae.data.get("active_calories") if ae else None
                    ),
                    equivalent_walking_distance_meters=_maybe_int(
                        ae.data.get("equivalent_walking_distance_meters")
                        if ae
                        else None
                    ),
                )
            )
        return out

    def _build_health_workouts(self, events: list[Event]) -> list[HealthWorkout]:
        rows: list[HealthWorkout] = []
        for e in events:
            dur_s = e.data.get("duration_seconds")
            try:
                dm = float(dur_s) / 60.0 if dur_s is not None else 0.0
            except (TypeError, ValueError):
                dm = 0.0
            intens = e.data.get("intensity")
            intens_s = (
                str(intens) if intens is not None and str(intens).strip() else None
            )
            rows.append(
                HealthWorkout(
                    title=str(e.data.get("title") or "Workout"),
                    start=e.timestamp,
                    duration_minutes=round(dm, 1),
                    calories=_maybe_int(e.data.get("calories")),
                    intensity=intens_s,
                )
            )
        rows.sort(key=lambda r: r.start, reverse=True)
        return rows[:20]

    def _build_finance_summary(self, events: list[Event]) -> FinanceDaySummary | None:
        if not events:
            return None
        omit_amounts = any(
            bool(
                e.data.get("omit_amount_in_summary")
                or e.data.get("omit_amount_in_digest")  # legacy Plaid field name
            )
            for e in events
        )
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

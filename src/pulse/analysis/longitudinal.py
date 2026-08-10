"""Long-horizon structure: what is true about someone over months.

The change surface answers "what is different this week", which turns out to be the
wrong question. A week-scale change is something the user did days ago and remembers
doing; reporting it back is the restatement problem in a new costume. Recent is not
the same as unknown.

What a person genuinely cannot see about themselves is structure that only exists at
a scale they cannot hold in their head:

* **composition drift** — how the mix of what they do has shifted over a year, which
  is invisible day to day because each day looks like the last;
* **rotation** — whether attention moves through phases rather than accumulating, so
  today's focus is predictably temporary;
* **circadian phase** — when they sleep and how far that has moved;
* **attention structure** — which activities hold them and which they only ever touch
  in fragments, which is not the same as which they spend the most time on;
* **dormancy** — what quietly stopped, which leaves no memory at all because
  stopping is not an event;
* **seasonality** — what recurs annually.

Everything here is normalised against total volume for the period. Raw counts across
a long horizon are dominated by changes in how much data exists rather than changes in
behaviour, and chasing an un-normalised trend is exactly the drifting-baseline error
that corrupted the old vault patterns.

This layer computes statistics and does not name topics. Grouping domains into
"chemistry" or "infrastructure" is interpretation, and interpretation belongs to the
agent, which can see titles and knows the user. Hard-coding the categories here would
bake in the analyst's assumptions and cap what can ever be discovered.
"""

from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pulse.analysis.entities import entity_key, entity_parent
from pulse.analysis.signal import is_bulk_event
from pulse.domain.events import Event

# A month needs this much data before its shares mean anything.
MIN_MONTH_EVENTS = 200
# An entity needs this much presence before its trend is worth reporting.
MIN_ENTITY_EVENTS = 60
MIN_MONTHS_PRESENT = 3
# Share change versus peak that counts as a collapse or a rise.
COLLAPSE_FRACTION = 0.25
RISE_MULTIPLE = 2.0
# Months of the entity's own recent past that a trend is judged against.
PRIOR_MONTHS = 4
# An entity has to have been a real part of the mix before its decline is a finding.
# Everything peaks and most things decay; only a peak worth noticing makes a story.
MIN_MEANINGFUL_SHARE = 1.5
# Hard cap so the agent gets a shortlist to reason about, never a spreadsheet.
MAX_TRENDS = 20
# Sustained for this long, then silent for this long → dormant.
DORMANT_MIN_SPAN_DAYS = 42
DORMANT_MIN_SILENT_DAYS = 56
# Sessions: a gap under this continues one; at or over this anchors "deep".
SESSION_GAP_MINUTES = 10.0
DEEP_SESSION_MINUTES = 30.0
# Time charged to a session containing a single event, which has no measurable span.
DWELL_MINUTES = 1.0
# Local hour that starts a new "night" for sleep-proxy purposes.
NIGHT_BOUNDARY_HOUR = 5
# Plausible bounds for an inferred sleep gap, in hours.
MIN_SLEEP_GAP = 3.0
MAX_SLEEP_GAP = 14.0


@dataclass(slots=True)
class MonthShare:
    month: str
    count: int
    share: float


@dataclass(slots=True)
class EntityTrend:
    kind: str
    key: str
    total: int
    months: list[MonthShare]
    peak_share: float
    peak_month: str
    recent_share: float
    classification: str  # rising | collapsed | declining | steady
    fraction_of_peak: float

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(slots=True)
class SleepPhase:
    period: str
    nights: int
    bedtime_hour: float
    wake_hour: float
    gap_hours: float


@dataclass(slots=True)
class AttentionProfile:
    kind: str
    key: str
    total_minutes: float
    deep_fraction: float
    sessions_anchored: int
    median_session_minutes: float

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(slots=True)
class Dormancy:
    kind: str
    key: str
    total: int
    span_days: int
    silent_days: int
    last_seen: str

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(slots=True)
class LongitudinalProfile:
    start: str
    end: str
    total_events: int
    months_covered: int
    entity_trends: list[EntityTrend] = field(default_factory=list)
    sleep_phases: list[SleepPhase] = field(default_factory=list)
    attention: list[AttentionProfile] = field(default_factory=list)
    dormant: list[Dormancy] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.entity_trends or self.sleep_phases or self.attention or self.dormant
        )


def _month(d: datetime) -> str:
    return f"{d.year}-{d.month:02d}"


def _usable(events: list[Event]) -> list[Event]:
    """Drop bulk mail; it reflects senders' behaviour, not the user's."""
    return [e for e in events if not is_bulk_event(e)]


# ----------------------------------------------------------------------
# Composition drift
# ----------------------------------------------------------------------


def entity_trends(
    events: list[Event],
    *,
    min_entity_events: int = MIN_ENTITY_EVENTS,
    recent_months: int = 2,
) -> list[EntityTrend]:
    """Per-entity monthly share of all activity, and where it sits versus its peak.

    Shares, never counts: total volume swings by an order of magnitude across a year,
    so a raw count trend mostly measures how much history exists.
    """
    usable = _usable(events)
    month_totals = Counter(_month(e.timestamp) for e in usable)
    months = sorted(m for m, n in month_totals.items() if n >= MIN_MONTH_EVENTS)
    if len(months) < MIN_MONTHS_PRESENT:
        return []
    month_index = {m: i for i, m in enumerate(months)}

    # Group siblings under one parent. A self-hosted stack going quiet is one fact
    # about the user, not eleven; reported per-subdomain it drowns everything else.
    per_entity: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for event in usable:
        key = entity_key(event)
        if key is None:
            continue
        m = _month(event.timestamp)
        if m in month_index:
            per_entity[(key[0], entity_parent(*key))][m] += 1

    out: list[EntityTrend] = []
    for (kind, name), counts in per_entity.items():
        total = sum(counts.values())
        if total < min_entity_events:
            continue
        present = [m for m in months if counts.get(m)]
        if len(present) < MIN_MONTHS_PRESENT:
            continue

        series = [
            MonthShare(m, counts.get(m, 0), counts.get(m, 0) / month_totals[m] * 100)
            for m in months
        ]
        peak = max(series, key=lambda s: s.share)
        tail = series[-recent_months:] or series[-1:]
        recent = st.mean(s.share for s in tail)
        # Compare against the entity's own recent past, not the start of the window.
        # Anchoring on the first months made anything absent back then read as
        # "rising" even while sitting at a third of its peak.
        prior = series[-(recent_months + PRIOR_MONTHS) : -recent_months] or series[:1]
        prior_median = st.median([s.share for s in prior])

        fraction = recent / peak.share if peak.share else 0.0
        peak_is_old = peak.month not in {
            s.month for s in series[-(recent_months + 1) :]
        }

        if (
            peak.share >= MIN_MEANINGFUL_SHARE
            and fraction <= COLLAPSE_FRACTION
            and peak_is_old
        ):
            classification = "collapsed"
        elif prior_median and recent >= prior_median * RISE_MULTIPLE:
            classification = "rising"
        elif prior_median and recent <= prior_median / RISE_MULTIPLE:
            classification = "declining"
        else:
            classification = "steady"

        out.append(
            EntityTrend(
                kind=kind,
                key=name,
                total=total,
                months=series,
                peak_share=round(peak.share, 2),
                peak_month=peak.month,
                recent_share=round(recent, 2),
                classification=classification,
                fraction_of_peak=round(fraction, 2),
            )
        )

    # Rank by how large a part of life the entity ever was, not by raw volume, and
    # drop the steady majority: "unchanged" is not a finding, and a long list of
    # everything past its peak is the noise this layer exists to avoid.
    moved = [t for t in out if t.classification != "steady"]
    moved.sort(key=lambda t: t.peak_share, reverse=True)
    return moved[:MAX_TRENDS]


# ----------------------------------------------------------------------
# Circadian phase
# ----------------------------------------------------------------------


def _night_of(d: datetime) -> date:
    return (d - timedelta(hours=NIGHT_BOUNDARY_HOUR)).date()


def sleep_phases(events: list[Event], *, period_months: int = 3) -> list[SleepPhase]:
    """Infer bedtime/wake from the daily silence, bucketed into periods.

    This is a proxy: the last event before a long silence and the first after it. It
    cannot see sleep, only the absence of activity, so it is directional evidence
    about *phase drift* rather than a measurement of sleep.
    """
    by_night: dict[date, list[datetime]] = defaultdict(list)
    for event in events:
        by_night[_night_of(event.timestamp)].append(event.timestamp)
    if not by_night:
        return []

    nights = sorted(by_night)
    buckets: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for a, b in zip(nights, nights[1:]):
        if (b - a).days != 1:
            continue
        last, first = max(by_night[a]), min(by_night[b])
        gap = (first - last).total_seconds() / 3600
        if not (MIN_SLEEP_GAP <= gap <= MAX_SLEEP_GAP):
            continue
        # Put after-midnight bedtimes on a continuous scale so the median does not
        # collapse to noon when times straddle 00:00.
        bed = last.hour + last.minute / 60
        bed = bed + 24 if bed < 12 else bed
        wake = first.hour + first.minute / 60
        quarter = (a.month - 1) // period_months + 1
        buckets[f"{a.year}P{quarter}"].append((bed, wake, gap))

    out: list[SleepPhase] = []
    for period in sorted(buckets):
        rows = buckets[period]
        if len(rows) < 10:
            continue
        out.append(
            SleepPhase(
                period=period,
                nights=len(rows),
                bedtime_hour=round(st.median(r[0] for r in rows) % 24, 2),
                wake_hour=round(st.median(r[1] for r in rows), 2),
                gap_hours=round(st.median(r[2] for r in rows), 2),
            )
        )
    return out


# ----------------------------------------------------------------------
# Attention structure
# ----------------------------------------------------------------------


def _sessionize(events: list[Event]) -> list[list[Event]]:
    ordered = sorted(events, key=lambda e: e.timestamp)
    if not ordered:
        return []
    sessions: list[list[Event]] = []
    current = [ordered[0]]
    for prev, nxt in zip(ordered, ordered[1:]):
        gap = (nxt.timestamp - prev.timestamp).total_seconds() / 60
        if gap <= SESSION_GAP_MINUTES:
            current.append(nxt)
        else:
            sessions.append(current)
            current = [nxt]
    sessions.append(current)
    return sessions


def attention_profile(
    events: list[Event], *, min_minutes: float = 60.0
) -> list[AttentionProfile]:
    """How much of each entity's time is spent in deep sessions rather than glances.

    Total time answers "where do the hours go". This answers something different and
    less visible: what actually holds attention. An entity can absorb many hours purely
    in fragments, which is a different relationship from one that anchors long sessions.
    """
    sessions = _sessionize(events)
    total: Counter = Counter()
    deep: Counter = Counter()
    anchored: Counter = Counter()
    lengths: dict[tuple[str, str], list[float]] = defaultdict(list)

    for session in sessions:
        span = (session[-1].timestamp - session[0].timestamp).total_seconds() / 60
        # A one-event session has zero span. Charging it zero time would erase purely
        # glanced-at entities from the profile entirely, when "only ever glanced at"
        # is precisely the finding worth having. Count a small fixed dwell instead,
        # matching how the digest estimates isolated visits.
        minutes = max(span, DWELL_MINUTES)
        keys = [k for k in (entity_key(e) for e in session) if k is not None]
        if not keys:
            continue
        counts = Counter(keys)
        for key, n in counts.items():
            share = minutes * n / len(keys)
            total[key] += share
            lengths[key].append(minutes)
            if minutes >= DEEP_SESSION_MINUTES:
                deep[key] += share
        if minutes >= DEEP_SESSION_MINUTES:
            anchored[counts.most_common(1)[0][0]] += 1

    out: list[AttentionProfile] = []
    for key, minutes in total.items():
        if minutes < min_minutes:
            continue
        kind, name = key
        out.append(
            AttentionProfile(
                kind=kind,
                key=name,
                total_minutes=round(minutes, 1),
                deep_fraction=round(deep[key] / minutes, 3) if minutes else 0.0,
                sessions_anchored=anchored.get(key, 0),
                median_session_minutes=round(st.median(lengths[key]), 1),
            )
        )
    out.sort(key=lambda a: a.total_minutes, reverse=True)
    return out


# ----------------------------------------------------------------------
# Dormancy
# ----------------------------------------------------------------------


def dormant_entities(
    events: list[Event], *, as_of: date, min_events: int = 100
) -> list[Dormancy]:
    """Entities that were sustained for a while and then stopped.

    Stopping is not an event, so it leaves no memory and no notification. This is the
    only lane here that reports an absence, and it is safe precisely because it is
    computed rather than inferred from a window that happens to be quiet.
    """
    by_entity: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for event in events:
        key = entity_key(event)
        if key is not None:
            by_entity[key].append(event.timestamp)

    out: list[Dormancy] = []
    for (kind, name), stamps in by_entity.items():
        if len(stamps) < min_events:
            continue
        first, last = min(stamps).date(), max(stamps).date()
        span = (last - first).days
        silent = (as_of - last).days
        if span >= DORMANT_MIN_SPAN_DAYS and silent >= DORMANT_MIN_SILENT_DAYS:
            out.append(
                Dormancy(
                    kind=kind,
                    key=name,
                    total=len(stamps),
                    span_days=span,
                    silent_days=silent,
                    last_seen=last.isoformat(),
                )
            )
    out.sort(key=lambda d: d.total, reverse=True)
    return out


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------


def build_longitudinal_profile(
    events: list[Event], *, as_of: date
) -> LongitudinalProfile:
    if not events:
        return LongitudinalProfile(
            start="",
            end="",
            total_events=0,
            months_covered=0,
            notes=["No events in range."],
        )

    stamps = [e.timestamp for e in events]
    months = {_month(t) for t in stamps}
    profile = LongitudinalProfile(
        start=min(stamps).date().isoformat(),
        end=max(stamps).date().isoformat(),
        total_events=len(events),
        months_covered=len(months),
    )

    if len(months) < MIN_MONTHS_PRESENT:
        profile.notes.append(
            f"Only {len(months)} month(s) of history; long-horizon structure needs "
            f"at least {MIN_MONTHS_PRESENT}. Trends are omitted."
        )
    else:
        profile.entity_trends = entity_trends(events)

    profile.sleep_phases = sleep_phases(events)
    profile.attention = attention_profile(events)
    profile.dormant = dormant_entities(events, as_of=as_of)
    return profile

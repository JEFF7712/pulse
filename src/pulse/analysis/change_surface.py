"""Change surface — what is different about a window, versus its trailing baseline.

This layer does not decide what is *interesting*. It concentrates attention on the
small fraction of a window that departs from the user's own history, so an agent can
reason over that instead of re-reading a whole day and inventing significance for it.

Two kinds of lane:

* **Exact / statistical** — entities that are new, returning after dormancy, or well
  off their baseline rate. Cheap, and the shapes are known in advance.
* **Embedding novelty** — events whose text sits far from everything in the baseline,
  grouped into clusters. Shape-agnostic: it can surface a kind of activity nobody
  wrote a rule for, which is the point.

Correlating these signals with each other is deliberately *not* done here. Pairing
same-day entities is a cartesian product that yields hundreds of coincidences and no
insight, which is precisely the manufactured-pattern failure this layer exists to
avoid. Deciding that two changes are related is interpretation, and interpretation is
the agent's job; this layer only says what moved.

Everything here is deterministic. An empty surface is a normal, common result and
means no agent needs to be woken.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from pulse.analysis.entities import entity_key, entity_label, entity_parent
from pulse.analysis.signal import is_bulk_event
from pulse.domain.events import Event

# An entity must clear this many events in the window before "new" is worth saying.
# One stray visit to a domain is noise, not a change in what someone is doing.
MIN_NEW_ENTITY_COUNT = 3
# Absent this many days, then back → "returning" rather than merely present.
DORMANT_DAYS = 21
# Rate change versus baseline needed to count as a shift, in both directions.
SPIKE_RATIO = 3.0
DROP_RATIO = 0.25
# An entity needs a real baseline before a ratio against it means anything.
MIN_BASELINE_EVENTS = 10
# Cosine distance from the nearest baseline centroid, above which an event is novel.
# Calibrated against a real store: the distribution is tight (median ~0.15) and this
# sits near the 97th percentile, so a week yields a handful of candidates, not a list.
NOVELTY_THRESHOLD = 0.32
MIN_CLUSTER_SIZE = 2
# Pure-Python fallback cost is O(window x centroids x dim); cap the centroids.
MAX_CENTROIDS_PURE_PYTHON = 400


@dataclass(slots=True)
class EntityDelta:
    kind: str
    key: str
    status: str  # new | returning | spike | drop
    count: int
    baseline_daily: float
    ratio: float | None
    last_seen_before: str | None = None
    sample_titles: list[str] = field(default_factory=list)
    # Set when sibling subdomains were merged into this row.
    merged_from: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return entity_label(self.kind, self.key)


@dataclass(slots=True)
class NovelCluster:
    event_ids: list[str]
    novelty: float
    sources: list[str]
    sample_titles: list[str]


@dataclass(slots=True)
class ChangeSurface:
    window_start: str
    window_end: str
    baseline_start: str
    baseline_end: str
    window_events: int
    baseline_events: int
    entity_deltas: list[EntityDelta] = field(default_factory=list)
    novel_clusters: list[NovelCluster] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.entity_deltas or self.novel_clusters)

    def signal_count(self) -> int:
        return len(self.entity_deltas) + len(self.novel_clusters)


def _title_of(event: Event) -> str:
    data = event.data or {}
    for key in ("title", "subject", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _day_of(event: Event) -> str:
    return event.timestamp.date().isoformat()


def _index_by_entity(events: list[Event]) -> dict[tuple[str, str], list[Event]]:
    grouped: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        key = entity_key(event)
        if key is not None:
            grouped[key].append(event)
    return grouped


def _samples(events: list[Event], limit: int = 3) -> list[str]:
    seen: list[str] = []
    for event in events:
        title = _title_of(event)
        if title and title not in seen:
            seen.append(title)
        if len(seen) >= limit:
            break
    return seen


def compute_entity_deltas(
    window: list[Event],
    baseline: list[Event],
    *,
    baseline_days: int,
    window_days: int,
    window_end: date,
) -> list[EntityDelta]:
    """Entities that are new, returning after dormancy, or off their baseline rate."""
    window_by_entity = _index_by_entity(window)
    baseline_by_entity = _index_by_entity(baseline)
    span = max(baseline_days, 1)
    deltas: list[EntityDelta] = []

    for key, events in window_by_entity.items():
        kind, name = key
        count = len(events)
        prior = baseline_by_entity.get(key, [])
        baseline_daily = len(prior) / span

        # The volume threshold is applied *after* sibling collapse: five subdomains
        # with one visit each is still five visits to a site that is new.
        if not prior:
            deltas.append(
                EntityDelta(
                    kind=kind,
                    key=name,
                    status="new",
                    count=count,
                    baseline_daily=0.0,
                    ratio=None,
                    sample_titles=_samples(events),
                )
            )
            continue

        last_before = max(e.timestamp for e in prior)
        dormant_for = (window_end - last_before.date()).days
        if dormant_for >= DORMANT_DAYS:
            deltas.append(
                EntityDelta(
                    kind=kind,
                    key=name,
                    status="returning",
                    count=count,
                    baseline_daily=round(baseline_daily, 2),
                    ratio=None,
                    last_seen_before=last_before.date().isoformat(),
                    sample_titles=_samples(events),
                )
            )
            continue

        # A ratio against a thin baseline is arithmetic, not evidence.
        if len(prior) < MIN_BASELINE_EVENTS or baseline_daily <= 0:
            continue

        # Divide by the nominal window length, not by the days that happen to carry
        # events. Dividing by "days present" inflates the rate of anything bursty and
        # makes every concentrated session look like a spike.
        window_daily = count / max(window_days, 1)
        ratio = window_daily / baseline_daily
        if ratio >= SPIKE_RATIO:
            status = "spike"
        elif ratio <= DROP_RATIO:
            status = "drop"
        else:
            continue
        deltas.append(
            EntityDelta(
                kind=kind,
                key=name,
                status=status,
                count=count,
                baseline_daily=round(baseline_daily, 2),
                ratio=round(ratio, 2),
                sample_titles=_samples(events),
            )
        )

    deltas = _collapse_sibling_deltas(deltas, window_days=window_days)
    deltas = [
        d
        for d in deltas
        if d.status not in ("new", "returning") or d.count >= MIN_NEW_ENTITY_COUNT
    ]
    deltas.sort(key=lambda d: d.count, reverse=True)
    return deltas


def _collapse_sibling_deltas(
    deltas: list[EntityDelta], *, window_days: int
) -> list[EntityDelta]:
    """Merge same-status siblings under one registrable domain into a single row.

    `parchment.com`, `auth.parchment.com` and `registration.parchment.com` all going
    new at once is one event in the user's life reported three times. Collapsing only
    same-status siblings keeps the case that matters: a genuinely new subdomain of a
    site whose parent is *not* new still stands on its own.
    """
    grouped: dict[tuple[str, str, str], list[EntityDelta]] = defaultdict(list)
    for delta in deltas:
        grouped[
            (delta.kind, entity_parent(delta.kind, delta.key), delta.status)
        ].append(delta)

    out: list[EntityDelta] = []
    for (kind, parent, status), members in grouped.items():
        if len(members) == 1:
            out.append(members[0])
            continue
        total = sum(m.count for m in members)
        baseline_daily = sum(m.baseline_daily for m in members)
        titles: list[str] = []
        for member in members:
            for title in member.sample_titles:
                if title not in titles:
                    titles.append(title)
        last_seen = [m.last_seen_before for m in members if m.last_seen_before]
        out.append(
            EntityDelta(
                kind=kind,
                key=parent,
                status=status,
                count=total,
                baseline_daily=round(baseline_daily, 2),
                ratio=(
                    round((total / max(window_days, 1)) / baseline_daily, 2)
                    if status in ("spike", "drop") and baseline_daily > 0
                    else None
                ),
                last_seen_before=max(last_seen) if last_seen else None,
                sample_titles=titles[:3],
                merged_from=sorted(m.key for m in members),
            )
        )
    return out


# ----------------------------------------------------------------------
# Embedding novelty
# ----------------------------------------------------------------------


def _centroids(
    baseline: list[Event], vectors: dict[str, list[float]], cap: int | None
) -> list[list[float]]:
    """Average the baseline into one vector per entity.

    All-pairs against every historical event is quadratic and far too slow in pure
    Python at dim 512. Per-entity centroids keep the comparison meaningful (an event
    is novel when it is unlike anything the user habitually does) at a fraction of it.
    """
    sums: dict[tuple[str, str], list[float]] = {}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for event in baseline:
        vec = vectors.get(event.id)
        if vec is None:
            continue
        key = entity_key(event)
        if key is None:
            continue
        acc = sums.get(key)
        if acc is None:
            sums[key] = list(vec)
        else:
            for i, value in enumerate(vec):
                acc[i] += value
        counts[key] += 1

    ordered = sorted(counts, key=lambda k: counts[k], reverse=True)
    if cap is not None:
        ordered = ordered[:cap]

    out: list[list[float]] = []
    for key in ordered:
        n = counts[key]
        out.append([value / n for value in sums[key]])
    return out


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _max_similarity_pure(
    window_vecs: list[list[float]], centroids: list[list[float]]
) -> list[float]:
    unit_centroids = [_normalise(c) for c in centroids]
    out: list[float] = []
    for vec in window_vecs:
        unit = _normalise(vec)
        best = -1.0
        for centroid in unit_centroids:
            dot = 0.0
            for a, b in zip(unit, centroid):
                dot += a * b
            if dot > best:
                best = dot
        out.append(best)
    return out


def _max_similarity(
    window_vecs: list[list[float]], centroids: list[list[float]]
) -> list[float]:
    try:
        import numpy as np
    except ImportError:
        return _max_similarity_pure(window_vecs, centroids[:MAX_CENTROIDS_PURE_PYTHON])

    w = np.asarray(window_vecs, dtype=np.float32)
    c = np.asarray(centroids, dtype=np.float32)
    w /= np.maximum(np.linalg.norm(w, axis=1, keepdims=True), 1e-12)
    c /= np.maximum(np.linalg.norm(c, axis=1, keepdims=True), 1e-12)
    return (w @ c.T).max(axis=1).tolist()


def compute_novel_clusters(
    window: list[Event],
    baseline: list[Event],
    vectors: dict[str, list[float]],
    *,
    threshold: float = NOVELTY_THRESHOLD,
    centroid_cap: int | None = None,
) -> list[NovelCluster]:
    """Group window events that sit far from every baseline centroid.

    Returns an empty list when there is nothing to compare against; "everything is
    novel" on a cold store is a false alarm, not a discovery.
    """
    # Newsletters and marketing blasts are textually unique by construction, so they
    # dominate any novelty ranking while saying nothing about the user. Drop them
    # before scoring rather than trying to out-threshold them afterwards.
    window_with_vecs = [e for e in window if e.id in vectors and not is_bulk_event(e)]
    if not window_with_vecs:
        return []
    centroids = _centroids(baseline, vectors, centroid_cap)
    if len(centroids) < 5:
        return []

    sims = _max_similarity([vectors[e.id] for e in window_with_vecs], centroids)
    novel = [
        (event, 1.0 - sim)
        for event, sim in zip(window_with_vecs, sims)
        if (1.0 - sim) >= threshold
    ]
    if not novel:
        return []

    # Group by parent entity so a burst of related pages reads as one thing, and so
    # sibling subdomains (nvidia.com / marketplace.nvidia.com) do not each fall below
    # the cluster minimum on their own.
    grouped: dict[tuple[str, str], list[tuple[Event, float]]] = defaultdict(list)
    for event, novelty in novel:
        key = entity_key(event)
        parent = ("event", event.id) if key is None else (key[0], entity_parent(*key))
        grouped[parent].append((event, novelty))

    clusters: list[NovelCluster] = []
    for members in grouped.values():
        if len(members) < MIN_CLUSTER_SIZE:
            continue
        events = [e for e, _ in members]
        clusters.append(
            NovelCluster(
                event_ids=[e.id for e in events],
                novelty=round(max(n for _, n in members), 3),
                sources=sorted({e.source for e in events}),
                sample_titles=_samples(events, limit=5),
            )
        )
    clusters.sort(key=lambda c: c.novelty, reverse=True)
    return clusters


def build_change_surface(
    window: list[Event],
    baseline: list[Event],
    *,
    window_start: date,
    window_end: date,
    baseline_start: date,
    vectors: dict[str, list[float]] | None = None,
    centroid_cap: int | None = None,
) -> ChangeSurface:
    """Assemble the full change surface for a window against its trailing baseline."""
    baseline_days = max((window_start - baseline_start).days, 1)
    window_days = max((window_end - window_start).days + 1, 1)
    surface = ChangeSurface(
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        baseline_start=baseline_start.isoformat(),
        baseline_end=(window_start - timedelta(days=1)).isoformat(),
        window_events=len(window),
        baseline_events=len(baseline),
    )

    if not baseline:
        surface.notes.append(
            "No baseline events in range; change detection needs history and is skipped."
        )
        return surface

    surface.entity_deltas = compute_entity_deltas(
        window,
        baseline,
        baseline_days=baseline_days,
        window_days=window_days,
        window_end=window_end,
    )
    if vectors:
        surface.novel_clusters = compute_novel_clusters(
            window, baseline, vectors, centroid_cap=centroid_cap
        )
    else:
        surface.notes.append(
            "No embeddings available; open-ended novelty detection skipped "
            "(run `pulse embed` with the semantic extra installed)."
        )
    return surface

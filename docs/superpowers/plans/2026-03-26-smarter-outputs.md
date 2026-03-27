# Smarter Outputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat bullet-list digests and thin event summaries with a three-stage pipeline: code pre-processing, Haiku source summarization, and Sonnet discovery — producing narrative digests and higher-quality cross-source pattern detection.

**Architecture:** New `EventPreprocessor` clusters raw events by topic/thread/session. `SourceSummarizer` sends each source's clusters to Haiku for narrative summaries. Those narratives feed both a new `DigestBuilder` (narrative daily digests) and the existing `DiscoveryEngine` (with sharpened prompts). Falls back to current bullet-list format when no LLM is configured.

**Tech Stack:** Python 3.12+, existing Pulse core (aiosqlite, anthropic SDK), Haiku for summarization, Sonnet for discovery

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/pulse/analysis/preprocessor.py` | `EventPreprocessor` — clusters/groups/dedupes raw events into `PreprocessedDay` |
| `src/pulse/analysis/source_summarizer.py` | `SourceSummarizer` — Haiku pass turning preprocessed data into per-source narratives |
| `src/pulse/analysis/digest_builder.py` | `DigestBuilder` — renders narrative markdown digest from preprocessed data + LLM narratives |
| `src/pulse/analysis/prompts.py` | Modified — sharpened discovery prompt with rejection criteria |
| `src/pulse/analysis/discovery.py` | Modified — wired into preprocessor + source summarizer pipeline |
| `src/pulse/analysis/summarizer.py` | Modified — delegates to DigestBuilder when LLM available |
| `src/pulse/llm/anthropic.py` | Modified — `complete()` accepts optional `model` override |
| `src/pulse/app/config.py` | Modified — adds `summarization_model` and `discovery_model` fields |
| `src/pulse/jobs/runners.py` | Modified — passes LLM to digest job when available |

---

### Task 1: Add model override to AnthropicProvider

**Files:**
- Modify: `src/pulse/llm/anthropic.py`
- Test: `tests/unit/test_llm_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_llm_provider.py

def test_anthropic_provider_respects_model_override():
    from unittest.mock import MagicMock, patch

    with patch("anthropic.Anthropic") as MockClient:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        MockClient.return_value.messages.create.return_value = mock_response

        from pulse.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-5-20250514")

        import asyncio
        asyncio.run(provider.complete("hello", model="claude-haiku-4-5-20251001"))

        call_kwargs = MockClient.return_value.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_provider.py::test_anthropic_provider_respects_model_override -v`
Expected: FAIL — `complete()` got an unexpected keyword argument 'model'

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/llm/anthropic.py
import anthropic


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        kwargs: dict = {
            "model": model or self._model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)
        return response.content[0].text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_llm_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/llm/anthropic.py tests/unit/test_llm_provider.py
git commit -m "feat: add model override to AnthropicProvider.complete()"
```

---

### Task 2: Add config fields for summarization and discovery models

**Files:**
- Modify: `src/pulse/app/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_config.py

def test_pulse_config_has_model_defaults():
    from pulse.app.config import PulseConfig

    config = PulseConfig()
    assert config.summarization_model == "claude-haiku-4-5-20251001"
    assert config.discovery_model == "claude-sonnet-4-5-20250514"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py::test_pulse_config_has_model_defaults -v`
Expected: FAIL — `PulseConfig` has no field `summarization_model`

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/app/config.py
from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    poll_interval: str = "15m"


class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    anthropic_api_key: str | None = None
    summarization_model: str = "claude-haiku-4-5-20251001"
    discovery_model: str = "claude-sonnet-4-5-20250514"
    connectors: dict[str, ConnectorConfig] = {}


# Backward compatibility alias
Settings = PulseConfig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/config.py tests/unit/test_config.py
git commit -m "feat: add summarization_model and discovery_model config fields"
```

---

### Task 3: Build EventPreprocessor — browsing clustering

**Files:**
- Create: `src/pulse/analysis/preprocessor.py`
- Create: `tests/unit/test_preprocessor.py`

- [ ] **Step 1: Write the failing test for browsing clusters**

```python
# tests/unit/test_preprocessor.py
from datetime import UTC, datetime

from pulse.domain.events import Event


def _browsing_event(id, ts, url, title):
    return Event(
        id=id,
        timestamp=ts,
        source="browser",
        event_type="browsing.visit",
        data={"url": url, "title": title, "browser": "firefox"},
    )


def test_browsing_clusters_group_by_domain():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _browsing_event("b1", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://docs.rs/tokio/latest", "tokio - Rust"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 10, tzinfo=UTC),
                        "https://docs.rs/tokio/latest/tokio/net", "tokio::net - Rust"),
        _browsing_event("b3", datetime(2026, 3, 26, 14, 20, tzinfo=UTC),
                        "https://docs.rs/async-std/latest", "async-std - Rust"),
        _browsing_event("b4", datetime(2026, 3, 26, 15, 30, tzinfo=UTC),
                        "https://news.ycombinator.com", "Hacker News"),
        _browsing_event("b5", datetime(2026, 3, 26, 15, 35, tzinfo=UTC),
                        "https://news.ycombinator.com/item?id=123", "Show HN: something"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    # Should have browsing clusters grouped by domain
    assert len(result.browsing_clusters) >= 2
    domains = [c.domain for c in result.browsing_clusters]
    assert "docs.rs" in domains
    assert "news.ycombinator.com" in domains

    # docs.rs cluster should have 3 visits
    docs_cluster = next(c for c in result.browsing_clusters if c.domain == "docs.rs")
    assert docs_cluster.visit_count == 3
    assert docs_cluster.estimated_minutes > 0


def test_browsing_clusters_deduplicate_same_url():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _browsing_event("b1", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://example.com/page", "Page"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 5, tzinfo=UTC),
                        "https://example.com/page", "Page"),
        _browsing_event("b3", datetime(2026, 3, 26, 14, 10, tzinfo=UTC),
                        "https://example.com/other", "Other"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    cluster = next(c for c in result.browsing_clusters if c.domain == "example.com")
    assert cluster.visit_count == 2  # deduped: 2 unique URLs
    assert len(cluster.titles) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_preprocessor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/analysis/preprocessor.py
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
class PreprocessedDay:
    browsing_clusters: list[TopicCluster] = field(default_factory=list)
    email_threads: list[EmailThread] = field(default_factory=list)
    calendar_blocks: list[CalendarBlock] = field(default_factory=list)
    media_sessions: list[MediaSession] = field(default_factory=list)
    time_blocks: list[TimeBlock] = field(default_factory=list)
    raw_stats: dict[str, int] = field(default_factory=dict)


class EventPreprocessor:
    def preprocess(self, events: list[Event]) -> PreprocessedDay:
        by_type: dict[str, list[Event]] = defaultdict(list)
        source_counts: dict[str, int] = defaultdict(int)

        for event in sorted(events, key=lambda e: e.timestamp):
            by_type[event.event_type].append(event)
            source_counts[event.source] += 1

        return PreprocessedDay(
            browsing_clusters=self._cluster_browsing(by_type.get("browsing.visit", [])),
            email_threads=self._group_email_threads(by_type.get("email.received", [])),
            calendar_blocks=self._build_calendar_blocks(by_type.get("calendar.event", [])),
            media_sessions=self._build_media_sessions(events),
            time_blocks=self._build_time_blocks(events),
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
                e.data.get("from", "") for e in thread_events if e.data.get("from")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_preprocessor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/preprocessor.py tests/unit/test_preprocessor.py
git commit -m "feat: add EventPreprocessor with browsing clustering and dedup"
```

---

### Task 4: EventPreprocessor — email threading and calendar blocks

**Files:**
- Modify: `tests/unit/test_preprocessor.py`

- [ ] **Step 1: Write tests for email threading**

```python
# Append to tests/unit/test_preprocessor.py

def _email_event(id, ts, subject, sender):
    return Event(
        id=id,
        timestamp=ts,
        source="gmail",
        event_type="email.received",
        data={"subject": subject, "from": sender},
    )


def test_email_threads_group_by_subject():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _email_event("e1", datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
                      "Q2 Roadmap", "alice@co.com"),
        _email_event("e2", datetime(2026, 3, 26, 9, 30, tzinfo=UTC),
                      "Re: Q2 Roadmap", "bob@co.com"),
        _email_event("e3", datetime(2026, 3, 26, 10, 0, tzinfo=UTC),
                      "Re: Re: Q2 Roadmap", "alice@co.com"),
        _email_event("e4", datetime(2026, 3, 26, 11, 0, tzinfo=UTC),
                      "Lunch?", "carol@co.com"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    assert len(result.email_threads) == 2
    roadmap = next(t for t in result.email_threads if t.subject == "Q2 Roadmap")
    assert roadmap.message_count == 3
    assert roadmap.is_active is True
    assert "alice@co.com" in roadmap.senders
    assert "bob@co.com" in roadmap.senders

    lunch = next(t for t in result.email_threads if t.subject == "Lunch?")
    assert lunch.message_count == 1
    assert lunch.is_active is False


def test_calendar_blocks_detect_back_to_back():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        Event(id="c1", timestamp=datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "Standup"}),
        Event(id="c2", timestamp=datetime(2026, 3, 26, 9, 15, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "Design Review"}),
        Event(id="c3", timestamp=datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
              source="calendar", event_type="calendar.event",
              data={"title": "1:1"}),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    assert len(result.calendar_blocks) == 3
    assert result.calendar_blocks[0].back_to_back is True  # Standup -> Design Review
    assert result.calendar_blocks[1].back_to_back is False  # gap to 1:1
    assert result.calendar_blocks[2].back_to_back is False  # last event


def test_time_blocks_group_by_2h_windows():
    from pulse.analysis.preprocessor import EventPreprocessor

    events = [
        _email_event("e1", datetime(2026, 3, 26, 9, 0, tzinfo=UTC), "A", "a@co.com"),
        _email_event("e2", datetime(2026, 3, 26, 9, 30, tzinfo=UTC), "B", "b@co.com"),
        _browsing_event("b1", datetime(2026, 3, 26, 9, 15, tzinfo=UTC),
                        "https://example.com", "Example"),
        _browsing_event("b2", datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                        "https://example.com", "Example"),
    ]

    preprocessor = EventPreprocessor()
    result = preprocessor.preprocess(events)

    # Block 4 = 08:00-10:00 should have gmail:2, browser:1
    block_4 = next(b for b in result.time_blocks if b.block == 4)
    assert block_4.sources["gmail"] == 2
    assert block_4.sources["browser"] == 1

    # Block 7 = 14:00-16:00 should have browser:1
    block_7 = next(b for b in result.time_blocks if b.block == 7)
    assert block_7.sources["browser"] == 1
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_preprocessor.py -v`
Expected: All PASS (implementation already handles these in Task 3)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_preprocessor.py
git commit -m "test: add email threading and calendar block tests for preprocessor"
```

---

### Task 5: Build SourceSummarizer (Haiku pass)

**Files:**
- Create: `src/pulse/analysis/source_summarizer.py`
- Create: `tests/unit/test_source_summarizer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_source_summarizer.py
import asyncio
from datetime import UTC, datetime

from pulse.analysis.preprocessor import (
    EmailThread,
    PreprocessedDay,
    TopicCluster,
    CalendarBlock,
    MediaSession,
    TimeBlock,
)


class FakeLLM:
    def __init__(self):
        self.calls: list[dict] = []

    async def complete(self, prompt, *, system_prompt=None, model=None):
        self.calls.append({"prompt": prompt, "model": model})
        return f"Summary for prompt about {len(prompt)} chars."


def _sample_preprocessed_day():
    return PreprocessedDay(
        browsing_clusters=[
            TopicCluster(
                domain="docs.rs",
                titles=["tokio - Rust", "tokio::net"],
                visit_count=5,
                estimated_minutes=45.0,
                first_visit=datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                last_visit=datetime(2026, 3, 26, 15, 0, tzinfo=UTC),
            ),
        ],
        email_threads=[
            EmailThread(subject="Q2 Roadmap", message_count=3,
                        senders=["alice@co.com", "bob@co.com"], is_active=True),
        ],
        calendar_blocks=[
            CalendarBlock(title="Standup", start=datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
                          duration_minutes=15, back_to_back=False),
        ],
        media_sessions=[],
        time_blocks=[],
        raw_stats={"browser": 5, "gmail": 3, "calendar": 1},
    )


def test_source_summarizer_calls_llm_per_active_source():
    from pulse.analysis.source_summarizer import SourceSummarizer

    llm = FakeLLM()
    summarizer = SourceSummarizer(llm=llm, model="claude-haiku-4-5-20251001")

    day = _sample_preprocessed_day()
    result = asyncio.run(summarizer.summarize(day))

    # Should call LLM for browsing, email, and calendar (3 active sources)
    assert len(llm.calls) == 3
    # All calls should use haiku model
    assert all(c["model"] == "claude-haiku-4-5-20251001" for c in llm.calls)
    # Result should have narratives keyed by source
    assert "browsing" in result
    assert "email" in result
    assert "calendar" in result


def test_source_summarizer_skips_empty_sources():
    from pulse.analysis.source_summarizer import SourceSummarizer

    llm = FakeLLM()
    summarizer = SourceSummarizer(llm=llm, model="claude-haiku-4-5-20251001")

    day = PreprocessedDay(
        browsing_clusters=[],
        email_threads=[],
        calendar_blocks=[
            CalendarBlock(title="Meeting", start=datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
                          duration_minutes=30, back_to_back=False),
        ],
        media_sessions=[],
        time_blocks=[],
        raw_stats={"calendar": 1},
    )

    result = asyncio.run(summarizer.summarize(day))

    # Only calendar has data
    assert len(llm.calls) == 1
    assert "calendar" in result
    assert "browsing" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_source_summarizer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/analysis/source_summarizer.py
"""SourceSummarizer — Haiku pass for per-source narrative summaries."""
from __future__ import annotations

from pulse.analysis.preprocessor import PreprocessedDay


class SourceSummarizer:
    def __init__(self, llm, model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._model = model

    async def summarize(self, day: PreprocessedDay) -> dict[str, str]:
        """Summarize each active source into a short narrative. Returns {source: narrative}."""
        narratives: dict[str, str] = {}

        if day.browsing_clusters:
            narratives["browsing"] = await self._summarize_browsing(day)
        if day.email_threads:
            narratives["email"] = await self._summarize_email(day)
        if day.calendar_blocks:
            narratives["calendar"] = await self._summarize_calendar(day)
        if day.media_sessions:
            narratives["media"] = await self._summarize_media(day)

        return narratives

    async def _summarize_browsing(self, day: PreprocessedDay) -> str:
        lines = []
        for cluster in day.browsing_clusters[:15]:
            titles = ", ".join(cluster.titles[:5])
            lines.append(
                f"- {cluster.domain}: {cluster.visit_count} pages, "
                f"~{cluster.estimated_minutes:.0f} min ({titles})"
            )

        prompt = (
            "Summarize this person's browsing activity into 2-3 paragraphs. "
            "Focus on what topics they explored, how long they spent, and anything notable.\n\n"
            f"Browsing clusters:\n" + "\n".join(lines)
        )
        return await self._llm.complete(prompt, model=self._model)

    async def _summarize_email(self, day: PreprocessedDay) -> str:
        lines = []
        active = [t for t in day.email_threads if t.is_active]
        inactive = [t for t in day.email_threads if not t.is_active]

        if active:
            lines.append("Active conversations:")
            for t in active[:10]:
                senders = ", ".join(t.senders[:3])
                lines.append(f"- \"{t.subject}\" ({t.message_count} messages, with {senders})")

        if inactive:
            lines.append(f"\n{len(inactive)} other threads (newsletters, notifications, single messages)")
            for t in inactive[:5]:
                lines.append(f"- \"{t.subject}\" from {t.senders[0] if t.senders else 'unknown'}")

        prompt = (
            "Summarize this person's email activity into 2-3 paragraphs. "
            "Focus on what conversations were active and what seemed important.\n\n"
            + "\n".join(lines)
        )
        return await self._llm.complete(prompt, model=self._model)

    async def _summarize_calendar(self, day: PreprocessedDay) -> str:
        total_minutes = sum(b.duration_minutes for b in day.calendar_blocks)
        back_to_back = sum(1 for b in day.calendar_blocks if b.back_to_back)

        lines = [f"Total: {len(day.calendar_blocks)} events, ~{total_minutes:.0f} min"]
        if back_to_back:
            lines.append(f"Back-to-back meetings: {back_to_back}")

        for block in day.calendar_blocks:
            time_str = block.start.strftime("%H:%M")
            b2b = " [back-to-back]" if block.back_to_back else ""
            lines.append(f"- {time_str} {block.title}{b2b}")

        prompt = (
            "Summarize this person's calendar into 2-3 paragraphs. "
            "Note meeting density, gaps, and what kind of day it was.\n\n"
            + "\n".join(lines)
        )
        return await self._llm.complete(prompt, model=self._model)

    async def _summarize_media(self, day: PreprocessedDay) -> str:
        lines = []
        for session in day.media_sessions:
            items = ", ".join(session.items[:5])
            more = f" (+{len(session.items) - 5} more)" if len(session.items) > 5 else ""
            lines.append(
                f"- {session.source} session (~{session.duration_minutes:.0f} min): {items}{more}"
            )

        prompt = (
            "Summarize this person's media consumption into 1-2 paragraphs. "
            "Note what they listened to or watched and any themes.\n\n"
            + "\n".join(lines)
        )
        return await self._llm.complete(prompt, model=self._model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_source_summarizer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/source_summarizer.py tests/unit/test_source_summarizer.py
git commit -m "feat: add SourceSummarizer for Haiku-powered per-source narratives"
```

---

### Task 6: Build DigestBuilder (narrative daily digest)

**Files:**
- Create: `src/pulse/analysis/digest_builder.py`
- Create: `tests/unit/test_digest_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_digest_builder.py
import asyncio
from datetime import UTC, date, datetime

from pulse.analysis.preprocessor import (
    CalendarBlock,
    EmailThread,
    MediaSession,
    PreprocessedDay,
    TimeBlock,
    TopicCluster,
)


def test_digest_builder_produces_narrative_markdown():
    from pulse.analysis.digest_builder import DigestBuilder

    day = PreprocessedDay(
        browsing_clusters=[
            TopicCluster(
                domain="docs.rs",
                titles=["tokio - Rust"],
                visit_count=5,
                estimated_minutes=45.0,
                first_visit=datetime(2026, 3, 26, 14, 0, tzinfo=UTC),
                last_visit=datetime(2026, 3, 26, 15, 0, tzinfo=UTC),
            ),
        ],
        email_threads=[
            EmailThread(subject="Q2 Roadmap", message_count=3,
                        senders=["alice@co.com"], is_active=True),
            EmailThread(subject="Newsletter", message_count=1,
                        senders=["news@co.com"], is_active=False),
        ],
        calendar_blocks=[
            CalendarBlock(title="Standup", start=datetime(2026, 3, 26, 9, 0, tzinfo=UTC),
                          duration_minutes=15, back_to_back=False),
        ],
        media_sessions=[
            MediaSession(source="spotify", items=["Song A by Artist X", "Song B by Artist Y"],
                         duration_minutes=30.0,
                         first_item=datetime(2026, 3, 26, 20, 0, tzinfo=UTC),
                         last_item=datetime(2026, 3, 26, 20, 30, tzinfo=UTC)),
        ],
        time_blocks=[],
        raw_stats={"browser": 5, "gmail": 4, "calendar": 1, "spotify": 2},
    )

    narratives = {
        "browsing": "Spent an afternoon deep-diving into Rust async patterns.",
        "email": "Active thread on Q2 Roadmap with Alice.",
        "calendar": "Light meeting day with just a morning standup.",
        "media": "Relaxed evening with a Spotify session.",
    }

    builder = DigestBuilder()
    md = builder.build(date(2026, 3, 26), day, narratives)

    assert "# 2026-03-26" in md
    assert "## Day at a Glance" in md
    assert "## Timeline" in md
    assert "## Email" in md
    assert "Standup" in md
    assert "Q2 Roadmap" in md
    assert "docs.rs" in md


def test_digest_builder_fallback_without_narratives():
    from pulse.analysis.digest_builder import DigestBuilder

    day = PreprocessedDay(
        browsing_clusters=[],
        email_threads=[
            EmailThread(subject="Hello", message_count=1,
                        senders=["a@co.com"], is_active=False),
        ],
        calendar_blocks=[],
        media_sessions=[],
        time_blocks=[],
        raw_stats={"gmail": 1},
    )

    builder = DigestBuilder()
    md = builder.build(date(2026, 3, 26), day, narratives=None)

    # Should still produce valid markdown without Day at a Glance
    assert "# 2026-03-26" in md
    assert "Hello" in md
    assert "## Day at a Glance" not in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_digest_builder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/analysis/digest_builder.py
"""DigestBuilder — renders narrative daily digest markdown."""
from __future__ import annotations

from datetime import date

from pulse.analysis.preprocessor import PreprocessedDay

_BLOCK_LABELS = {
    0: "Late Night (12am-2am)",
    1: "Early Morning (2am-4am)",
    2: "Early Morning (4am-6am)",
    3: "Morning (6am-8am)",
    4: "Morning (8am-10am)",
    5: "Late Morning (10am-12pm)",
    6: "Afternoon (12pm-2pm)",
    7: "Afternoon (2pm-4pm)",
    8: "Late Afternoon (4pm-6pm)",
    9: "Evening (6pm-8pm)",
    10: "Evening (8pm-10pm)",
    11: "Night (10pm-12am)",
}


class DigestBuilder:
    def build(
        self,
        day: date,
        preprocessed: PreprocessedDay,
        narratives: dict[str, str] | None = None,
    ) -> str:
        sections: list[str] = [f"# {day.isoformat()}", ""]

        # Day at a Glance (only with LLM narratives)
        if narratives:
            glance = self._build_glance(narratives)
            sections.extend(["## Day at a Glance", glance, ""])

        # Timeline (chronological, grouped by time block)
        timeline = self._build_timeline(preprocessed)
        if timeline:
            sections.extend(["## Timeline", timeline, ""])

        # Email
        if preprocessed.email_threads:
            sections.extend(["## Email", self._build_email(preprocessed), ""])

        # Media
        if preprocessed.media_sessions:
            sections.extend(["## Media", self._build_media(preprocessed), ""])

        # Browsing
        if preprocessed.browsing_clusters:
            sections.extend(["## Browsing", self._build_browsing(preprocessed), ""])

        return "\n".join(sections)

    def _build_glance(self, narratives: dict[str, str]) -> str:
        # Combine first sentence of each narrative
        parts = []
        for source in ("calendar", "email", "browsing", "media"):
            text = narratives.get(source, "")
            if text:
                # Take first sentence
                first = text.split(". ")[0].rstrip(".")
                parts.append(first + ".")
        return " ".join(parts) if parts else "Quiet day."

    def _build_timeline(self, day: PreprocessedDay) -> str:
        # Collect all timestamped items
        items: list[tuple[int, str]] = []

        for block in day.calendar_blocks:
            time_str = block.start.strftime("%H:%M")
            b2b = " (back-to-back)" if block.back_to_back else ""
            items.append((block.start.hour, f"- {time_str} {block.title}{b2b}"))

        # Add browsing cluster summaries at their start time
        for cluster in day.browsing_clusters[:10]:
            time_str = cluster.first_visit.strftime("%H:%M")
            items.append((
                cluster.first_visit.hour,
                f"- {time_str} Browsing: {cluster.domain} "
                f"({cluster.visit_count} pages, ~{cluster.estimated_minutes:.0f} min)",
            ))

        # Add media sessions
        for session in day.media_sessions:
            time_str = session.first_item.strftime("%H:%M")
            item_preview = session.items[0] if session.items else session.source
            count = f" (+{len(session.items) - 1} more)" if len(session.items) > 1 else ""
            items.append((
                session.first_item.hour,
                f"- {time_str} {session.source.title()}: {item_preview}{count}",
            ))

        if not items:
            return ""

        items.sort(key=lambda x: x[0])

        # Group by 2-hour blocks
        lines = []
        current_block = -1
        for hour, text in items:
            block = hour // 2
            if block != current_block:
                current_block = block
                label = _BLOCK_LABELS.get(block, f"Block {block}")
                lines.append(f"### {label}")
            lines.append(text)

        return "\n".join(lines)

    def _build_email(self, day: PreprocessedDay) -> str:
        lines = []
        active = [t for t in day.email_threads if t.is_active]
        inactive = [t for t in day.email_threads if not t.is_active]

        for thread in active:
            senders = ", ".join(thread.senders[:3])
            lines.append(
                f"- **{thread.subject}** ({thread.message_count} messages with {senders})"
            )

        if inactive:
            lines.append(f"- {len(inactive)} other messages (newsletters, notifications)")

        return "\n".join(lines) if lines else "No email activity."

    def _build_media(self, day: PreprocessedDay) -> str:
        lines = []
        for session in day.media_sessions:
            items = ", ".join(session.items[:5])
            more = f" (+{len(session.items) - 5} more)" if len(session.items) > 5 else ""
            lines.append(
                f"- {session.source.title()}: {items}{more} (~{session.duration_minutes:.0f} min)"
            )
        return "\n".join(lines) if lines else "No media activity."

    def _build_browsing(self, day: PreprocessedDay) -> str:
        lines = []
        for cluster in day.browsing_clusters[:10]:
            titles = ", ".join(cluster.titles[:3])
            more = f" (+{len(cluster.titles) - 3} more)" if len(cluster.titles) > 3 else ""
            lines.append(
                f"- {cluster.domain}: {titles}{more} (~{cluster.estimated_minutes:.0f} min)"
            )
        return "\n".join(lines) if lines else "No browsing activity."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_digest_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/digest_builder.py tests/unit/test_digest_builder.py
git commit -m "feat: add DigestBuilder for narrative daily digests"
```

---

### Task 7: Sharpen the discovery prompt

**Files:**
- Modify: `src/pulse/analysis/prompts.py`
- Modify: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_prompts.py

def test_discovery_prompt_includes_rejection_criteria():
    result = build_discovery_prompt(
        cadence="weekly",
        date_range="2026-03-20 to 2026-03-26",
        event_summary="some events",
        active_patterns="",
        baselines="",
        user_profile="",
    )

    system = result["system_prompt"]
    assert "do not report" in system.lower() or "do not" in system.lower()
    assert "cross-source" in system.lower()
    assert "baseline" in system.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_prompts.py::test_discovery_prompt_includes_rejection_criteria -v`
Expected: FAIL — current prompt doesn't contain rejection criteria

- [ ] **Step 3: Update SYSTEM_PROMPT in prompts.py**

Replace the `SYSTEM_PROMPT` in `src/pulse/analysis/prompts.py`:

```python
SYSTEM_PROMPT = """You are Pulse's insight engine, analyzing personal data for cross-source patterns.

## Role
Analyze the user's personal data streams (calendar, email, browsing, music, etc.) to surface meaningful cross-source insights about behavior, habits, and trends.

## Rules
- Only report interesting or actionable findings — skip noise
- Update existing patterns with new evidence rather than duplicating them
- Mark patterns as invalidated if the data no longer supports them
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
```

- [ ] **Step 4: Run all prompt tests to verify they pass**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/prompts.py tests/unit/test_prompts.py
git commit -m "feat: sharpen discovery prompt with rejection criteria and pattern qualifiers"
```

---

### Task 8: Wire preprocessor and source summarizer into DiscoveryEngine

**Files:**
- Modify: `src/pulse/analysis/discovery.py`
- Modify: `tests/unit/test_discovery.py`

- [ ] **Step 1: Update the discovery test to verify preprocessor + summarizer are used**

```python
# Replace FakeLLM in tests/unit/test_discovery.py with one that tracks model param

class FakeLLM:
    def __init__(self, response: str):
        self.calls: list[dict] = []
        self._response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, "model": model})
        return self._response
```

Also add a test:

```python
# Append to tests/unit/test_discovery.py

def test_discovery_engine_uses_source_summarizer(tmp_path):
    """Discovery should make Haiku summarization calls before the Sonnet discovery call."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            events = [
                _make_event("e1", datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                            "gmail", "email.received",
                            {"subject": "Project update", "from": "alice@example.com"}),
                _make_event("e2", datetime(2026, 3, 20, 14, 0, tzinfo=UTC),
                            "browser", "browsing.visit",
                            {"url": "https://docs.rs/tokio", "title": "tokio - Rust"}),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
            summarization_model="claude-haiku-4-5-20251001",
            discovery_model="claude-sonnet-4-5-20250514",
        )
        return await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    # Should have summarization calls (haiku) + 1 discovery call (sonnet)
    haiku_calls = [c for c in fake_llm.calls if c["model"] == "claude-haiku-4-5-20251001"]
    sonnet_calls = [c for c in fake_llm.calls if c["model"] == "claude-sonnet-4-5-20250514"]

    assert len(haiku_calls) >= 1, "Should have at least one Haiku summarization call"
    assert len(sonnet_calls) == 1, "Should have exactly one Sonnet discovery call"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_discovery.py::test_discovery_engine_uses_source_summarizer -v`
Expected: FAIL — `DiscoveryEngine` doesn't accept `summarization_model`/`discovery_model`

- [ ] **Step 3: Update DiscoveryEngine**

Replace `src/pulse/analysis/discovery.py` with:

```python
"""DiscoveryEngine — orchestrates LLM-assisted pattern discovery."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from pulse.analysis.event_summarizer import EventSummarizer
from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.prompts import build_discovery_prompt, parse_discovery_response
from pulse.analysis.source_summarizer import SourceSummarizer
from pulse.analysis.vault_memory import VaultMemory
from pulse.domain.notifications import Notification
from pulse.store.analytics import AnalyticsRepository
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema


@dataclass(slots=True)
class DiscoveryResult:
    new_patterns: int
    updated_patterns: int
    notifications_sent: int


DATA_WINDOWS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:80]


class DiscoveryEngine:
    def __init__(
        self,
        database_path,
        vault_root,
        llm,
        notification_channel=None,
        summarization_model: str = "claude-haiku-4-5-20251001",
        discovery_model: str = "claude-sonnet-4-5-20250514",
    ):
        self._db_path = database_path
        self._vault = VaultMemory(vault_root)
        self._llm = llm
        self._channel = notification_channel
        self._summarization_model = summarization_model
        self._discovery_model = discovery_model

    async def run_discovery(self, cadence: str, target_date: date) -> DiscoveryResult:
        window_days = DATA_WINDOWS.get(cadence, 7)
        start_date = target_date - timedelta(days=window_days - 1)

        async with connect_db(self._db_path) as db:
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            current = start_date
            while current <= target_date:
                await analytics.aggregate_day(current.isoformat())
                current += timedelta(days=1)

            end_date = target_date + timedelta(days=1)
            stats = await analytics.get_daily_stats_range(
                start_date.isoformat(), end_date.isoformat()
            )

            all_events = []
            current = start_date
            while current <= target_date:
                day_events = await event_repo.list_events_for_day(current.isoformat())
                all_events.extend(day_events)
                current += timedelta(days=1)

            baselines: list[dict] = []
            for weeks_back in range(1, 5):
                week_start = target_date - timedelta(weeks=weeks_back)
                week_baselines = await analytics.get_weekly_baselines(week_start.isoformat())
                baselines.extend(week_baselines)

        # Stage 1: Preprocess events
        preprocessor = EventPreprocessor()
        preprocessed = preprocessor.preprocess(all_events)

        # Stage 2: Source summarization (Haiku)
        summarizer = SourceSummarizer(llm=self._llm, model=self._summarization_model)
        narratives = await summarizer.summarize(preprocessed)

        # Build combined narrative for discovery prompt
        narrative_text = "\n\n".join(
            f"### {source.title()}\n{text}" for source, text in narratives.items()
        )

        # Also build the old-style event summary as fallback context
        date_range = (
            f"{start_date.isoformat()} to {target_date.isoformat()}"
            if start_date != target_date
            else target_date.isoformat()
        )
        event_summary = EventSummarizer().summarize(
            date_range=date_range,
            stats=stats,
            events=all_events,
            baselines=baselines if baselines else None,
        )

        # Combine narratives with stats
        combined_summary = narrative_text
        if event_summary:
            combined_summary += f"\n\n### Raw Statistics\n{event_summary}"

        # Read vault memory
        active_patterns = self._vault.read_patterns()
        patterns_text = "\n\n".join(
            f"### {p['slug']}\n{p['content']}" for p in active_patterns
        )
        routines_text = self._vault.read_life_file("routines.md")
        profile_text = self._vault.read_config_file("profile.md")

        # Stage 3: Discovery (Sonnet)
        prompt_dict = build_discovery_prompt(
            cadence=cadence,
            date_range=date_range,
            event_summary=combined_summary or "(no events in window)",
            active_patterns=patterns_text,
            baselines=routines_text,
            user_profile=profile_text,
        )

        raw_response = await self._llm.complete(
            prompt_dict["user_prompt"],
            system_prompt=prompt_dict["system_prompt"],
            model=self._discovery_model,
        )

        discovery = parse_discovery_response(raw_response)

        # Write back results (unchanged from before)
        target_str = target_date.isoformat()
        new_count = 0
        updated_count = 0

        async with connect_db(self._db_path) as db:
            analytics = AnalyticsRepository(db)

            for pattern in discovery.new_patterns:
                slug = _slugify(pattern.title)
                vault_path = f"02-Insights/patterns/{slug}.md"

                self._vault.write_pattern(
                    slug=slug,
                    title=pattern.title,
                    status="active",
                    confidence=pattern.confidence,
                    first_seen=target_str,
                    last_updated=target_str,
                    observation=pattern.observation,
                    evidence_log=pattern.evidence,
                    trend=pattern.trend,
                )

                await analytics.upsert_insight(
                    id=slug,
                    title=pattern.title,
                    status="active",
                    confidence=str(pattern.confidence),
                    first_seen=target_str,
                    last_seen=target_str,
                    vault_path=vault_path,
                )
                new_count += 1

            for update in discovery.updated_patterns:
                slug = update.slug
                title = update.slug.replace("-", " ").title()
                vault_path = f"02-Insights/patterns/{slug}.md"

                self._vault.update_pattern(
                    slug=slug,
                    title=title,
                    status=update.status,
                    confidence=update.confidence,
                    first_seen=target_str,
                    last_updated=target_str,
                    observation=update.update_note,
                    evidence_log=update.new_evidence,
                    trend=update.trend,
                )

                await analytics.upsert_insight(
                    id=slug,
                    title=title,
                    status=update.status,
                    confidence=str(update.confidence),
                    first_seen=target_str,
                    last_seen=target_str,
                    vault_path=vault_path,
                )
                updated_count += 1

        if discovery.baseline_updates:
            self._vault.write_life_file("routines.md", discovery.baseline_updates)

        notifications_sent = 0
        for notif_item in discovery.notifications:
            if self._channel is not None:
                self._channel.send(
                    Notification(
                        title=notif_item.title,
                        body=notif_item.body,
                        category="insight",
                        priority=notif_item.priority,
                    )
                )
                notifications_sent += 1

        return DiscoveryResult(
            new_patterns=new_count,
            updated_patterns=updated_count,
            notifications_sent=notifications_sent,
        )
```

- [ ] **Step 4: Run all discovery tests**

Run: `pytest tests/unit/test_discovery.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/analysis/discovery.py tests/unit/test_discovery.py
git commit -m "feat: wire preprocessor and source summarizer into discovery pipeline"
```

---

### Task 9: Wire DigestBuilder into daily digest job

**Files:**
- Modify: `src/pulse/analysis/summarizer.py`
- Modify: `src/pulse/jobs/runners.py`

- [ ] **Step 1: Update DailySummarizer to use preprocessor and digest builder when LLM available**

```python
# src/pulse/analysis/summarizer.py
from dataclasses import dataclass
from datetime import date

from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.digest_builder import DigestBuilder
from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def __init__(self, llm=None, summarization_model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._summarization_model = summarization_model

    async def summarize_async(self, day: date, events: list[Event]) -> DailySummary:
        """Async summarization with LLM narratives when available."""
        preprocessor = EventPreprocessor()
        preprocessed = preprocessor.preprocess(events)

        narratives = None
        if self._llm is not None:
            from pulse.analysis.source_summarizer import SourceSummarizer
            summarizer = SourceSummarizer(llm=self._llm, model=self._summarization_model)
            narratives = await summarizer.summarize(preprocessed)

        builder = DigestBuilder()
        markdown = builder.build(day, preprocessed, narratives)
        return DailySummary(day=day, markdown=markdown)

    def summarize(self, day: date, events: list[Event]) -> DailySummary:
        """Sync fallback — uses preprocessor but no LLM narratives."""
        preprocessor = EventPreprocessor()
        preprocessed = preprocessor.preprocess(events)
        builder = DigestBuilder()
        markdown = builder.build(day, preprocessed, narratives=None)
        return DailySummary(day=day, markdown=markdown)


def _event_text(event: Event, preferred_key: str | None = None) -> str:
    if preferred_key is not None:
        value = event.data.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return event.event_type
```

- [ ] **Step 2: Update runners.py to pass LLM to digest job**

```python
# In src/pulse/jobs/runners.py, replace _build_daily_summary and run_daily_digest_job:

async def run_daily_digest_job(
    day: date, database_path: str | Path, vault_path: str | Path,
    llm=None, summarization_model: str = "claude-haiku-4-5-20251001",
) -> JobResult:
    summary = await _build_daily_summary(
        day=day, database_path=database_path,
        llm=llm, summarization_model=summarization_model,
    )
    output_path = write_daily_digest(
        vault_root=Path(vault_path),
        date_slug=day.isoformat(),
        content=summary.markdown,
    )
    return JobResult(status="success", detail=str(output_path))


async def _build_daily_summary(
    day: date,
    database_path: str | Path,
    llm=None,
    summarization_model: str = "claude-haiku-4-5-20251001",
):
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        events = await repository.list_events_for_day(day.isoformat())

    summarizer = DailySummarizer(llm=llm, summarization_model=summarization_model)
    if llm is not None:
        return await summarizer.summarize_async(day, events)
    return summarizer.summarize(day, events)
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All PASS. Existing tests use `DailySummarizer().summarize()` (sync, no LLM) which still works.

- [ ] **Step 4: Commit**

```bash
git add src/pulse/analysis/summarizer.py src/pulse/jobs/runners.py
git commit -m "feat: wire DigestBuilder into daily digest job with optional LLM narratives"
```

---

### Task 10: Wire LLM into scheduled digest and discovery jobs

**Files:**
- Modify: `src/pulse/jobs/scheduler.py`

- [ ] **Step 1: Update _make_daily_digest_job to pass LLM when available**

In `src/pulse/jobs/scheduler.py`, update `_make_daily_digest_job`:

```python
def _make_daily_digest_job(config):
    async def job():
        day = _resolve_current_day(config)

        llm = None
        if config.anthropic_api_key:
            from pulse.llm.anthropic import AnthropicProvider
            llm = AnthropicProvider(api_key=config.anthropic_api_key)

        return await run_daily_digest_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=llm,
            summarization_model=config.summarization_model,
        )
    return job
```

And update `_make_discovery_job` to pass model params:

```python
def _make_discovery_job(cadence, config):
    async def job():
        from pulse.jobs.runners import run_discovery_job
        from pulse.llm.anthropic import AnthropicProvider

        day = _resolve_current_day(config)
        llm = None
        if config.anthropic_api_key:
            llm = AnthropicProvider(api_key=config.anthropic_api_key)

        if llm is None:
            return JobResult(
                status="skipped",
                detail=f"Discovery ({cadence}) skipped: no LLM provider configured",
            )

        channel = _build_telegram_channel(config)
        return await run_discovery_job(
            cadence=cadence,
            target_date=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=llm,
            notification_channel=channel,
            summarization_model=config.summarization_model,
            discovery_model=config.discovery_model,
        )
    return job
```

And update `run_discovery_job` in `runners.py` to accept and pass model params:

```python
async def run_discovery_job(
    cadence: str,
    target_date: date,
    database_path: str | Path,
    vault_path: str | Path,
    llm,
    notification_channel=None,
    summarization_model: str = "claude-haiku-4-5-20251001",
    discovery_model: str = "claude-sonnet-4-5-20250514",
) -> JobResult:
    from pulse.analysis.discovery import DiscoveryEngine

    engine = DiscoveryEngine(
        database_path=database_path,
        vault_root=Path(vault_path),
        llm=llm,
        notification_channel=notification_channel,
        summarization_model=summarization_model,
        discovery_model=discovery_model,
    )
    result = await engine.run_discovery(cadence=cadence, target_date=target_date)
    return JobResult(
        status="success",
        detail=(
            f"Discovery ({cadence}): {result.new_patterns} new patterns, "
            f"{result.updated_patterns} updated, {result.notifications_sent} notifications"
        ),
    )
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/pulse/jobs/scheduler.py src/pulse/jobs/runners.py
git commit -m "feat: wire LLM into scheduled digest and discovery jobs with model config"
```

---

### Task 11: Run full test suite and verify end-to-end

**Files:**
- No new files

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from pulse.analysis.preprocessor import EventPreprocessor; from pulse.analysis.source_summarizer import SourceSummarizer; from pulse.analysis.digest_builder import DigestBuilder; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git add -A
git commit -m "feat: complete smarter outputs pipeline — preprocessor, source summarizer, narrative digests"
```

---

## Summary

| Task | Component | What it builds |
|------|-----------|---------------|
| 1 | AnthropicProvider | Model override on `complete()` |
| 2 | PulseConfig | `summarization_model` and `discovery_model` fields |
| 3 | EventPreprocessor | Browsing clustering, dedup, time estimation |
| 4 | EventPreprocessor | Email threading, calendar blocks, time blocks |
| 5 | SourceSummarizer | Haiku pass — per-source narratives |
| 6 | DigestBuilder | Narrative daily digest markdown |
| 7 | Prompts | Sharpened discovery prompt with rejection criteria |
| 8 | DiscoveryEngine | Wired into preprocessor + summarizer pipeline |
| 9 | DailySummarizer + runners | Digest job uses preprocessor + optional LLM |
| 10 | Scheduler + runners | Scheduled jobs pass LLM and model config |
| 11 | Integration | Full test suite verification |

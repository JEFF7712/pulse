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
from pulse.domain.pattern_statuses import normalize_pattern_status
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
    """Lowercase, remove non-alphanumeric (keep spaces), replace spaces with hyphens, truncate to 80 chars."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:80]


def _notification_pattern_context_id(pattern_ref: str | None) -> str | None:
    if pattern_ref is None:
        return None

    slug = _canonicalize_pattern_ref(pattern_ref)
    if not slug:
        return None

    return f"pattern:{slug}"


def _canonicalize_pattern_ref(pattern_ref: str) -> str:
    normalized_ref = re.sub(r"[^a-z0-9]+", " ", pattern_ref.lower()).strip()
    return re.sub(r"\s+", "-", normalized_ref)[:80]


def _valid_new_pattern_title(title: str) -> bool:
    return bool(_slugify(title))


def _valid_updated_pattern_slug(slug: str) -> bool:
    return bool(_canonicalize_pattern_ref(slug))


class DiscoveryEngine:
    def __init__(
        self,
        database_path,
        vault_root,
        llm,
        notification_channel=None,
        summarization_model: str = "",
        discovery_model: str = "",
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
                await analytics.aggregate_weekly_baselines(week_start.isoformat())
                week_baselines = await analytics.get_weekly_baselines(
                    week_start.isoformat()
                )
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
        known_pattern_context_ids = {
            f"pattern:{slug}"
            for pattern in active_patterns
            if (slug := _canonicalize_pattern_ref(pattern["slug"]))
        }
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
        if (
            not discovery.new_patterns
            and not discovery.updated_patterns
            and not discovery.notifications
            and discovery.baseline_updates is None
            and len(raw_response.strip()) > 80
        ):
            raw_response = await self._llm.complete(
                "Your previous reply was not usable. Output ONLY one JSON object matching "
                "the schema from the system prompt. No markdown fences, no commentary.\n\n"
                f"Broken output was:\n{raw_response[:8000]}",
                system_prompt=prompt_dict["system_prompt"],
                model=self._discovery_model,
            )
            discovery = parse_discovery_response(raw_response)

        # Write back results
        target_str = target_date.isoformat()
        new_count = 0
        updated_count = 0

        async with connect_db(self._db_path) as db:
            analytics = AnalyticsRepository(db)
            existing_insights = await analytics.list_insights()
            known_pattern_context_ids.update(
                f"pattern:{slug}"
                for insight in existing_insights
                if (slug := _canonicalize_pattern_ref(insight["id"]))
            )

            for pattern in discovery.new_patterns:
                if not _valid_new_pattern_title(pattern.title):
                    continue

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
                known_pattern_context_ids.add(f"pattern:{slug}")
                new_count += 1

            for update in discovery.updated_patterns:
                if not _valid_updated_pattern_slug(update.slug):
                    continue

                slug = _canonicalize_pattern_ref(update.slug)
                existing_insight = await analytics.get_insight(slug)
                if existing_insight is None and not self._vault.pattern_exists(slug):
                    continue

                try:
                    status = normalize_pattern_status(update.status)
                except ValueError:
                    continue

                vault_path = f"02-Insights/patterns/{slug}.md"
                title = (
                    existing_insight["title"]
                    if existing_insight is not None
                    else update.slug.replace("-", " ").title()
                )
                first_seen = (
                    existing_insight["first_seen"]
                    if existing_insight is not None
                    else target_str
                )

                self._vault.update_pattern(
                    slug=slug,
                    title=title,
                    status=status,
                    confidence=update.confidence,
                    first_seen=first_seen,
                    last_updated=target_str,
                    observation=update.update_note,
                    evidence_log=update.new_evidence,
                    trend=update.trend,
                )

                await analytics.upsert_insight(
                    id=slug,
                    title=title,
                    status=status,
                    confidence=str(update.confidence),
                    first_seen=first_seen,
                    last_seen=target_str,
                    vault_path=vault_path,
                )
                known_pattern_context_ids.add(f"pattern:{slug}")
                updated_count += 1

        if discovery.baseline_updates:
            self._vault.write_life_file("routines.md", discovery.baseline_updates)

        notifications_sent = 0
        for notif_item in discovery.notifications:
            if self._channel is not None:
                context_id = None
                if notif_item.pattern_slug:
                    candidate_context_id = _notification_pattern_context_id(
                        notif_item.pattern_slug
                    )
                    if candidate_context_id in known_pattern_context_ids:
                        context_id = candidate_context_id

                self._channel.send(
                    Notification(
                        title=notif_item.title,
                        body=notif_item.body,
                        category="insight",
                        context_id=context_id,
                        priority=notif_item.priority,
                    )
                )
                notifications_sent += 1

        return DiscoveryResult(
            new_patterns=new_count,
            updated_patterns=updated_count,
            notifications_sent=notifications_sent,
        )

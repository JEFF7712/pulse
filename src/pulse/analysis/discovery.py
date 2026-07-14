"""DiscoveryEngine — orchestrates LLM-assisted pattern discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from pulse.analysis.event_summarizer import EventSummarizer
from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.prompts import NewPattern, build_discovery_prompt, parse_discovery_response
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

_PATTERN_ARCHIVE_DIR = "_archive"


def _vault_path_for_pattern(slug: str, status: str) -> str:
    if normalize_pattern_status(status) == "inactive":
        return f"02-Insights/patterns/{_PATTERN_ARCHIVE_DIR}/{slug}.md"
    return f"02-Insights/patterns/{slug}.md"


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


_ISO_DAY_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _evidence_days(evidence: list[str]) -> set[str]:
    days: set[str] = set()
    for item in evidence:
        match = _ISO_DAY_RE.search(item)
        if match:
            days.add(match.group(1))
    return days


def _is_significant_new_pattern(pattern) -> bool:
    confidence = pattern.confidence
    if not isinstance(confidence, (int, float)):
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

    evidence_count = len(pattern.evidence)
    distinct_days = len(_evidence_days(pattern.evidence))

    if confidence < 0.65:
        return False
    if evidence_count < 2:
        return False
    if distinct_days >= 2:
        return True
    return evidence_count >= 4 and confidence >= 0.8


def _should_prune_low_signal_pattern(insight: dict, vault: VaultMemory) -> bool:
    if insight["first_seen"] != insight["last_seen"]:
        return False

    snapshot = vault.read_pattern_snapshot(insight["id"])
    if snapshot is None:
        return False
    if snapshot["has_user_notes"]:
        return False

    candidate = NewPattern(
        title=insight["title"],
        observation="",
        confidence=insight["confidence"],
        evidence=snapshot["evidence"],
        trend="",
    )
    return not _is_significant_new_pattern(candidate)


class DiscoveryEngine:
    def __init__(
        self,
        database_path,
        vault_root,
        llm,
        timezone: str = "UTC",
        notification_channel=None,
        summarization_model: str = "",
        discovery_model: str = "",
    ):
        self._db_path = database_path
        self._vault = VaultMemory(vault_root)
        self._llm = llm
        self._timezone = timezone
        self._channel = notification_channel
        self._summarization_model = summarization_model
        self._discovery_model = discovery_model

    async def _sync_inactive_pattern_archives(
        self, analytics: AnalyticsRepository
    ) -> None:
        """Purge stale archive files, move legacy inactive files out of the main folder, fix DB paths."""
        purged_slugs = self._vault.purge_archived_patterns()
        if purged_slugs:
            await analytics.delete_insights(purged_slugs)

        for insight in await analytics.list_insights(status="inactive"):
            slug = insight["id"]
            expected_path = _vault_path_for_pattern(slug, "inactive")
            if self._vault.inactive_pattern_in_active_folder(slug):
                self._vault.move_pattern_from_active_to_archive(slug)
                await analytics.upsert_insight(
                    id=slug,
                    title=insight["title"],
                    status="inactive",
                    confidence=insight["confidence"],
                    first_seen=insight["first_seen"],
                    last_seen=insight["last_seen"],
                    vault_path=expected_path,
                )
            elif self._vault.archived_pattern_exists(slug) and insight.get(
                "vault_path"
            ) != expected_path:
                await analytics.upsert_insight(
                    id=slug,
                    title=insight["title"],
                    status="inactive",
                    confidence=insight["confidence"],
                    first_seen=insight["first_seen"],
                    last_seen=insight["last_seen"],
                    vault_path=expected_path,
                )

    async def run_discovery(self, cadence: str, target_date: date) -> DiscoveryResult:
        window_days = DATA_WINDOWS.get(cadence, 7)
        start_date = target_date - timedelta(days=window_days - 1)

        async with connect_db(self._db_path) as db:
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            current = start_date
            while current <= target_date:
                await analytics.aggregate_day(
                    current.isoformat(), timezone=self._timezone
                )
                current += timedelta(days=1)

            end_date = target_date + timedelta(days=1)
            stats = await analytics.get_daily_stats_range(
                start_date.isoformat(), end_date.isoformat()
            )

            all_events = []
            current = start_date
            while current <= target_date:
                day_events = await event_repo.list_events_for_day(
                    current.isoformat(), timezone=self._timezone
                )
                all_events.extend(day_events)
                current += timedelta(days=1)

            baselines: list[dict] = []
            for weeks_back in range(1, 5):
                week_start = target_date - timedelta(weeks=weeks_back)
                await analytics.aggregate_weekly_baselines(
                    week_start.isoformat(), timezone=self._timezone
                )
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

        async with connect_db(self._db_path) as db:
            await self._sync_inactive_pattern_archives(AnalyticsRepository(db))

        # Read vault memory
        active_patterns = self._vault.read_patterns()
        active_pattern_slugs = {pattern["slug"] for pattern in active_patterns}
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
        run_classification: dict[str, str] = {}

        async with connect_db(self._db_path) as db:
            analytics = AnalyticsRepository(db)
            existing_insights = await analytics.list_insights()
            stale_insight_ids = [
                insight["id"]
                for insight in existing_insights
                if insight["id"] not in active_pattern_slugs
                and not self._vault.pattern_exists(insight["id"])
            ]
            if stale_insight_ids:
                await analytics.delete_insights(stale_insight_ids)
                stale_insight_id_set = set(stale_insight_ids)
                existing_insights = [
                    insight
                    for insight in existing_insights
                    if insight["id"] not in stale_insight_id_set
                ]
            known_pattern_ids = active_pattern_slugs | {
                insight["id"] for insight in existing_insights
            }
            known_pattern_context_ids.update(
                f"pattern:{slug}"
                for insight in existing_insights
                if (slug := _canonicalize_pattern_ref(insight["id"]))
            )

            for pattern in discovery.new_patterns:
                if not _valid_new_pattern_title(pattern.title):
                    continue
                if not _is_significant_new_pattern(pattern):
                    continue

                slug = _slugify(pattern.title)
                vault_path = _vault_path_for_pattern(slug, "active")
                existed_before_write = slug in known_pattern_ids

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
                known_pattern_ids.add(slug)
                if existed_before_write:
                    updated_count += 1
                    run_classification[slug] = "updated"
                else:
                    new_count += 1
                    run_classification[slug] = "new"

            for update in discovery.updated_patterns:
                if not _valid_updated_pattern_slug(update.slug):
                    continue

                slug = _canonicalize_pattern_ref(update.slug)
                existing_insight = await analytics.get_insight(slug)
                if existing_insight is None and not self._vault.pattern_exists(slug):
                    continue
                existed_before_write = slug in known_pattern_ids

                try:
                    status = normalize_pattern_status(update.status)
                except ValueError:
                    continue

                vault_path = _vault_path_for_pattern(slug, status)
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
                known_pattern_ids.add(slug)
                if existed_before_write:
                    updated_count += 1
                    run_classification[slug] = "updated"
                else:
                    new_count += 1
                    run_classification[slug] = "new"

            current_insights = await analytics.list_insights()
            pruned_ids: list[str] = []
            for insight in current_insights:
                slug = insight["id"]
                if not _should_prune_low_signal_pattern(insight, self._vault):
                    continue
                self._vault.delete_pattern(slug)
                pruned_ids.append(slug)

                classification = run_classification.get(slug)
                if classification == "new":
                    new_count -= 1
                elif classification == "updated":
                    updated_count -= 1
                known_pattern_context_ids.discard(f"pattern:{slug}")

            if pruned_ids:
                await analytics.delete_insights(pruned_ids)

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

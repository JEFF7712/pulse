"""Tests for DiscoveryEngine — LLM-assisted pattern discovery orchestrator."""

import asyncio
import json
from datetime import UTC, date, datetime

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(id, timestamp, source, event_type, data=None):
    from pulse.domain.events import Event

    return Event(
        id=id,
        timestamp=timestamp,
        source=source,
        event_type=event_type,
        data=data or {},
    )


# Canned LLM response: 1 new pattern, 0 updated patterns, 1 notification
_LLM_RESPONSE = json.dumps(
    {
        "new_patterns": [
            {
                "title": "Late Night Focus Sessions",
                "observation": "User consistently works after 22:00 on weeknights.",
                "confidence": 0.85,
                "evidence": [
                    "2026-03-19: coding session 22:00-01:00",
                    "2026-03-20: writing 23:00-00:30",
                ],
                "trend": "new",
            }
        ],
        "updated_patterns": [],
        "notifications": [
            {
                "title": "New Pattern Detected",
                "body": "You have a late-night focus pattern emerging.",
                "priority": "medium",
                "pattern_slug": "late-night-focus-sessions",
            }
        ],
        "baseline_updates": "Late-night coding sessions avg 2h per weeknight.",
    }
)


class FakeLLM:
    def __init__(self, response: str):
        self.calls: list[dict] = []
        self._response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "model": model}
        )
        return self._response


class FakeChannel:
    def __init__(self):
        self.sent: list = []

    def send(self, notification):
        self.sent.append(notification)
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discovery_engine_full_cycle(tmp_path):
    """Seeds events, runs discovery with FakeLLM, verifies all side-effects."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)

            # Seed some events on the target day
            events = [
                _make_event(
                    "e1",
                    datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                    {"subject": "Project update", "from": "alice@example.com"},
                ),
                _make_event(
                    "e2",
                    datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                    "github",
                    "commit.pushed",
                    {"message": "fix: improve caching"},
                ),
                _make_event(
                    "e3",
                    datetime(2026, 3, 20, 23, 0, tzinfo=UTC),
                    "github",
                    "commit.pushed",
                    {"message": "feat: add new endpoint"},
                ),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        result = await engine.run_discovery("daily", target_date)

        # Return everything we need to verify
        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        patterns = vault.read_patterns()

        return result, insights, patterns

    result, insights, patterns = asyncio.run(exercise())

    # LLM was called
    assert len(fake_llm.calls) >= 1, "LLM should have been called at least once"

    # New pattern counts
    assert result.new_patterns == 1
    assert result.updated_patterns == 0

    # Notification was sent
    assert result.notifications_sent == 1
    assert len(fake_channel.sent) == 1
    notif = fake_channel.sent[0]
    assert notif.title == "New Pattern Detected"
    assert notif.body == "You have a late-night focus pattern emerging."
    assert notif.context_id == "pattern:late-night-focus-sessions"

    # Pattern was written to vault
    assert len(patterns) == 1
    assert patterns[0]["slug"] == "late-night-focus-sessions"
    assert "Late Night Focus Sessions" in patterns[0]["content"]

    # Insight stored in DB
    assert len(insights) == 1
    assert insights[0]["title"] == "Late Night Focus Sessions"
    assert insights[0]["status"] == "active"
    assert (
        insights[0]["vault_path"] == "02-Insights/patterns/late-night-focus-sessions.md"
    )


def test_discovery_engine_works_without_notification_channel(tmp_path):
    """Discovery run with no notification channel yields notifications_sent == 0."""
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
                _make_event(
                    "e1",
                    datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
                    "calendar",
                    "calendar.event",
                    {"title": "Weekly Sync"},
                ),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        return await engine.run_discovery("daily", target_date)

    result = asyncio.run(exercise())

    assert result.notifications_sent == 0
    assert result.new_patterns == 1


def test_discovery_notifications_include_pattern_context_id(tmp_path):
    """Pattern discovery notifications should carry a stable pattern:<slug> context."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    fake_llm = FakeLLM(_LLM_RESPONSE)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    assert len(fake_channel.sent) == 1
    assert fake_channel.sent[0].context_id == "pattern:late-night-focus-sessions"


def test_discovery_notifications_map_context_ids_by_pattern_slug(tmp_path):
    """Only notifications explicitly tied to a pattern slug should get a pattern context id."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [
                {
                    "title": "Late Night Focus Sessions",
                    "observation": "User consistently works after 22:00 on weeknights.",
                    "confidence": 0.85,
                    "evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "new",
                }
            ],
            "updated_patterns": [],
            "notifications": [
                {
                    "title": "Weekly Discovery Complete",
                    "body": "Discovery finished successfully.",
                    "priority": "low",
                },
                {
                    "title": "New Pattern Detected",
                    "body": "You have a late-night focus pattern emerging.",
                    "priority": "medium",
                    "pattern_slug": "late-night-focus-sessions",
                },
            ],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    assert [n.context_id for n in fake_channel.sent] == [
        None,
        "pattern:late-night-focus-sessions",
    ]


def test_discovery_notifications_match_canonical_pattern_slug_variants(tmp_path):
    """Pattern notification references should match canonically despite formatting variance."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [
                {
                    "title": "Late Night Focus Sessions",
                    "observation": "User consistently works after 22:00 on weeknights.",
                    "confidence": 0.85,
                    "evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "new",
                }
            ],
            "updated_patterns": [],
            "notifications": [
                {
                    "title": "Variant 1",
                    "body": "Title-shaped reference.",
                    "priority": "medium",
                    "pattern_slug": " Late Night Focus Sessions!! ",
                },
                {
                    "title": "Variant 2",
                    "body": "Case and whitespace varied reference.",
                    "priority": "medium",
                    "pattern_slug": "LATE-night   focus sessions",
                },
                {
                    "title": "Mismatch",
                    "body": "Different pattern reference.",
                    "priority": "low",
                    "pattern_slug": "morning-routine",
                },
            ],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    assert [n.context_id for n in fake_channel.sent] == [
        "pattern:late-night-focus-sessions",
        "pattern:late-night-focus-sessions",
        None,
    ]


def test_discovery_notifications_include_context_for_existing_known_pattern(tmp_path):
    """Known preexisting patterns should still thread notification context ids."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [],
            "notifications": [
                {
                    "title": "Pattern still active",
                    "body": "Late-night focus is still showing up.",
                    "priority": "medium",
                    "pattern_slug": "Late Night Focus Sessions",
                }
            ],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            await analytics.upsert_insight(
                id="late-night-focus-sessions",
                title="Night Owl Deep Work",
                status="active",
                confidence="0.7",
                first_seen="2026-03-01",
                last_seen="2026-03-10",
                vault_path="02-Insights/patterns/late-night-focus-sessions.md",
            )
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    assert len(fake_channel.sent) == 1
    assert fake_channel.sent[0].context_id == "pattern:late-night-focus-sessions"


def test_discovery_updates_preserve_existing_insight_first_seen(tmp_path):
    """Updated patterns should keep the original first_seen for existing insights."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [
                {
                    "slug": "late-night-focus-sessions",
                    "status": "confirmed",
                    "confidence": 0.91,
                    "update_note": "Still happening this week.",
                    "new_evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "stable",
                }
            ],
            "notifications": [],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            await analytics.upsert_insight(
                id="late-night-focus-sessions",
                title="Late Night Focus Sessions",
                status="active",
                confidence="0.7",
                first_seen="2026-03-01",
                last_seen="2026-03-10",
                vault_path="02-Insights/patterns/late-night-focus-sessions.md",
            )
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        pattern_content = vault.read_pattern_by_slug("late-night-focus-sessions")

        return insights[0], pattern_content

    insight, pattern_content = asyncio.run(exercise())

    assert insight["id"] == "late-night-focus-sessions"
    assert insight["first_seen"] == "2026-03-01"
    assert insight["last_seen"] == "2026-03-20"
    assert "**First seen:** 2026-03-01" in pattern_content


def test_discovery_aggregates_prior_weekly_baselines_before_reading(tmp_path):
    """Discovery should populate prior weekly baselines before consuming them."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
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

            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
                        "gmail",
                        "email.received",
                        {"subject": "Project update", "from": "alice@example.com"},
                    ),
                    _make_event(
                        "e2",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            return await analytics.get_weekly_baselines("2026-03-13")

    baselines = asyncio.run(exercise())

    assert len(baselines) == 1
    assert baselines[0]["source"] == "gmail"
    assert baselines[0]["event_type"] == "email.received"


def test_discovery_skips_malformed_pattern_entries(tmp_path):
    """Blank required identifiers should not produce insight or vault writes."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [
                {
                    "title": "   ",
                    "observation": "Should be ignored.",
                    "confidence": 0.8,
                    "evidence": ["x"],
                    "trend": "new",
                }
            ],
            "updated_patterns": [
                {
                    "slug": "   ",
                    "status": "confirmed",
                    "confidence": 0.9,
                    "update_note": "Should be ignored.",
                    "new_evidence": ["y"],
                    "trend": "stable",
                }
            ],
            "notifications": [],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        result = await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        patterns = vault.read_patterns()

        return result, insights, patterns

    result, insights, patterns = asyncio.run(exercise())

    assert result.new_patterns == 0
    assert result.updated_patterns == 0
    assert insights == []
    assert patterns == []


def test_discovery_skips_updated_pattern_when_pattern_is_unknown(tmp_path):
    """Updated patterns should not create a brand-new insight or vault file."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [
                {
                    "slug": "late-night-focus-sessions",
                    "status": "confirmed",
                    "confidence": 0.91,
                    "update_note": "Still happening this week.",
                    "new_evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "stable",
                }
            ],
            "notifications": [],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            event_repo = EventRepository(db)
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        result = await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        patterns = vault.read_patterns()

        return result, insights, patterns

    result, insights, patterns = asyncio.run(exercise())

    assert result.updated_patterns == 0
    assert insights == []
    assert patterns == []


def test_discovery_skips_updated_pattern_with_invalid_status(tmp_path):
    """Updated patterns should not write statuses outside the bounded contract."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [
                {
                    "slug": "late-night-focus-sessions",
                    "status": "definitely-maybe",
                    "confidence": 0.91,
                    "update_note": "Still happening this week.",
                    "new_evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "stable",
                }
            ],
            "notifications": [],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            await analytics.upsert_insight(
                id="late-night-focus-sessions",
                title="Late Night Focus Sessions",
                status="active",
                confidence="0.7",
                first_seen="2026-03-01",
                last_seen="2026-03-10",
                vault_path="02-Insights/patterns/late-night-focus-sessions.md",
            )
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        result = await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insight = await analytics.get_insight("late-night-focus-sessions")

        return result, insight

    result, insight = asyncio.run(exercise())

    assert result.updated_patterns == 0
    assert insight is not None
    assert insight["status"] == "active"


def test_discovery_updates_preserve_existing_insight_title(tmp_path):
    """Updated patterns should reuse the stored title instead of regenerating from slug."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [
                {
                    "slug": "late-night-focus-sessions",
                    "status": "confirmed",
                    "confidence": 0.91,
                    "update_note": "Still happening this week.",
                    "new_evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "stable",
                }
            ],
            "notifications": [],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            await analytics.upsert_insight(
                id="late-night-focus-sessions",
                title="Night Owl Deep Work",
                status="active",
                confidence="0.7",
                first_seen="2026-03-01",
                last_seen="2026-03-10",
                vault_path="02-Insights/patterns/late-night-focus-sessions.md",
            )
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
        )
        await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insight = await analytics.get_insight("late-night-focus-sessions")

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        pattern_content = vault.read_pattern_by_slug("late-night-focus-sessions")

        return insight, pattern_content

    insight, pattern_content = asyncio.run(exercise())

    assert insight is not None
    assert insight["title"] == "Night Owl Deep Work"
    assert "# Pattern: Night Owl Deep Work" in pattern_content
    assert "type: pattern" in pattern_content
    assert "## Related days" in pattern_content


def test_discovery_canonicalizes_updated_pattern_slugs(tmp_path):
    """Updated pattern slugs should normalize before any DB, vault, or context use."""
    from pulse.analysis.discovery import DiscoveryEngine
    from pulse.store.analytics import AnalyticsRepository
    from pulse.store.db import connect_db
    from pulse.store.events import EventRepository
    from pulse.store.schema import bootstrap_schema

    db_path = tmp_path / "test.db"
    vault_root = tmp_path / "vault"
    target_date = date(2026, 3, 20)

    response = json.dumps(
        {
            "new_patterns": [],
            "updated_patterns": [
                {
                    "slug": "  Late Night Focus Sessions../  ",
                    "status": "confirmed",
                    "confidence": 0.91,
                    "update_note": "Still happening this week.",
                    "new_evidence": ["2026-03-20: writing 23:00-00:30"],
                    "trend": "stable",
                }
            ],
            "notifications": [
                {
                    "title": "Pattern updated",
                    "body": "Late-night focus is still active.",
                    "priority": "medium",
                    "pattern_slug": "Late Night Focus Sessions",
                }
            ],
            "baseline_updates": None,
        }
    )
    fake_llm = FakeLLM(response)
    fake_channel = FakeChannel()

    async def exercise():
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            analytics = AnalyticsRepository(db)
            event_repo = EventRepository(db)

            await analytics.upsert_insight(
                id="late-night-focus-sessions",
                title="Night Owl Deep Work",
                status="active",
                confidence="0.7",
                first_seen="2026-03-01",
                last_seen="2026-03-10",
                vault_path="02-Insights/patterns/late-night-focus-sessions.md",
            )
            await event_repo.upsert_events(
                [
                    _make_event(
                        "e1",
                        datetime(2026, 3, 20, 22, 30, tzinfo=UTC),
                        "github",
                        "commit.pushed",
                        {"message": "feat: add new endpoint"},
                    ),
                ]
            )

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=fake_channel,
        )
        result = await engine.run_discovery("daily", target_date)

        async with connect_db(db_path) as db:
            analytics = AnalyticsRepository(db)
            insights = await analytics.list_insights()

        from pulse.analysis.vault_memory import VaultMemory

        vault = VaultMemory(vault_root)
        canonical = vault.read_pattern_by_slug("late-night-focus-sessions")
        unsafe = vault.read_pattern_by_slug("late-night-focus-sessions..")

        return result, insights, canonical, unsafe

    result, insights, canonical, unsafe = asyncio.run(exercise())

    assert result.updated_patterns == 1
    assert len(insights) == 1
    assert insights[0]["id"] == "late-night-focus-sessions"
    assert insights[0]["title"] == "Night Owl Deep Work"
    assert canonical
    assert unsafe == ""
    assert len(fake_channel.sent) == 1
    assert fake_channel.sent[0].context_id == "pattern:late-night-focus-sessions"


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
                _make_event(
                    "e1",
                    datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                    "gmail",
                    "email.received",
                    {"subject": "Project update", "from": "alice@example.com"},
                ),
                _make_event(
                    "e2",
                    datetime(2026, 3, 20, 14, 0, tzinfo=UTC),
                    "browser",
                    "browsing.visit",
                    {"url": "https://docs.rs/tokio", "title": "tokio - Rust"},
                ),
            ]
            await event_repo.upsert_events(events)

        engine = DiscoveryEngine(
            database_path=db_path,
            vault_root=vault_root,
            llm=fake_llm,
            notification_channel=None,
            summarization_model="claude-haiku-4-5-20251001",
            discovery_model="claude-sonnet-4-6",
        )
        return await engine.run_discovery("daily", target_date)

    asyncio.run(exercise())

    # Should have summarization calls (haiku) + 1 discovery call (sonnet)
    haiku_calls = [
        c for c in fake_llm.calls if c["model"] == "claude-haiku-4-5-20251001"
    ]
    sonnet_calls = [c for c in fake_llm.calls if c["model"] == "claude-sonnet-4-6"]

    assert len(haiku_calls) >= 1, "Should have at least one Haiku summarization call"
    assert len(sonnet_calls) == 1, "Should have exactly one Sonnet discovery call"

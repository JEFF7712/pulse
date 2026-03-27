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

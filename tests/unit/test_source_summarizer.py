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

from datetime import date, datetime, UTC

import pytest

from pulse.analysis.summarizer import DailySummarizer, DailySummary
from pulse.domain.events import Event


class FakeLLM:
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return (
            "## Timeline\n"
            "- 09:00 Standup with team\n"
            "\n"
            "## Email Highlights\n"
            "- Advisor sent portfolio update\n"
            "\n"
            "## Spending\n"
            "- No spending recorded.\n"
            "\n"
            "## Health\n"
            "- No health updates.\n"
            "\n"
            "## Media\n"
            "- No media activity.\n"
            "\n"
            "## Insights\n"
            "- Light day with only 1 meeting\n"
            "- Email from advisor may need follow-up\n"
        )


@pytest.mark.asyncio
async def test_summarizer_with_llm_produces_insights():
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Standup"},
        ),
    ]
    summarizer = DailySummarizer(llm=FakeLLM())
    summary = await summarizer.summarize(date(2026, 3, 22), events)

    assert isinstance(summary, DailySummary)
    assert "## Insights" in summary.markdown
    assert "Light day" in summary.markdown
    assert "## Timeline" in summary.markdown


@pytest.mark.asyncio
async def test_summarizer_without_llm_falls_back_to_raw():
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Standup"},
        ),
    ]
    summarizer = DailySummarizer()
    summary = await summarizer.summarize(date(2026, 3, 22), events)

    assert "## Timeline" in summary.markdown
    assert "Standup" in summary.markdown
    assert "## Insights" not in summary.markdown

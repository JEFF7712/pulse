from datetime import UTC, date, datetime

import pytest


@pytest.mark.asyncio
async def test_daily_summarizer_renders_markdown_digest_from_events():
    from pulse.analysis.summarizer import DailySummarizer
    from pulse.domain.events import Event

    day = date(2026, 3, 22)
    events = [
        Event(
            id="evt-1",
            timestamp=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            source="calendar",
            event_type="calendar.event",
            data={"title": "Team sync"},
        ),
        Event(
            id="evt-2",
            timestamp=datetime(2026, 3, 22, 10, 30, tzinfo=UTC),
            source="email",
            event_type="email.received",
            data={"subject": "Project update"},
        ),
        Event(
            id="evt-3",
            timestamp=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
            source="slack",
            event_type="message.created",
            data={},
        ),
    ]

    summary = await DailySummarizer().summarize(day, events)

    expected = "\n".join(
        [
            "# 2026-03-22",
            "",
            "## Timeline",
            "- Team sync",
            "- message.created",
            "",
            "## Email Highlights",
            "- Project update",
            "",
            "## Spending",
            "- No spending recorded.",
            "",
            "## Health",
            "- No health updates.",
            "",
            "## Media",
            "- No media activity.",
            "",
            "## Tags",
            "- No tags.",
        ]
    )

    assert summary.day == day
    assert summary.markdown == expected

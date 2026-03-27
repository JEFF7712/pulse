from datetime import UTC, datetime

from pulse.analysis.preprocessor import EventPreprocessor
from pulse.domain.events import Event


def test_finance_summary_groups_merchants():
    p = EventPreprocessor()
    events = [
        Event(
            id="p1",
            timestamp=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
            source="plaid",
            event_type="finance.transaction",
            data={
                "name": "Cafe",
                "amount": 4.5,
                "omit_amount_in_digest": False,
            },
        ),
        Event(
            id="p2",
            timestamp=datetime(2026, 3, 26, 13, 0, tzinfo=UTC),
            source="plaid",
            event_type="finance.transaction",
            data={
                "name": "Cafe",
                "amount": 3.0,
                "omit_amount_in_digest": False,
            },
        ),
    ]
    day = p.preprocess(events)
    assert day.finance_summary is not None
    assert day.finance_summary.transaction_count == 2
    assert day.finance_summary.total_outflow == 7.5
    assert day.finance_summary.omit_amounts is False


def test_finance_omit_amounts_flag():
    p = EventPreprocessor()
    events = [
        Event(
            id="p1",
            timestamp=datetime(2026, 3, 26, 12, 0, tzinfo=UTC),
            source="plaid",
            event_type="finance.transaction",
            data={"name": "X", "amount": 10.0, "omit_amount_in_digest": True},
        ),
    ]
    day = p.preprocess(events)
    assert day.finance_summary is not None
    assert day.finance_summary.omit_amounts is True


def test_dev_activities_extracted():
    p = EventPreprocessor()
    ts = datetime(2026, 3, 26, 10, 0, tzinfo=UTC)
    events = [
        Event(
            id="g1",
            timestamp=ts,
            source="github",
            event_type="dev.push",
            data={
                "title": "Push to main",
                "provider": "github",
                "action": "PushEvent",
                "repo": "acme/app",
                "url": "https://github.com/acme/app",
            },
        ),
    ]
    day = p.preprocess(events)
    assert len(day.dev_activities) == 1
    assert day.dev_activities[0].repo == "acme/app"
    assert day.dev_activities[0].title == "Push to main"

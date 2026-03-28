import asyncio
from datetime import UTC, datetime


def test_companion_connector_source_name():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()
    assert connector.get_source_name() == "companion"


def test_companion_connector_webhook_path():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()
    assert connector.get_webhook_path() == "/webhooks/companion"


def test_companion_connector_parses_location_enter_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:05:00Z",
                        "data": {
                            "place": "office",
                            "lat": 40.7128,
                            "lng": -74.006,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].source == "companion"
    assert events[0].event_type == "location.enter"
    assert events[0].data["place"] == "office"
    assert events[0].timestamp == datetime(2026, 3, 27, 9, 5, tzinfo=UTC)


def test_companion_connector_parses_location_exit_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.exit",
                        "timestamp": "2026-03-27T18:15:00Z",
                        "data": {
                            "place": "office",
                            "duration_minutes": 550,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "location.exit"
    assert events[0].data["duration_minutes"] == 550


def test_companion_connector_parses_health_steps_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "health.steps",
                        "timestamp": "2026-03-27T23:59:00Z",
                        "data": {"count": 8420},
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "health.steps"
    assert events[0].data["count"] == 8420


def test_companion_connector_parses_health_sleep_event():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "health.sleep",
                        "timestamp": "2026-03-27T07:15:00Z",
                        "data": {
                            "in_bed_minutes": 465,
                            "asleep_minutes": 410,
                        },
                    }
                ]
            }
        )
    )

    assert len(events) == 1
    assert events[0].event_type == "health.sleep"
    assert events[0].data["asleep_minutes"] == 410


def test_companion_connector_parses_batch_of_mixed_events():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:00:00Z",
                        "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                    },
                    {
                        "type": "health.steps",
                        "timestamp": "2026-03-27T23:59:00Z",
                        "data": {"count": 8420},
                    },
                ]
            }
        )
    )

    assert len(events) == 2
    types = {e.event_type for e in events}
    assert types == {"location.enter", "health.steps"}


def test_companion_connector_rejects_unknown_event_type():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "unknown.type",
                        "timestamp": "2026-03-27T09:00:00Z",
                        "data": {},
                    }
                ]
            }
        )
    )

    assert len(events) == 0


def test_companion_connector_returns_empty_for_missing_events_key():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(connector.handle_webhook({}))
    assert events == []


def test_companion_connector_event_ids_are_prefixed_with_source_name():
    from pulse.connectors.companion import CompanionConnector

    connector = CompanionConnector()

    events = asyncio.run(
        connector.handle_webhook(
            {
                "events": [
                    {
                        "type": "location.enter",
                        "timestamp": "2026-03-27T09:05:00Z",
                        "data": {"place": "office", "lat": 40.7, "lng": -74.0},
                    }
                ]
            }
        )
    )

    assert events[0].id.startswith("companion:")

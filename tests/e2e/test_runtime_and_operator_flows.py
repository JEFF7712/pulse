import asyncio
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

import pulse.app.home_actions as home_actions
from pulse.app.config import Settings
from pulse.app.main import create_app
from pulse.domain.events import Event
from pulse.store.db import connect_db
from pulse.store.events import EventRepository
from pulse.store.schema import bootstrap_schema


async def _seed_event(database_path: str, *, title: str, timestamp: datetime) -> None:
    async with connect_db(database_path) as db:
        await bootstrap_schema(db)
        repository = EventRepository(db)
        await repository.upsert_events(
            [
                Event(
                    id="runtime-e2e-event-1",
                    timestamp=timestamp,
                    source="calendar",
                    event_type="calendar.event",
                    data={"title": title},
                )
            ]
        )


def test_discovery_action_redirects_when_llm_not_configured(
    tmp_path, monkeypatch
) -> None:
    """Home discovery requires a resolved discovery LLM; without it we redirect with an error."""
    target_day = date(2026, 3, 22)
    database_path = tmp_path / "pulse.db"
    vault_path = tmp_path / "vault"

    monkeypatch.setattr(
        home_actions, "_resolve_current_day", lambda settings: target_day
    )

    asyncio.run(
        _seed_event(
            str(database_path),
            title="Runtime E2E seeded event",
            timestamp=datetime(
                target_day.year,
                target_day.month,
                target_day.day,
                9,
                0,
                tzinfo=UTC,
            ),
        )
    )

    client = TestClient(
        create_app(
            settings=Settings(
                database_path=str(database_path),
                vault_path=str(vault_path),
                timezone="UTC",
            )
        )
    )

    response = client.post("/actions/discover", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?error=discovery-not-configured"


def test_runtime_routes_are_available_with_temp_settings(tmp_path) -> None:
    client = TestClient(
        create_app(
            settings=Settings(
                database_path=str(tmp_path / "pulse.db"),
                vault_path=str(tmp_path / "vault"),
                timezone="UTC",
            )
        )
    )

    health_response = client.get("/health")
    home_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert home_response.status_code == 200
    assert "text/html" in home_response.headers["content-type"]
    assert "Pulse" in home_response.text

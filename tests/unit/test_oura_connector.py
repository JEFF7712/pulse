from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from pulse.connectors.oura import OuraConnector


def test_oura_pull_maps_sleep_and_readiness() -> None:
    sleep_payload = {
        "data": [
            {
                "id": "s1",
                "day": "2026-03-27",
                "score": 82,
                "total_sleep_duration": 25200,
                "time_in_bed_duration": 27000,
                "efficiency": 88,
                "contributors": {},
            }
        ],
        "next_token": None,
    }
    readiness_payload = {
        "data": [
            {
                "id": "r1",
                "day": "2026-03-27",
                "score": 79,
                "contributors": {},
            }
        ],
        "next_token": None,
    }
    activity_payload = {
        "data": [
            {
                "id": "a1",
                "day": "2026-03-27",
                "score": 88,
                "steps": 9100,
                "active_calories": 420,
                "equivalent_walking_distance": 7200,
            }
        ],
        "next_token": None,
    }
    workout_payload = {
        "data": [
            {
                "id": "w1",
                "sport": "cycling",
                "start_datetime": "2026-03-27T07:15:00+00:00",
                "end_datetime": "2026-03-27T08:00:00+00:00",
                "calories": 300,
                "intensity": "moderate",
            }
        ],
        "next_token": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer pat-test"
        u = str(request.url)
        if "daily_sleep" in u:
            return httpx.Response(200, json=sleep_payload)
        if "daily_readiness" in u:
            return httpx.Response(200, json=readiness_payload)
        if "daily_activity" in u:
            return httpx.Response(200, json=activity_payload)
        if "workout" in u:
            return httpx.Response(200, json=workout_payload)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    async def run():
        c = OuraConnector(personal_access_token="pat-test", http_client=client)
        events = await c.pull(since=None)
        assert len(events) == 4
        types = {e.event_type for e in events}
        assert types == {
            "health.sleep",
            "health.readiness",
            "health.activity",
            "health.workout",
        }
        sleep_ev = next(e for e in events if e.event_type == "health.sleep")
        assert sleep_ev.data["day"] == "2026-03-27"
        assert sleep_ev.data["score"] == 82
        assert sleep_ev.timestamp == datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        wo = next(e for e in events if e.event_type == "health.workout")
        assert wo.data["title"] == "cycling"
        assert wo.data["duration_seconds"] == 2700

    import asyncio

    asyncio.run(run())


def test_oura_auth_manager_exchange_code() -> None:
    from pulse.connectors.oura_auth import OuraAuthManager

    mock_response = httpx.Response(
        200,
        json={
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
        },
        request=httpx.Request("POST", "https://api.ouraring.com/oauth/token"),
    )
    with patch("pulse.connectors.oura_auth.httpx.post", return_value=mock_response):
        m = OuraAuthManager("cid", "sec", Path("/tmp/oura_tok.json"))
        data = m._exchange_code("code")
        assert data["access_token"] == "a"
        assert "expires_at" in data

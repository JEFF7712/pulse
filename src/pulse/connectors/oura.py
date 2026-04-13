"""Oura Ring sleep, readiness, daily activity, and workouts → Pulse health.* events."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from pulse.connectors.oura_auth import OuraAuthManager
from pulse.domain.connectors import Connector, ConnectorAuthError
from pulse.domain.events import Event

logger = logging.getLogger(__name__)

OURA_API = "https://api.ouraring.com/v2/usercollection"
_DEFAULT_LOOKBACK_DAYS = 14


def _parse_oura_datetime(raw: object) -> datetime | None:
    if not raw:
        return None
    s = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:
        return None


class OuraConnector(Connector):
    def __init__(
        self,
        auth_manager: OuraAuthManager | None = None,
        personal_access_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth = auth_manager
        pat = (personal_access_token or "").strip()
        self._pat = pat or None
        self._http = http_client

    def get_source_name(self) -> str:
        return "oura"

    def get_default_interval(self) -> timedelta:
        return timedelta(hours=6)

    async def validate_config(self) -> bool:
        if self._pat:
            return True
        return self._auth is not None and self._auth.is_authorized()

    def _bearer(self) -> str:
        if self._pat:
            return self._pat
        if self._auth is None:
            raise RuntimeError("Initialize Oura auth manager")
        return self._auth.get_valid_token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._bearer()}"}

    async def pull(self, since: datetime | None = None) -> list[Event]:
        if not await self.validate_config():
            return []

        end_d = datetime.now(UTC).date()
        sync_cursor = since.astimezone(UTC) if since is not None else None
        if sync_cursor is not None:
            start_d = sync_cursor.date()
        else:
            start_d = end_d - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
        if start_d > end_d:
            start_d = end_d

        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        events: list[Event] = []

        try:
            sleep_rows = await self._fetch_paginated(
                client, "daily_sleep", start_d, end_d
            )
            readiness_rows = await self._fetch_paginated(
                client, "daily_readiness", start_d, end_d
            )
            activity_rows = await self._fetch_paginated_optional(
                client, "daily_activity", start_d, end_d
            )
            workout_rows = await self._fetch_paginated_optional(
                client, "workout", start_d, end_d
            )

            for row in sleep_rows:
                ev = _sleep_event(row)
                if ev is None:
                    continue
                if sync_cursor is not None and ev.timestamp <= sync_cursor:
                    continue
                events.append(ev)

            for row in readiness_rows:
                ev = _readiness_event(row)
                if ev is None:
                    continue
                if sync_cursor is not None and ev.timestamp <= sync_cursor:
                    continue
                events.append(ev)

            for row in activity_rows:
                ev = _activity_event(row)
                if ev is None:
                    continue
                if sync_cursor is not None and ev.timestamp <= sync_cursor:
                    continue
                events.append(ev)

            for row in workout_rows:
                ev = _workout_event(row)
                if ev is None:
                    continue
                if sync_cursor is not None and ev.timestamp <= sync_cursor:
                    continue
                events.append(ev)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(
                    "Oura API unauthorized — run `pulse configure` → Connectors → Oura, "
                    "or set PULSE_OURA_PERSONAL_ACCESS_TOKEN"
                )
                raise ConnectorAuthError(
                    "Oura API unauthorized — run `pulse configure` → Connectors → Oura, "
                    "or set PULSE_OURA_PERSONAL_ACCESS_TOKEN"
                ) from e
            logger.warning("Oura API error: %s", e)
            return []
        except Exception:
            logger.exception("Oura pull failed")
            return []
        finally:
            if owns:
                await client.aclose()

        return events

    async def _fetch_paginated(
        self,
        client: httpx.AsyncClient,
        resource: str,
        start_d: date,
        end_d: date,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            params: dict[str, str] = {
                "start_date": start_d.isoformat(),
                "end_date": end_d.isoformat(),
            }
            if next_token:
                params["next_token"] = next_token
            resp = await client.get(
                f"{OURA_API}/{resource}",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data") or []
            if isinstance(data, list):
                rows.extend(data)
            next_token = body.get("next_token")
            if not next_token:
                break
        return rows

    async def _fetch_paginated_optional(
        self,
        client: httpx.AsyncClient,
        resource: str,
        start_d: date,
        end_d: date,
    ) -> list[dict[str, Any]]:
        try:
            return await self._fetch_paginated(client, resource, start_d, end_d)
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Oura %s not available (HTTP %s); omitting.",
                resource,
                e.response.status_code,
            )
            return []
        except Exception:
            logger.warning("Oura %s fetch failed; omitting.", resource, exc_info=True)
            return []


def _day_anchor(day_str: str) -> datetime:
    """Noon UTC on ``day_str`` so the row sorts into that calendar day in string range queries."""
    d = date.fromisoformat(day_str)
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=UTC)


def _sleep_event(row: dict[str, Any]) -> Event | None:
    day = row.get("day")
    if not day:
        return None
    day_s = str(day)
    eid = row.get("id")
    if not eid:
        eid = f"sleep:{day_s}"

    score = row.get("score")
    contributors = (
        row.get("contributors") if isinstance(row.get("contributors"), dict) else {}
    )

    return Event(
        id=f"oura:sleep:{eid}",
        timestamp=_day_anchor(day_s),
        source="oura",
        event_type="health.sleep",
        data={
            "day": day_s,
            "score": score,
            "total_sleep_seconds": row.get("total_sleep_duration"),
            "time_in_bed_seconds": row.get("time_in_bed_duration"),
            "efficiency": row.get("efficiency"),
            "restless_periods": row.get("restless_periods"),
            "deep_sleep_seconds": row.get("deep_sleep_duration"),
            "rem_sleep_seconds": row.get("rem_sleep_duration"),
            "light_sleep_seconds": row.get("light_sleep_duration"),
            "awake_seconds": row.get("awake_time"),
            "bedtime_start": row.get("bedtime_start"),
            "bedtime_end": row.get("bedtime_end"),
            "contributors": contributors,
        },
        metadata={},
    )


def _readiness_event(row: dict[str, Any]) -> Event | None:
    day = row.get("day")
    if not day:
        return None
    day_s = str(day)
    eid = row.get("id")
    if not eid:
        eid = f"readiness:{day_s}"

    score = row.get("score")
    contributors = (
        row.get("contributors") if isinstance(row.get("contributors"), dict) else {}
    )

    return Event(
        id=f"oura:readiness:{eid}",
        timestamp=_day_anchor(day_s),
        source="oura",
        event_type="health.readiness",
        data={
            "day": day_s,
            "score": score,
            "temperature_deviation": row.get("temperature_deviation"),
            "temperature_trend": row.get("temperature_trend"),
            "contributors": contributors,
        },
        metadata={},
    )


def _activity_event(row: dict[str, Any]) -> Event | None:
    day = row.get("day")
    if not day:
        return None
    day_s = str(day)
    eid = row.get("id")
    if not eid:
        eid = f"activity:{day_s}"

    return Event(
        id=f"oura:activity:{eid}",
        timestamp=_day_anchor(day_s),
        source="oura",
        event_type="health.activity",
        data={
            "day": day_s,
            "score": row.get("score"),
            "steps": row.get("steps"),
            "equivalent_walking_distance_meters": row.get(
                "equivalent_walking_distance"
            ),
            "high_activity_met_minutes": row.get("high_activity_met_minutes"),
            "medium_activity_met_minutes": row.get("medium_activity_met_minutes"),
            "low_activity_met_minutes": row.get("low_activity_met_minutes"),
            "active_calories": row.get("active_calories"),
            "total_calories": row.get("total_calories"),
            "target_calories": row.get("target_calories"),
        },
        metadata={},
    )


def _workout_event(row: dict[str, Any]) -> Event | None:
    wid = row.get("id")
    start_raw = row.get("start_datetime") or row.get("start_time")
    ts = _parse_oura_datetime(start_raw)
    if not wid or ts is None:
        return None

    end_raw = row.get("end_datetime") or row.get("end_time")
    end_ts = _parse_oura_datetime(end_raw)
    duration_s: int | None = None
    if end_ts is not None:
        duration_s = max(0, int((end_ts - ts).total_seconds()))

    label = row.get("sport") or row.get("activity") or row.get("label") or "Workout"

    return Event(
        id=f"oura:workout:{wid}",
        timestamp=ts,
        source="oura",
        event_type="health.workout",
        data={
            "title": str(label),
            "calories": row.get("calories"),
            "intensity": row.get("intensity"),
            "distance_meters": row.get("distance"),
            "start_datetime": str(start_raw) if start_raw else "",
            "end_datetime": str(end_raw) if end_raw else "",
            "duration_seconds": duration_s,
            "source_device": row.get("source"),
        },
        metadata={},
    )

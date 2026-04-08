"""Linear assigned issues → Pulse dev.linear.issue events (development activity stream)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulse.domain.connectors import Connector
from pulse.domain.events import Event

logger = logging.getLogger(__name__)

LINEAR_GQL = "https://api.linear.app/graphql"
_DEFAULT_LOOKBACK = timedelta(days=14)
_MAX_PAGES = 25

# Assignee = viewer; filter client-side by updatedAt (avoids DateTime filter schema drift).
_ASSIGNED_ISSUES_QUERY = """
query AssignedIssues($after: String) {
  issues(
    first: 50
    after: $after
    filter: { assignee: { isMe: { eq: true } } }
    orderBy: updatedAt
  ) {
    nodes {
      id
      identifier
      title
      url
      updatedAt
      state { name }
      team { key name }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


class LinearConnector(Connector):
    def __init__(
        self,
        api_key: str | None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip() or None
        self._http = http_client

    def get_source_name(self) -> str:
        return "linear"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._api_key is not None

    def _headers(self) -> dict[str, str]:
        assert self._api_key is not None
        return {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }

    async def pull(self, since: datetime | None = None) -> list[Event]:
        if not self._api_key:
            return []

        sync_cursor = since.astimezone(UTC) if since is not None else None
        lookback = datetime.now(UTC) - _DEFAULT_LOOKBACK

        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        out: list[Event] = []

        try:
            cursor: str | None = None
            for _ in range(_MAX_PAGES):
                payload = {
                    "query": _ASSIGNED_ISSUES_QUERY,
                    "variables": {"after": cursor},
                }
                resp = await client.post(LINEAR_GQL, json=payload, headers=self._headers())
                if resp.status_code == 401:
                    logger.warning("Linear API unauthorized — check PULSE_LINEAR_API_KEY")
                    return []
                resp.raise_for_status()
                body = resp.json()
                errs = body.get("errors")
                if errs:
                    logger.warning("Linear GraphQL errors: %s", errs)
                    return []

                data = body.get("data") or {}
                conn = (data.get("issues") or {}) if isinstance(data, dict) else {}
                nodes = conn.get("nodes") or []
                if not isinstance(nodes, list):
                    break

                stop_paging = False
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    parsed = _parse_issue_node(node, sync_cursor, lookback)
                    if parsed == "stop":
                        stop_paging = True
                        break
                    if parsed is None:
                        continue
                    out.append(parsed)
                if stop_paging:
                    break

                page = conn.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                    break
                cursor = page.get("endCursor")
                if not cursor:
                    break
        except httpx.HTTPStatusError as e:
            logger.warning("Linear HTTP error: %s", e)
            return []
        except Exception:
            logger.exception("Linear pull failed")
            return []
        finally:
            if owns:
                await client.aclose()

        return out


def _parse_issue_node(
    node: dict[str, Any],
    sync_cursor: datetime | None,
    lookback: datetime,
) -> Event | None | str:
    """Return Event, None to skip, or 'stop' if older than lookback (stop paging)."""
    iid = node.get("id")
    if not isinstance(iid, str) or not iid:
        return None
    raw_updated = node.get("updatedAt")
    if not raw_updated:
        return None
    try:
        ts = datetime.fromisoformat(str(raw_updated).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None

    if ts < lookback:
        return "stop"
    if sync_cursor is not None and ts <= sync_cursor:
        return None

    ident = str(node.get("identifier") or "").strip()
    title = str(node.get("title") or "").strip() or "(issue)"
    team = node.get("team") if isinstance(node.get("team"), dict) else {}
    team_key = str(team.get("key") or "").strip()
    state = node.get("state") if isinstance(node.get("state"), dict) else {}
    state_name = str(state.get("name") or "").strip()

    url = str(node.get("url") or "").strip()
    display = f"{ident}: {title}" if ident else title
    repo = f"{team_key}/{ident}" if team_key and ident else (team_key or "linear")

    return Event(
        id=f"linear:{iid}",
        timestamp=ts,
        source="linear",
        event_type="dev.linear.issue",
        data={
            "title": display,
            "url": url,
            "identifier": ident,
            "issue_title": title,
            "team": team_key,
            "state": state_name,
            "provider": "linear",
            "action": "issue.updated",
            "repo": repo,
        },
        metadata={},
    )

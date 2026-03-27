"""GitLab user events → Pulse dev.* events."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulse.connectors.gitlab_auth import GitLabAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

_MAX_EVENTS = 50


def _map_action_kind(action_name: str) -> str:
    if action_name in ("pushed to", "pushed new"):
        return "dev.push"
    if "issue" in action_name and "comment" not in action_name:
        return "dev.issue"
    if "merge request" in action_name or action_name.startswith("opened merge request"):
        return "dev.pull_request"
    if "comment" in action_name:
        return "dev.comment"
    return "dev.repo_activity"


class GitLabConnector(Connector):
    def __init__(
        self,
        base_url: str = "https://gitlab.com",
        personal_token: str | None = None,
        auth_manager: GitLabAuthManager | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._personal_token = personal_token
        self._auth_manager = auth_manager
        self._http = http_client

    def get_source_name(self) -> str:
        return "gitlab"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        if self._personal_token:
            return True
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _headers(self) -> dict[str, str]:
        if self._personal_token:
            return {"PRIVATE-TOKEN": self._personal_token}
        assert self._auth_manager is not None
        return {"Authorization": f"Bearer {self._auth_manager.get_valid_token()}"}

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        try:
            resp = await client.get(
                f"{self._base}/api/v4/events",
                params={"per_page": _MAX_EVENTS},
                headers=self._headers(),
            )
            resp.raise_for_status()
            rows = resp.json()
            events: list[Event] = []
            for row in rows:
                created = row.get("created_at")
                if not created:
                    continue
                ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if since is not None and ts <= since.astimezone(UTC):
                    continue
                eid = str(row.get("id", ""))
                target_title = row.get("target_title") or ""
                proj = row.get("project_id")
                repo = str(proj) if proj is not None else ""
                action = row.get("action_name") or row.get("push_data", {}).get("action") or "activity"
                et = _map_action_kind(str(action).lower())
                title = target_title or f"{action} (project {repo})"
                url = row.get("target_url") or self._base
                events.append(
                    Event(
                        id=f"gitlab:{eid}",
                        timestamp=ts,
                        source="gitlab",
                        event_type=et,
                        data={
                            "repo": repo,
                            "action": str(action),
                            "title": title,
                            "url": url,
                            "provider": "gitlab",
                        },
                    )
                )
            return events
        finally:
            if owns:
                await client.aclose()

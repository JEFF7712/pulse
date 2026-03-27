"""GitHub user events → Pulse dev.* events."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pulse.connectors.github_auth import GitHubAuthManager
from pulse.domain.connectors import Connector
from pulse.domain.events import Event

GITHUB_API = "https://api.github.com"
_MAX_EVENTS = 50


def _map_event_type(gh_type: str) -> str:
    if gh_type == "PushEvent":
        return "dev.push"
    if gh_type == "IssuesEvent":
        return "dev.issue"
    if gh_type == "PullRequestEvent":
        return "dev.pull_request"
    if gh_type in ("IssueCommentEvent", "PullRequestReviewCommentEvent"):
        return "dev.comment"
    return "dev.repo_activity"


def _title_for_event(row: dict[str, Any]) -> str:
    t = row.get("type", "")
    payload = row.get("payload") or {}
    repo = (row.get("repo") or {}).get("name", "")
    if t == "PushEvent":
        ref = (payload.get("ref") or "").split("/")[-1]
        commits = payload.get("commits") or []
        return f"Push to {ref} ({len(commits)} commits) — {repo}"
    if t == "IssuesEvent":
        issue = payload.get("issue") or {}
        return issue.get("title") or f"Issue in {repo}"
    if t == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        return pr.get("title") or f"PR in {repo}"
    if t == "WatchEvent":
        return f"Starred {repo}"
    if t == "CreateEvent":
        return f"Created {payload.get('ref_type', 'ref')} in {repo}"
    return f"{t} — {repo}"


def _url_for_event(row: dict[str, Any]) -> str:
    payload = row.get("payload") or {}
    for key in ("pull_request", "issue", "comment"):
        obj = payload.get(key)
        if isinstance(obj, dict) and obj.get("html_url"):
            return str(obj["html_url"])
    repo = (row.get("repo") or {}).get("name", "")
    if repo:
        return f"https://github.com/{repo}"
    return ""


class GitHubConnector(Connector):
    def __init__(
        self,
        auth_manager: GitHubAuthManager | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._http = http_client

    def get_source_name(self) -> str:
        return "github"

    def get_default_interval(self) -> timedelta:
        return timedelta(minutes=30)

    async def validate_config(self) -> bool:
        return self._auth_manager is not None and self._auth_manager.is_authorized()

    def _headers(self) -> dict[str, str]:
        assert self._auth_manager is not None
        token = self._auth_manager.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def pull(self, since: datetime | None = None) -> list[Event]:
        client = self._http or httpx.AsyncClient(timeout=60.0)
        owns = self._http is None
        try:
            params: dict[str, str | int] = {"per_page": _MAX_EVENTS}
            resp = await client.get(
                f"{GITHUB_API}/user/events",
                params=params,
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
                repo_name = (row.get("repo") or {}).get("name", "")
                et = _map_event_type(row.get("type", ""))
                eid = str(row.get("id", ""))
                events.append(
                    Event(
                        id=f"github:{eid}",
                        timestamp=ts,
                        source="github",
                        event_type=et,
                        data={
                            "repo": repo_name,
                            "action": row.get("type", ""),
                            "title": _title_for_event(row),
                            "url": _url_for_event(row),
                            "provider": "github",
                        },
                    )
                )
            return events
        finally:
            if owns:
                await client.aclose()

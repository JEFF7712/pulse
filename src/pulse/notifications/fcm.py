"""FCM notification channel — sends push notifications via Firebase Cloud Messaging."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pulse.domain.notifications import Notification

logger = logging.getLogger(__name__)

_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class HTTPClient(Protocol):
    def post(self, url: str, *, headers: dict, json: dict) -> Any: ...


class FCMChannel:
    def __init__(
        self,
        project_id: str,
        credentials: Any,
        device_tokens: list[dict[str, str]],
        http_client: HTTPClient | None = None,
    ) -> None:
        self._project_id = project_id
        self._credentials = credentials
        self._device_tokens = device_tokens
        self._url = _FCM_SEND_URL.format(project_id=project_id)

        if http_client is None:
            import httpx

            self._http: HTTPClient = httpx
        else:
            self._http = http_client

    def send(self, notification: Notification) -> bool:
        if not self._device_tokens:
            return False

        self._ensure_valid_credentials()

        headers = {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

        for device in self._device_tokens:
            message: dict[str, Any] = {
                "token": device["token"],
                "notification": {
                    "title": notification.title,
                    "body": notification.body,
                },
            }

            data: dict[str, str] = {"category": notification.category}
            if notification.context_id is not None:
                data["context_id"] = notification.context_id
            if data:
                message["data"] = data

            try:
                response = self._http.post(
                    self._url,
                    headers=headers,
                    json={"message": message},
                )
                response.raise_for_status()
            except Exception:
                logger.warning(
                    "FCM send failed for token %s…",
                    device["token"][:8],
                    exc_info=True,
                )

        return True

    def _ensure_valid_credentials(self) -> None:
        if not self._credentials.valid:
            import google.auth.transport.requests

            self._credentials.refresh(google.auth.transport.requests.Request())

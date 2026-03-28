import httpx

from pulse.domain.notifications import Notification


class WebhookNotificationChannel:
    """POST notification payload as JSON to an HTTP endpoint."""

    def __init__(self, url: str) -> None:
        self._url = url

    def send(self, notification: Notification) -> bool:
        payload = {
            "title": notification.title,
            "body": notification.body,
            "category": notification.category,
            "context_id": notification.context_id,
            "priority": notification.priority,
        }
        response = httpx.post(self._url, json=payload, timeout=30.0)
        response.raise_for_status()
        return True

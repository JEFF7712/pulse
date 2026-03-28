import httpx

from pulse.domain.notifications import Notification


class SlackWebhookChannel:
    """Slack incoming webhook (app or legacy webhook URL)."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url.strip()

    def send(self, notification: Notification) -> bool:
        text = f"{notification.title}\n\n{notification.body}"
        if len(text) > 40000:
            text = text[:39997] + "..."
        response = httpx.post(self._url, json={"text": text}, timeout=30.0)
        response.raise_for_status()
        return True

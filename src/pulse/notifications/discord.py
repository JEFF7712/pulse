import httpx

from pulse.domain.notifications import Notification


class DiscordWebhookChannel:
    """Discord incoming webhook (server Settings → Integrations → Webhooks)."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url.strip()

    def send(self, notification: Notification) -> bool:
        title = notification.title[:256]
        description = notification.body
        if len(description) > 4096:
            description = description[:4093] + "..."
        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": 3447003,
                }
            ]
        }
        response = httpx.post(self._url, json=payload, timeout=30.0)
        response.raise_for_status()
        return True

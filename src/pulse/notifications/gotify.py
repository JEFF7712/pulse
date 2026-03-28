import httpx

from pulse.domain.notifications import Notification


class GotifyChannel:
    """Gotify push server (https://gotify.net/docs/pushmsg)."""

    def __init__(self, base_url: str, app_token: str) -> None:
        self._url = f"{base_url.rstrip('/')}/message"
        self._token = app_token.strip()

    def send(self, notification: Notification) -> bool:
        priority = 8 if notification.priority == "high" else 3
        payload = {
            "title": notification.title[:200],
            "message": notification.body,
            "priority": priority,
        }
        response = httpx.post(
            self._url,
            params={"token": self._token},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        return True

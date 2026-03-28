import httpx

from pulse.domain.notifications import Notification


class PushoverChannel:
    """Pushover.net mobile/desktop push (https://pushover.net/api)."""

    _API = "https://api.pushover.net/1/messages.json"

    def __init__(self, user_key: str, api_token: str) -> None:
        self._user_key = user_key.strip()
        self._api_token = api_token.strip()

    def send(self, notification: Notification) -> bool:
        message = notification.body
        if len(message) > 1024:
            message = message[:1021] + "..."
        title = notification.title[:250]
        priority = 1 if notification.priority == "high" else 0
        response = httpx.post(
            self._API,
            data={
                "token": self._api_token,
                "user": self._user_key,
                "title": title,
                "message": message,
                "priority": str(priority),
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return True

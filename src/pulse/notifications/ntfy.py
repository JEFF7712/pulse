import httpx

from pulse.domain.notifications import Notification


class NtfyChannel:
    """Push notifications via ntfy (https://ntfy.sh or self-hosted)."""

    def __init__(self, topic: str, *, base_url: str = "https://ntfy.sh") -> None:
        self._url = f"{base_url.rstrip('/')}/{topic}"

    def send(self, notification: Notification) -> bool:
        headers = {
            "Title": notification.title,
            "Tags": "pulse",
        }
        if notification.priority == "high":
            headers["Priority"] = "high"
        response = httpx.post(
            self._url,
            content=notification.body,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        return True

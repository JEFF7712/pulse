from collections.abc import Sequence

from pulse.domain.notifications import Notification, NotificationChannel


class BroadcastNotificationChannel:
    """Send the same notification to every configured channel."""

    def __init__(self, channels: Sequence[NotificationChannel]) -> None:
        if not channels:
            raise ValueError("BroadcastNotificationChannel requires at least one channel")
        self._channels = list(channels)

    def send(self, notification: Notification) -> bool:
        ok = False
        for ch in self._channels:
            if ch.send(notification):
                ok = True
        return ok

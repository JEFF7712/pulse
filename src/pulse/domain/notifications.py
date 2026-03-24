from dataclasses import dataclass
from typing import Protocol


REPLY_CONTEXT_PREFIX = "Context: "


@dataclass(slots=True)
class Notification:
    title: str
    body: str
    category: str
    context_id: str | None = None
    priority: str = "normal"


class NotificationChannel(Protocol):
    def send(self, notification: Notification) -> bool: ...


def append_reply_context(body: str, context_id: str | None) -> str:
    if context_id is None:
        return body

    return f"{body}\n\n{REPLY_CONTEXT_PREFIX}{context_id}"


def extract_reply_context(message_text: str) -> str | None:
    for line in message_text.splitlines():
        if line.startswith(REPLY_CONTEXT_PREFIX):
            context_id = line.removeprefix(REPLY_CONTEXT_PREFIX).strip()
            if context_id:
                return context_id

    return None

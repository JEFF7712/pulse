from typing import Protocol

import httpx

from pulse.domain.notifications import Notification, append_reply_context


class TelegramClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...


class _TokenBackedTelegramClient:
    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_message(self, chat_id: str, text: str) -> None:
        response = httpx.post(self._url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


class TelegramChannel:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        client: TelegramClient | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client: TelegramClient = client or _TokenBackedTelegramClient(bot_token)

    def send(self, notification: Notification) -> bool:
        # Carry the reply handle in the message body. A Telegram reply quotes the
        # original, so this is what lets an inbound "yes" be matched back to the
        # specific thing it is answering.
        body = append_reply_context(notification.body, notification.context_id)
        self.client.send_message(self.chat_id, f"{notification.title}\n\n{body}")
        return True

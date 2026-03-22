def test_telegram_channel_sends_title_and_body_and_returns_true():
    from pulse.domain.notifications import Notification
    from pulse.notifications.telegram import TelegramChannel

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def send_message(self, chat_id: str, text: str) -> None:
            self.calls.append((chat_id, text))

    client = FakeClient()
    channel = TelegramChannel(bot_token="token", chat_id="chat-123", client=client)
    notification = Notification(
        title="Daily digest",
        body="3 new signals detected.",
        category="digest",
    )

    result = channel.send(notification)

    assert result is True
    assert notification.context_id is None
    assert notification.priority == "normal"
    assert client.calls == [
        ("chat-123", "Daily digest\n\n3 new signals detected."),
    ]


def test_telegram_channel_builds_token_backed_client_when_not_injected():
    from pulse.notifications.telegram import TelegramChannel

    channel = TelegramChannel(bot_token="token-123", chat_id="chat-123")

    assert channel.client.bot_token == "token-123"

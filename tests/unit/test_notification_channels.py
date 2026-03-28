from unittest.mock import MagicMock

import httpx
import pytest

from pulse.app.config import PulseConfig
from pulse.domain.notifications import Notification
from pulse.notifications.broadcast import BroadcastNotificationChannel
import smtplib

from pulse.notifications.discord import DiscordWebhookChannel
from pulse.notifications.factory import build_notification_channel
from pulse.notifications.gotify import GotifyChannel
from pulse.notifications.ntfy import NtfyChannel
from pulse.notifications.pushover import PushoverChannel
from pulse.notifications.slack import SlackWebhookChannel
from pulse.notifications.smtp import SmtpChannel
from pulse.notifications.telegram import TelegramChannel
from pulse.notifications.webhook import WebhookNotificationChannel


def test_build_notification_channel_returns_none_when_unconfigured() -> None:
    assert build_notification_channel(PulseConfig()) is None


def test_build_notification_channel_telegram_only() -> None:
    config = PulseConfig(telegram_bot_token="t", telegram_chat_id="c")
    ch = build_notification_channel(config)
    assert isinstance(ch, TelegramChannel)


def test_build_notification_channel_ntfy_only() -> None:
    config = PulseConfig(ntfy_topic="pulse-alerts")
    ch = build_notification_channel(config)
    assert isinstance(ch, NtfyChannel)


def test_build_notification_channel_webhook_only() -> None:
    config = PulseConfig(notification_webhook_url="https://example.com/hook")
    ch = build_notification_channel(config)
    assert isinstance(ch, WebhookNotificationChannel)


def test_build_notification_channel_broadcast_when_multiple() -> None:
    config = PulseConfig(
        telegram_bot_token="t",
        telegram_chat_id="c",
        ntfy_topic="pulse",
    )
    ch = build_notification_channel(config)
    assert isinstance(ch, BroadcastNotificationChannel)


def test_build_notification_channel_discord_only() -> None:
    config = PulseConfig(discord_webhook_url="https://discord.com/api/webhooks/x/y")
    ch = build_notification_channel(config)
    assert isinstance(ch, DiscordWebhookChannel)


def test_build_notification_channel_slack_only() -> None:
    config = PulseConfig(slack_webhook_url="https://hooks.slack.com/services/T/B/x")
    ch = build_notification_channel(config)
    assert isinstance(ch, SlackWebhookChannel)


def test_build_notification_channel_gotify_only_when_url_and_token() -> None:
    assert build_notification_channel(PulseConfig(gotify_url="https://g.example.com")) is None
    ch = build_notification_channel(
        PulseConfig(gotify_url="https://g.example.com", gotify_app_token="tok")
    )
    assert isinstance(ch, GotifyChannel)


def test_build_notification_channel_smtp_when_host_from_to_set() -> None:
    assert build_notification_channel(PulseConfig(smtp_host="smtp.example.com")) is None
    ch = build_notification_channel(
        PulseConfig(
            smtp_host="smtp.example.com",
            smtp_from="from@example.com",
            smtp_to="a@example.com, b@example.com",
        )
    )
    assert isinstance(ch, SmtpChannel)


def test_build_notification_channel_pushover_only_when_both_set() -> None:
    assert build_notification_channel(PulseConfig(pushover_user_key="u")) is None
    assert build_notification_channel(PulseConfig(pushover_api_token="t")) is None
    ch = build_notification_channel(
        PulseConfig(pushover_user_key="user", pushover_api_token="app")
    )
    assert isinstance(ch, PushoverChannel)


def test_broadcast_sends_to_all_subchannels() -> None:
    class Recording:
        def __init__(self) -> None:
            self.sent: list[Notification] = []

        def send(self, notification: Notification) -> bool:
            self.sent.append(notification)
            return True

    a, b = Recording(), Recording()
    bc = BroadcastNotificationChannel([a, b])
    n = Notification(title="Hi", body="Body", category="test")
    assert bc.send(n) is True
    assert len(a.sent) == 1 and len(b.sent) == 1
    assert a.sent[0].title == "Hi"


def test_broadcast_true_if_any_subchannel_succeeds() -> None:
    class Bad:
        def send(self, notification: Notification) -> bool:
            return False

    class Ok:
        def send(self, notification: Notification) -> bool:
            return True

    bc = BroadcastNotificationChannel([Bad(), Ok()])
    n = Notification(title="t", body="b", category="c")
    assert bc.send(n) is True


def test_broadcast_false_if_all_subchannels_fail() -> None:
    class Bad:
        def send(self, notification: Notification) -> bool:
            return False

    bc = BroadcastNotificationChannel([Bad(), Bad()])
    n = Notification(title="t", body="b", category="c")
    assert bc.send(n) is False


def test_broadcast_requires_at_least_one_channel() -> None:
    with pytest.raises(ValueError, match="at least one"):
        BroadcastNotificationChannel([])


def test_ntfy_channel_posts_with_title_header(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted.update(kwargs)
        return MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = NtfyChannel("my-topic", base_url="https://ntfy.example.com")
    n = Notification(title="Briefing", body="Line one", category="morning_briefing")
    assert ch.send(n) is True
    assert posted["url"] == "https://ntfy.example.com/my-topic"
    assert posted["headers"]["Title"] == "Briefing"
    assert posted["content"] == "Line one"


def test_webhook_channel_posts_json(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        return MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = WebhookNotificationChannel("https://hooks.example.com/pulse")
    n = Notification(
        title="T",
        body="B",
        category="insight",
        context_id="pattern:foo",
        priority="high",
    )
    assert ch.send(n) is True
    assert posted["json"]["category"] == "insight"
    assert posted["json"]["context_id"] == "pattern:foo"


def test_discord_webhook_posts_embed_json(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        return MagicMock(status_code=204, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = DiscordWebhookChannel("https://discord.com/api/webhooks/1/2")
    n = Notification(title="Title", body="Body text", category="c")
    assert ch.send(n) is True
    assert posted["json"]["embeds"][0]["title"] == "Title"
    assert posted["json"]["embeds"][0]["description"] == "Body text"


def test_slack_webhook_posts_text(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["json"] = kwargs.get("json")
        return MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = SlackWebhookChannel("https://hooks.slack.com/x")
    n = Notification(title="Hi", body="There", category="c")
    assert ch.send(n) is True
    assert "Hi" in posted["json"]["text"]
    assert "There" in posted["json"]["text"]


def test_pushover_posts_form(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["data"] = kwargs.get("data")
        return MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = PushoverChannel("user-key", "app-token")
    n = Notification(title="T", body="Msg", category="c", priority="high")
    assert ch.send(n) is True
    assert posted["url"] == "https://api.pushover.net/1/messages.json"
    assert posted["data"]["user"] == "user-key"
    assert posted["data"]["token"] == "app-token"
    assert posted["data"]["priority"] == "1"


def test_gotify_channel_posts_with_token_param(monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["params"] = kwargs.get("params")
        posted["json"] = kwargs.get("json")
        return MagicMock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(httpx, "post", fake_post)
    ch = GotifyChannel("https://gotify.example.com", "app-secret")
    n = Notification(title="T", body="Hello", category="c", priority="high")
    assert ch.send(n) is True
    assert posted["url"] == "https://gotify.example.com/message"
    assert posted["params"]["token"] == "app-secret"
    assert posted["json"]["priority"] == 8


def test_smtp_channel_sends_plain_text(monkeypatch) -> None:
    instances: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=30) -> None:
            self.host = host
            self.port = port
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def ehlo(self) -> None:
            pass

        def starttls(self, context=None) -> None:
            pass

        def login(self, user, password) -> None:
            self.login_user = user
            self.login_password = password

        def send_message(self, msg) -> None:
            self.sent = msg

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    ch = SmtpChannel(
        host="smtp.example.com",
        port=587,
        from_addr="pulse@example.com",
        to_addrs=["you@example.com"],
        username="u",
        password="p",
        use_tls=True,
        use_ssl=False,
    )
    n = Notification(title="Subject line", body="Body\nLine2", category="c")
    assert ch.send(n) is True
    assert instances[0].host == "smtp.example.com"
    assert instances[0].login_user == "u"
    assert str(instances[0].sent["Subject"]) == "Subject line"


def test_smtp_channel_ssl_mode(monkeypatch) -> None:
    instances: list = []

    class FakeSMTP_SSL:
        def __init__(self, host, port, timeout=30) -> None:
            instances.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def login(self, user, password) -> None:
            pass

        def send_message(self, msg) -> None:
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP_SSL)
    ch = SmtpChannel(
        host="smtp.example.com",
        port=465,
        from_addr="a@b.co",
        to_addrs=["c@d.co"],
        use_tls=False,
        use_ssl=True,
    )
    assert ch.send(Notification(title="S", body="B", category="c")) is True
    assert instances[0] == ("smtp.example.com", 465)

"""Build outbound notification channels from Pulse config."""

from __future__ import annotations

from pulse.app.config import PulseConfig
from pulse.domain.notifications import NotificationChannel
from pulse.notifications.broadcast import BroadcastNotificationChannel
from pulse.notifications.discord import DiscordWebhookChannel
from pulse.notifications.gotify import GotifyChannel
from pulse.notifications.ntfy import NtfyChannel
from pulse.notifications.pushover import PushoverChannel
from pulse.notifications.slack import SlackWebhookChannel
from pulse.notifications.smtp import SmtpChannel
from pulse.notifications.telegram import TelegramChannel
from pulse.notifications.webhook import WebhookNotificationChannel


def build_notification_channel(config: PulseConfig) -> NotificationChannel | None:
    """Return a channel that delivers to every configured backend (or None)."""
    channels: list[NotificationChannel] = []

    if config.telegram_bot_token and config.telegram_chat_id:
        channels.append(
            TelegramChannel(
                bot_token=config.telegram_bot_token,
                chat_id=config.telegram_chat_id,
            )
        )

    if config.ntfy_topic:
        base = (config.ntfy_base_url or "https://ntfy.sh").strip()
        channels.append(NtfyChannel(config.ntfy_topic.strip(), base_url=base))

    if config.notification_webhook_url:
        channels.append(WebhookNotificationChannel(config.notification_webhook_url.strip()))

    if config.discord_webhook_url:
        channels.append(DiscordWebhookChannel(config.discord_webhook_url))

    if config.slack_webhook_url:
        channels.append(SlackWebhookChannel(config.slack_webhook_url))

    if config.pushover_user_key and config.pushover_api_token:
        channels.append(
            PushoverChannel(config.pushover_user_key, config.pushover_api_token)
        )

    if config.gotify_url and config.gotify_app_token:
        channels.append(
            GotifyChannel(config.gotify_url.strip(), config.gotify_app_token.strip())
        )

    if config.smtp_host and config.smtp_from and config.smtp_to:
        to_list = [x.strip() for x in config.smtp_to.split(",") if x.strip()]
        if to_list:
            channels.append(
                SmtpChannel(
                    host=config.smtp_host.strip(),
                    port=config.smtp_port,
                    from_addr=config.smtp_from.strip(),
                    to_addrs=to_list,
                    username=config.smtp_user.strip() if config.smtp_user else None,
                    password=config.smtp_password,
                    use_tls=config.smtp_use_tls,
                    use_ssl=config.smtp_use_ssl,
                )
            )

    if not channels:
        return None
    if len(channels) == 1:
        return channels[0]
    return BroadcastNotificationChannel(channels)

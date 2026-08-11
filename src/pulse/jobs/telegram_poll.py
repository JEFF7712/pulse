"""Long-poll Telegram for replies, so confirmations work without a public endpoint.

The webhook path needs Telegram to be able to reach Pulse, which on a self-hosted
laptop means a tunnel, a public HTTPS endpoint and a machine that is awake. Polling
inverts that: Pulse reaches out, so it works from behind NAT, survives roaming, and
resumes cleanly after a suspend.

`getUpdates` blocks server-side until an update arrives or the timeout expires, so
this is one idle connection rather than a busy loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx

from pulse.app.config import PulseConfig

logger = logging.getLogger(__name__)

SYNC_KEY = "telegram_updates"
# Server-side hold for one getUpdates call. Long enough to be genuinely idle,
# short enough that a shutdown is not left waiting on it.
POLL_TIMEOUT_SECONDS = 25
# Backoff after a transport error, so a network blip does not become a hot loop.
ERROR_BACKOFF_SECONDS = 30
_API = "https://api.telegram.org"


class TelegramPoller:
    def __init__(
        self,
        config: PulseConfig,
        *,
        client: httpx.AsyncClient | None = None,
        handler=None,
    ) -> None:
        self._config = config
        self._client = client
        self._owns_client = client is None
        self._handler = handler
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def enabled(self) -> bool:
        return bool(self._config.telegram_bot_token and self._config.telegram_chat_id)

    async def start(self) -> bool:
        if not self.enabled():
            return False
        if await self._webhook_is_active():
            # getUpdates and a registered webhook are mutually exclusive; Telegram
            # answers 409 if both are used. The webhook is the explicit choice, so
            # defer to it rather than fighting over the update stream.
            logger.info(
                "telegram: a webhook is registered, so polling stays off "
                "(delete it with deleteWebhook to switch to polling)"
            )
            return False
        self._task = asyncio.create_task(self._run(), name="telegram-poller")
        return True

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=POLL_TIMEOUT_SECONDS + 10, base_url=_API
            )
        return self._client

    def _url(self, method: str) -> str:
        return f"/bot{self._config.telegram_bot_token}/{method}"

    async def _webhook_is_active(self) -> bool:
        try:
            resp = await self._http().get(self._url("getWebhookInfo"))
            resp.raise_for_status()
            return bool((resp.json().get("result") or {}).get("url"))
        except Exception:
            logger.warning("telegram: could not check webhook state", exc_info=True)
            return False

    async def _load_offset(self) -> int:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with connect_db(self._config.database_path) as db:
            await bootstrap_schema(db)
            raw = await SyncStateRepository(db).load(SYNC_KEY)
        try:
            return int(raw) if raw else 0
        except ValueError:
            return 0

    async def _save_offset(self, offset: int) -> None:
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with connect_db(self._config.database_path) as db:
            await bootstrap_schema(db)
            await SyncStateRepository(db).save(SYNC_KEY, str(offset))

    async def _run(self) -> None:
        offset = await self._load_offset()
        logger.info("telegram: polling for replies from offset %d", offset)
        while not self._stopping.is_set():
            try:
                updates = await self._fetch(offset)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("telegram: poll failed, backing off", exc_info=True)
                await self._sleep(ERROR_BACKOFF_SECONDS)
                continue

            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    # Advance past every update, including ones we ignore. Leaving an
                    # unhandled update unacknowledged would refetch it forever.
                    offset = max(offset, update_id + 1)
                try:
                    await self._handle(update)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("telegram: failed to handle update %s", update_id)

            if updates:
                await self._save_offset(offset)

    async def _fetch(self, offset: int) -> list[dict]:
        resp = await self._http().get(
            self._url("getUpdates"),
            params={
                "offset": offset,
                "timeout": POLL_TIMEOUT_SECONDS,
                "allowed_updates": '["message"]',
            },
        )
        if resp.status_code == 409:
            logger.warning("telegram: conflict (webhook active?), backing off")
            await self._sleep(ERROR_BACKOFF_SECONDS)
            return []
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("result")
        return result if isinstance(result, list) else []

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)

    def _message_text(self, message: dict) -> str | None:
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        quoted = message.get("reply_to_message")
        if isinstance(quoted, dict) and isinstance(quoted.get("text"), str):
            # The reply carries the original's `Context:` line only via the quote.
            return f"{text}\n{quoted['text']}"
        return text

    async def _handle(self, update: dict) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return

        # Only the configured chat may decide anything. Without this, anyone who
        # finds the bot could confirm a change to the user's profile.
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if chat_id != str(self._config.telegram_chat_id):
            logger.info("telegram: ignoring message from unknown chat %s", chat_id)
            return

        text = self._message_text(message)
        if text is None:
            return

        handler = self._handler
        if handler is None:
            from pulse.services.inbound import handle_inbound_text

            handler = handle_inbound_text

        result = await handler(self._config, text)
        if result:
            await self._reply(result)

    async def _reply(self, text: str) -> None:
        try:
            await self._http().post(
                self._url("sendMessage"),
                json={"chat_id": self._config.telegram_chat_id, "text": text},
            )
        except Exception:
            logger.warning("telegram: could not acknowledge reply", exc_info=True)

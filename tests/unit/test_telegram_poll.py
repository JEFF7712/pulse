import asyncio
import json

import httpx

from pulse.app.config import PulseConfig
from pulse.jobs.telegram_poll import SYNC_KEY, TelegramPoller

CHAT = "7542293680"


def _config(tmp_path, **kw):
    return PulseConfig(
        database_path=str(tmp_path / "t.db"),
        vault_path=str(tmp_path / "vault"),
        telegram_bot_token=kw.pop("token", "TOKEN"),
        telegram_chat_id=kw.pop("chat_id", CHAT),
        **kw,
    )


def _message(text, *, chat_id=CHAT, quoted=None, update_id=1):
    msg = {"message_id": 1, "text": text, "chat": {"id": int(chat_id)}}
    if quoted:
        msg["reply_to_message"] = {"message_id": 0, "text": quoted}
    return {"update_id": update_id, "message": msg}


class _Transport(httpx.AsyncBaseTransport):
    """Stub Telegram: scripted getUpdates batches, recorded sendMessage calls."""

    def __init__(self, batches, webhook_url=""):
        self.batches = list(batches)
        self.webhook_url = webhook_url
        self.sent: list[dict] = []
        self.offsets: list[int] = []

    async def handle_async_request(self, request):
        path = request.url.path
        if path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200, json={"ok": True, "result": {"url": self.webhook_url}}
            )
        if path.endswith("/getUpdates"):
            self.offsets.append(int(request.url.params.get("offset", 0)))
            if self.batches:
                return httpx.Response(
                    200, json={"ok": True, "result": self.batches.pop(0)}
                )
            await asyncio.sleep(3600)  # idle like a real long poll
        if path.endswith("/sendMessage"):
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True, "result": []})


def _drive(tmp_path, batches, *, handler, webhook_url="", config=None):
    """Run the poller until it has consumed the scripted batches, then stop."""
    transport = _Transport(batches, webhook_url=webhook_url)

    async def _go():
        client = httpx.AsyncClient(
            transport=transport, base_url="https://api.telegram.org"
        )
        poller = TelegramPoller(
            config or _config(tmp_path), client=client, handler=handler
        )
        started = await poller.start()
        if started:
            for _ in range(200):
                if not transport.batches:
                    break
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
        await poller.stop()
        await client.aclose()
        return started

    return asyncio.run(_go()), transport


def test_a_reply_is_handled_and_acknowledged(tmp_path):
    seen = []

    async def handler(config, text):
        seen.append(text)
        return "Updated: Location is now Columbus, OH."

    started, transport = _drive(
        tmp_path, [[_message("yes", quoted="Context: abc123def456")]], handler=handler
    )

    assert started is True
    assert "yes" in seen[0] and "abc123def456" in seen[0]
    assert transport.sent[0]["text"] == "Updated: Location is now Columbus, OH."
    assert transport.sent[0]["chat_id"] == CHAT


def test_messages_from_other_chats_are_ignored(tmp_path):
    """Without this, anyone who finds the bot could confirm a profile change."""
    called = False

    async def handler(config, text):
        nonlocal called
        called = True
        return "should not happen"

    _, transport = _drive(
        tmp_path, [[_message("yes", chat_id="999999")]], handler=handler
    )

    assert called is False
    assert transport.sent == []


def test_a_non_decision_gets_no_reply(tmp_path):
    async def handler(config, text):
        return None

    _, transport = _drive(
        tmp_path, [[_message("what did I do yesterday?")]], handler=handler
    )
    assert transport.sent == []


def test_offset_advances_past_handled_updates_and_persists(tmp_path):
    async def handler(config, text):
        return None

    config = _config(tmp_path)
    _, transport = _drive(
        tmp_path,
        [[_message("hi", update_id=41), _message("there", update_id=42)]],
        handler=handler,
        config=config,
    )

    async def _stored():
        import aiosqlite

        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with aiosqlite.connect(config.database_path) as db:
            await bootstrap_schema(db)
            return await SyncStateRepository(db).load(SYNC_KEY)

    assert asyncio.run(_stored()) == "43"
    assert transport.offsets[0] == 0


def test_offset_advances_even_when_handling_raises(tmp_path):
    """An unacknowledged update is refetched forever, so a failing handler must not
    wedge the poller on the same message."""

    async def handler(config, text):
        raise RuntimeError("boom")

    config = _config(tmp_path)
    _drive(tmp_path, [[_message("yes", update_id=7)]], handler=handler, config=config)

    async def _stored():
        import aiosqlite

        from pulse.store.schema import bootstrap_schema
        from pulse.store.sync_state import SyncStateRepository

        async with aiosqlite.connect(config.database_path) as db:
            await bootstrap_schema(db)
            return await SyncStateRepository(db).load(SYNC_KEY)

    assert asyncio.run(_stored()) == "8"


def test_polling_defers_to_a_registered_webhook(tmp_path):
    """getUpdates and a webhook are mutually exclusive; Telegram answers 409."""

    async def handler(config, text):
        return None

    started, transport = _drive(
        tmp_path,
        [[_message("yes")]],
        handler=handler,
        webhook_url="https://example.com/webhooks/telegram",
    )
    assert started is False
    assert transport.sent == []


def test_polling_is_off_without_telegram_configured(tmp_path):
    config = _config(tmp_path, token=None)
    poller = TelegramPoller(config)
    assert poller.enabled() is False
    assert asyncio.run(poller.start()) is False

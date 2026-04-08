import sys
import threading
from unittest.mock import MagicMock

import pytest

# Mock the openai module if not installed so we can test the provider
if "openai" not in sys.modules:
    sys.modules["openai"] = MagicMock()

import asyncio


def test_openai_provider_calls_chat_completions():
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    calls = []

    class FakeChoice:
        class Message:
            content = "test response"

        message = Message()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello", system_prompt="Be helpful"))

    assert result == "test response"
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.4"
    messages = calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Be helpful"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hello"


def test_openai_provider_model_override():
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    calls = []

    class FakeChoice:
        class Message:
            content = "ok"

        message = Message()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hi", model="gpt-5.4-mini"))
    assert calls[0]["model"] == "gpt-5.4-mini"


def test_openai_provider_no_system_prompt():
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    calls = []

    class FakeChoice:
        class Message:
            content = "ok"

        message = Message()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hello"))

    messages = calls[0]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


def test_openai_provider_uses_asyncio_to_thread(monkeypatch):
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    to_thread_calls = []
    create_calls = []

    async def fake_to_thread(func, *args, **kwargs):
        to_thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    class FakeChoice:
        class Message:
            content = "threaded openai response"

        message = Message()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello"))

    assert result == "threaded openai response"
    assert len(to_thread_calls) == 1
    assert len(create_calls) == 1


def test_openai_provider_propagates_sdk_exceptions_from_to_thread(monkeypatch):
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    expected = RuntimeError("openai sdk failed")

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeCompletions:
        def create(self, **kwargs):
            raise expected

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
    provider._client = FakeClient()

    try:
        asyncio.run(provider.complete("hello"))
    except RuntimeError as exc:
        assert exc is expected
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_openai_provider_cancellation_stops_waiting_but_not_worker_thread():
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class FakeChoice:
        class Message:
            content = "late openai response"

        message = Message()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            started.set()
            release.wait(timeout=1)
            finished.set()
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    async def exercise():
        provider = OpenAICompatibleProvider(api_key="fake", model="gpt-5.4")
        provider._client = FakeClient()

        task = asyncio.create_task(provider.complete("hello"))
        assert await asyncio.wait_for(asyncio.to_thread(started.wait, 1), timeout=2)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert not finished.is_set()
        release.set()
        assert await asyncio.wait_for(asyncio.to_thread(finished.wait, 1), timeout=2)

    asyncio.run(exercise())

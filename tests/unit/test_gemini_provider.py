import asyncio
import threading

import pytest


def test_gemini_provider_calls_generate_content():
    from pulse.llm.gemini import GeminiProvider

    calls = []

    class FakeResponse:
        text = "gemini response"

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello", system_prompt="Be helpful"))

    assert result == "gemini response"
    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-2.5-flash"
    assert calls[0]["contents"] == "hello"
    assert calls[0]["config"].system_instruction == "Be helpful"


def test_gemini_provider_model_override():
    from pulse.llm.gemini import GeminiProvider

    calls = []

    class FakeResponse:
        text = "ok"

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hi", model="gemini-2.5-pro"))
    assert calls[0]["model"] == "gemini-2.5-pro"


def test_gemini_provider_no_system_prompt():
    from pulse.llm.gemini import GeminiProvider

    calls = []

    class FakeResponse:
        text = "ok"

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hello"))
    assert calls[0]["config"].system_instruction is None


def test_gemini_provider_uses_asyncio_to_thread(monkeypatch):
    from pulse.llm.gemini import GeminiProvider

    to_thread_calls = []
    generate_calls = []

    async def fake_to_thread(func, *args, **kwargs):
        to_thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    class FakeResponse:
        text = "threaded gemini response"

    class FakeModels:
        def generate_content(self, **kwargs):
            generate_calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello"))

    assert result == "threaded gemini response"
    assert len(to_thread_calls) == 1
    assert len(generate_calls) == 1


def test_gemini_provider_propagates_sdk_exceptions_from_to_thread(monkeypatch):
    from pulse.llm.gemini import GeminiProvider

    expected = RuntimeError("gemini sdk failed")

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeModels:
        def generate_content(self, **kwargs):
            raise expected

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
    provider._client = FakeClient()

    try:
        asyncio.run(provider.complete("hello"))
    except RuntimeError as exc:
        assert exc is expected
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_gemini_provider_cancellation_stops_waiting_but_not_worker_thread():
    from pulse.llm.gemini import GeminiProvider

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class FakeResponse:
        text = "late gemini response"

    class FakeModels:
        def generate_content(self, **kwargs):
            started.set()
            release.wait(timeout=1)
            finished.set()
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    async def exercise():
        provider = GeminiProvider(api_key="fake", model="gemini-2.5-flash")
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

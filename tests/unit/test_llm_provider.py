import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest


def test_anthropic_provider_satisfies_llm_protocol():
    from pulse.domain.llm import LLM
    from pulse.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="fake-key")
    assert hasattr(provider, "complete")


def test_anthropic_provider_calls_api(monkeypatch):
    async def exercise():
        from pulse.llm.anthropic import AnthropicProvider

        calls = []

        class FakeMessages:
            def create(self, **kwargs):
                calls.append(kwargs)

                class FakeResponse:
                    class Content:
                        text = '{"patterns": []}'

                    content = [Content()]

                return FakeResponse()

        class FakeClient:
            messages = FakeMessages()

        provider = AnthropicProvider(api_key="fake-key")
        provider._client = FakeClient()

        result = await provider.complete(
            prompt="Find patterns",
            system_prompt="You are an insight engine",
        )

        assert result == '{"patterns": []}'
        assert len(calls) == 1
        assert calls[0]["system"] == "You are an insight engine"

    asyncio.run(exercise())


def test_anthropic_provider_respects_model_override():
    with patch("anthropic.Anthropic") as MockClient:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        MockClient.return_value.messages.create.return_value = mock_response

        from pulse.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key", model="claude-sonnet-4-6")

        import asyncio

        asyncio.run(provider.complete("hello", model="claude-haiku-4-5-20251001"))

        call_kwargs = MockClient.return_value.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_anthropic_provider_uses_asyncio_to_thread(monkeypatch):
    from pulse.llm.anthropic import AnthropicProvider

    to_thread_calls = []
    create_calls = []

    async def fake_to_thread(func, *args, **kwargs):
        to_thread_calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    class FakeMessages:
        def create(self, **kwargs):
            create_calls.append(kwargs)

            class FakeResponse:
                class Content:
                    text = "threaded anthropic response"

                content = [Content()]

            return FakeResponse()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = AnthropicProvider(api_key="fake-key")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello"))

    assert result == "threaded anthropic response"
    assert len(to_thread_calls) == 1
    assert len(create_calls) == 1


def test_anthropic_provider_propagates_sdk_exceptions_from_to_thread(monkeypatch):
    from pulse.llm.anthropic import AnthropicProvider

    expected = RuntimeError("anthropic sdk failed")

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    class FakeMessages:
        def create(self, **kwargs):
            raise expected

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    provider = AnthropicProvider(api_key="fake-key")
    provider._client = FakeClient()

    try:
        asyncio.run(provider.complete("hello"))
    except RuntimeError as exc:
        assert exc is expected
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_anthropic_provider_cancellation_stops_waiting_but_not_worker_thread():
    from pulse.llm.anthropic import AnthropicProvider

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class FakeMessages:
        def create(self, **kwargs):
            started.set()
            release.wait(timeout=1)
            finished.set()

            class FakeResponse:
                class Content:
                    text = "late anthropic response"

                content = [Content()]

            return FakeResponse()

    class FakeClient:
        messages = FakeMessages()

    async def exercise():
        provider = AnthropicProvider(api_key="fake-key")
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

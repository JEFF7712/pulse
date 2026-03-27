import asyncio
from unittest.mock import MagicMock, patch


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

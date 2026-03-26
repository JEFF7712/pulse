import asyncio


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

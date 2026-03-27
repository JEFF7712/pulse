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

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-4o")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello", system_prompt="Be helpful"))

    assert result == "test response"
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-4o"
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

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-4o")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hi", model="gpt-4o-mini"))
    assert calls[0]["model"] == "gpt-4o-mini"


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

    provider = OpenAICompatibleProvider(api_key="fake", model="gpt-4o")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hello"))

    messages = calls[0]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"

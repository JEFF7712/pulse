import asyncio


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

    provider = GeminiProvider(api_key="fake", model="gemini-2.0-flash")
    provider._client = FakeClient()

    result = asyncio.run(provider.complete("hello", system_prompt="Be helpful"))

    assert result == "gemini response"
    assert len(calls) == 1
    assert calls[0]["model"] == "gemini-2.0-flash"
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

    provider = GeminiProvider(api_key="fake", model="gemini-2.0-flash")
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

    provider = GeminiProvider(api_key="fake", model="gemini-2.0-flash")
    provider._client = FakeClient()

    asyncio.run(provider.complete("hello"))
    assert calls[0]["config"].system_instruction is None

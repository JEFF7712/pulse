import sys
import types

import pytest

from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig


@pytest.fixture
def stub_openai_module(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))


def test_create_llm_provider_anthropic(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    role = LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-5-20250514")
    provider = create_llm_provider(role)

    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(provider, AnthropicProvider)


def test_create_llm_provider_openai(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    role = LLMRoleConfig(provider="openai", model="gpt-4o")
    provider = create_llm_provider(role)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_llm_provider_ollama_no_key_needed(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    role = LLMRoleConfig(
        provider="ollama",
        model="llama3",
        base_url="http://localhost:11434/v1",
    )
    provider = create_llm_provider(role)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_llm_provider_gemini(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    role = LLMRoleConfig(provider="gemini", model="gemini-2.0-flash")
    provider = create_llm_provider(role)

    from pulse.llm.gemini import GeminiProvider

    assert isinstance(provider, GeminiProvider)


def test_create_llm_provider_unknown_raises():
    from pulse.llm.factory import create_llm_provider

    role = LLMRoleConfig(provider="foo", model="bar")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm_provider(role)


def test_create_llm_provider_missing_key_raises(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    role = LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-5-20250514")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_llm_provider(role)


def test_create_providers_from_config_new_style(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(provider="openai", model="gpt-4o-mini"),
            discovery=LLMRoleConfig(
                provider="anthropic", model="claude-sonnet-4-5-20250514"
            ),
        )
    )
    summ_llm, disc_llm = create_providers_from_config(config)

    from pulse.llm.openai_compat import OpenAICompatibleProvider
    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(summ_llm, OpenAICompatibleProvider)
    assert isinstance(disc_llm, AnthropicProvider)


def test_create_providers_from_config_single_block_fallback(
    monkeypatch, stub_openai_module
):
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(provider="openai", model="gpt-4o"),
            discovery=None,
        )
    )
    summ_llm, disc_llm = create_providers_from_config(config)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(summ_llm, OpenAICompatibleProvider)
    assert isinstance(disc_llm, OpenAICompatibleProvider)


def test_create_providers_from_config_legacy_anthropic(monkeypatch):
    from pulse.llm.factory import create_providers_from_config

    config = PulseConfig(anthropic_api_key="test-key")
    summ_llm, disc_llm = create_providers_from_config(config)

    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(summ_llm, AnthropicProvider)
    assert isinstance(disc_llm, AnthropicProvider)


def test_create_providers_from_config_no_config():
    from pulse.llm.factory import create_providers_from_config

    config = PulseConfig()
    summ_llm, disc_llm = create_providers_from_config(config)
    assert summ_llm is None
    assert disc_llm is None


def test_create_corrections_provider_prefers_dedicated_role(
    monkeypatch, stub_openai_module
):
    from pulse.llm.factory import create_corrections_provider_from_config

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            corrections=LLMRoleConfig(provider="openai", model="gpt-4o-mini"),
            discovery=LLMRoleConfig(
                provider="anthropic", model="claude-sonnet-4-5-20250514"
            ),
        )
    )

    provider = create_corrections_provider_from_config(config)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_corrections_provider_falls_back_to_discovery(monkeypatch):
    from pulse.llm.factory import create_corrections_provider_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            discovery=LLMRoleConfig(
                provider="anthropic", model="claude-sonnet-4-5-20250514"
            ),
        )
    )

    provider = create_corrections_provider_from_config(config)

    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(provider, AnthropicProvider)


def test_create_corrections_provider_legacy_fallback(monkeypatch):
    from pulse.llm.factory import create_corrections_provider_from_config

    captured = {}

    class FakeAnthropicProvider:
        def __init__(self, api_key: str, model: str) -> None:
            captured["api_key"] = api_key
            captured["model"] = model

    monkeypatch.setattr("pulse.llm.anthropic.AnthropicProvider", FakeAnthropicProvider)

    config = PulseConfig(
        anthropic_api_key="test-key", discovery_model="claude-sonnet-4-6"
    )

    provider = create_corrections_provider_from_config(config)

    assert isinstance(provider, FakeAnthropicProvider)
    assert captured == {"api_key": "test-key", "model": "claude-sonnet-4-6"}


def test_create_corrections_provider_no_config_returns_none():
    from pulse.llm.factory import create_corrections_provider_from_config

    provider = create_corrections_provider_from_config(PulseConfig())

    assert provider is None

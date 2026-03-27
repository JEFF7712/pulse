import pytest

from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig


def test_create_llm_provider_anthropic(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    role = LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-5-20250514")
    provider = create_llm_provider(role)

    from pulse.llm.anthropic import AnthropicProvider
    assert isinstance(provider, AnthropicProvider)


def test_create_llm_provider_openai(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    role = LLMRoleConfig(provider="openai", model="gpt-4o")
    provider = create_llm_provider(role)

    from pulse.llm.openai_compat import OpenAICompatibleProvider
    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_llm_provider_ollama_no_key_needed(monkeypatch):
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


def test_create_providers_from_config_new_style(monkeypatch):
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(provider="openai", model="gpt-4o-mini"),
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-5-20250514"),
        )
    )
    summ_llm, disc_llm = create_providers_from_config(config)

    from pulse.llm.openai_compat import OpenAICompatibleProvider
    from pulse.llm.anthropic import AnthropicProvider
    assert isinstance(summ_llm, OpenAICompatibleProvider)
    assert isinstance(disc_llm, AnthropicProvider)


def test_create_providers_from_config_single_block_fallback(monkeypatch):
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

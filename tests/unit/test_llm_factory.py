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
    role = LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6")
    provider = create_llm_provider(role)

    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(provider, AnthropicProvider)


def test_create_llm_provider_openai(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    role = LLMRoleConfig(provider="openai", model="gpt-5.4")
    provider = create_llm_provider(role)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_llm_provider_ollama_no_key_needed(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    role = LLMRoleConfig(
        provider="ollama",
        model="llama3.3",
        base_url="http://localhost:11434/v1",
    )
    provider = create_llm_provider(role)

    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_llm_provider_gemini(monkeypatch):
    from pulse.llm.factory import create_llm_provider

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    role = LLMRoleConfig(provider="gemini", model="gemini-2.5-flash")
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
    role = LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_llm_provider(role)


def test_create_providers_from_config_new_style(monkeypatch, stub_openai_module):
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(provider="openai", model="gpt-5.4-mini"),
            discovery=LLMRoleConfig(
                provider="anthropic", model="claude-sonnet-4-6"
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
            summarization=LLMRoleConfig(provider="openai", model="gpt-5.4"),
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
            corrections=LLMRoleConfig(provider="openai", model="gpt-5.4-mini"),
            discovery=LLMRoleConfig(
                provider="anthropic", model="claude-sonnet-4-6"
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
                provider="anthropic", model="claude-sonnet-4-6"
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

    config = PulseConfig(anthropic_api_key="test-key")

    provider = create_corrections_provider_from_config(config)

    assert isinstance(provider, FakeAnthropicProvider)
    assert captured == {"api_key": "test-key", "model": "claude-sonnet-4-6"}


def test_create_corrections_provider_no_config_returns_none():
    from pulse.llm.factory import create_corrections_provider_from_config

    provider = create_corrections_provider_from_config(PulseConfig())

    assert provider is None


def test_summarization_model_for_digest_uses_summarization_role() -> None:
    from pulse.llm.factory import summarization_model_for_digest

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(provider="openai", model="gpt-5.4-mini"),
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        )
    )
    assert summarization_model_for_digest(config) == "gpt-5.4-mini"


def test_summarization_model_for_digest_reuses_discovery_when_summarization_omitted() -> None:
    from pulse.llm.factory import summarization_model_for_digest

    config = PulseConfig(
        llm=LLMConfig(
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        )
    )
    assert summarization_model_for_digest(config) == "claude-sonnet-4-6"


def test_summarization_model_for_digest_legacy_uses_fixed_default() -> None:
    from pulse.llm.factory import (
        LEGACY_ANTHROPIC_SUMMARIZATION_MODEL,
        summarization_model_for_digest,
    )

    config = PulseConfig()
    assert summarization_model_for_digest(config) == LEGACY_ANTHROPIC_SUMMARIZATION_MODEL


def test_discovery_model_for_discovery_legacy_uses_fixed_default() -> None:
    from pulse.llm.factory import (
        LEGACY_ANTHROPIC_DISCOVERY_MODEL,
        discovery_model_for_discovery,
    )

    config = PulseConfig()
    assert discovery_model_for_discovery(config) == LEGACY_ANTHROPIC_DISCOVERY_MODEL


def test_discovery_model_for_discovery_uses_role() -> None:
    from pulse.llm.factory import discovery_model_for_discovery

    config = PulseConfig(
        llm=LLMConfig(
            discovery=LLMRoleConfig(provider="openai", model="gpt-5.4"),
        )
    )
    assert discovery_model_for_discovery(config) == "gpt-5.4"


def test_effective_llm_role_configs_requires_provider() -> None:
    from pulse.llm.factory import effective_llm_role_configs

    config = PulseConfig(
        llm=LLMConfig(summarization=LLMRoleConfig(model="some-model"))
    )
    with pytest.raises(ValueError, match="missing provider"):
        effective_llm_role_configs(config)


def test_llm_base_url_not_inherited_by_anthropic_role() -> None:
    from pulse.llm.factory import effective_llm_role_configs

    config = PulseConfig(
        llm=LLMConfig(
            provider="ollama",
            base_url="http://localhost:11434/v1",
            summarization=LLMRoleConfig(model="llama3"),
            discovery=LLMRoleConfig(provider="anthropic", model="claude-sonnet-4-6"),
        )
    )
    summ, disc = effective_llm_role_configs(config)
    assert summ is not None and disc is not None
    assert summ.base_url == "http://localhost:11434/v1"
    assert disc.base_url is None


def test_create_providers_from_config_shared_anthropic_provider_two_models(
    monkeypatch,
) -> None:
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    config = PulseConfig(
        llm=LLMConfig(
            provider="anthropic",
            summarization=LLMRoleConfig(model="claude-haiku-4-5-20251001"),
            discovery=LLMRoleConfig(model="claude-opus-4-6"),
        )
    )
    summ_llm, disc_llm = create_providers_from_config(config)
    from pulse.llm.anthropic import AnthropicProvider

    assert isinstance(summ_llm, AnthropicProvider)
    assert isinstance(disc_llm, AnthropicProvider)
    assert summ_llm._model == "claude-haiku-4-5-20251001"
    assert disc_llm._model == "claude-opus-4-6"


def test_create_providers_from_config_shared_openai_provider_two_models(
    monkeypatch,
    stub_openai_module,
) -> None:
    from pulse.llm.factory import create_providers_from_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    config = PulseConfig(
        llm=LLMConfig(
            provider="openai",
            summarization=LLMRoleConfig(model="gpt-5.4-nano"),
            discovery=LLMRoleConfig(model="gpt-5.4"),
        )
    )
    summ_llm, disc_llm = create_providers_from_config(config)
    from pulse.llm.openai_compat import OpenAICompatibleProvider

    assert isinstance(summ_llm, OpenAICompatibleProvider)
    assert isinstance(disc_llm, OpenAICompatibleProvider)
    assert summ_llm._model == "gpt-5.4-nano"
    assert disc_llm._model == "gpt-5.4"

"""LLM provider factory — creates providers from config."""
from __future__ import annotations

import os

from pulse.app.config import LLMRoleConfig, PulseConfig

_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "OPENAI_API_KEY",
}

_SUPPORTED_PROVIDERS = set(_API_KEY_ENV.keys())


def create_llm_provider(role_config: LLMRoleConfig):
    """Create an LLM provider instance from a role config."""
    provider = role_config.provider

    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_PROVIDERS))}"
        )

    env_var = _API_KEY_ENV[provider]
    api_key = os.environ.get(env_var)

    # Ollama doesn't need a real API key
    if provider == "ollama" and not api_key:
        api_key = "ollama"

    if not api_key:
        raise ValueError(
            f"{provider.title()} provider requires {env_var} environment variable"
        )

    if provider == "anthropic":
        from pulse.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=role_config.model)

    if provider in ("openai", "ollama"):
        from pulse.llm.openai_compat import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            api_key=api_key,
            model=role_config.model,
            base_url=role_config.base_url,
        )

    if provider == "gemini":
        from pulse.llm.gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=role_config.model)

    raise ValueError(f"Unknown LLM provider: '{provider}'")


def create_providers_from_config(config: PulseConfig) -> tuple:
    """Returns (summarization_llm, discovery_llm) from config.

    Resolution order:
    1. config.llm (new-style per-role config)
    2. config.anthropic_api_key (legacy single-provider)
    3. (None, None) if nothing configured
    """
    if config.llm is not None:
        summ_config = config.llm.summarization
        disc_config = config.llm.discovery

        # Single-block fallback: if only one role is configured, use it for both
        if summ_config and not disc_config:
            disc_config = summ_config
        elif disc_config and not summ_config:
            summ_config = disc_config

        if not summ_config and not disc_config:
            return (None, None)

        summ_llm = create_llm_provider(summ_config) if summ_config else None
        disc_llm = create_llm_provider(disc_config) if disc_config else None
        return (summ_llm, disc_llm)

    # Legacy: anthropic_api_key
    if config.anthropic_api_key:
        from pulse.llm.anthropic import AnthropicProvider
        summ_llm = AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=config.summarization_model,
        )
        disc_llm = AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=config.discovery_model,
        )
        return (summ_llm, disc_llm)

    return (None, None)

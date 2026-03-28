"""LLM provider factory — creates providers from config."""

from __future__ import annotations

import os

from pulse.app.config import LLMConfig, LLMRoleConfig, PulseConfig
from pulse.domain.llm import LLM

_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "OPENAI_API_KEY",
}

_SUPPORTED_PROVIDERS = set(_API_KEY_ENV.keys())

# Used only when `PULSE_ANTHROPIC_API_KEY` / `anthropic_api_key` is set without `[llm.*]`.
LEGACY_ANTHROPIC_SUMMARIZATION_MODEL = "claude-haiku-4-5-20251001"
LEGACY_ANTHROPIC_DISCOVERY_MODEL = "claude-sonnet-4-6"


def _resolve_role(llm: LLMConfig, role: LLMRoleConfig | None) -> LLMRoleConfig | None:
    """Apply `[llm]`-level defaults to a role block."""
    if role is None:
        return None
    provider = role.provider or llm.provider
    if not provider:
        raise ValueError(
            "LLM role is missing provider: set [llm] provider in pulse.toml or "
            "provider on [llm.summarization] / [llm.discovery] / [llm.corrections]."
        )
    if role.base_url is not None:
        base_url = role.base_url
    elif provider in ("openai", "ollama") and llm.base_url is not None:
        base_url = llm.base_url
    else:
        base_url = None
    return LLMRoleConfig(provider=provider, model=role.model, base_url=base_url)


def create_llm_provider(role_config: LLMRoleConfig) -> LLM:
    """Create an LLM provider instance from a role config."""
    provider = role_config.provider
    if not provider:
        raise ValueError(
            "create_llm_provider requires a resolved role with `provider` set"
        )

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

    # provider == "gemini"
    from pulse.llm.gemini import GeminiProvider

    return GeminiProvider(api_key=api_key, model=role_config.model)


def create_corrections_provider_from_config(config: PulseConfig) -> LLM | None:
    """Return the corrections LLM from config using corrections-specific fallback."""
    if config.llm is not None:
        llm = config.llm
        if llm.corrections is not None:
            resolved = _resolve_role(llm, llm.corrections)
            if resolved is not None:
                return create_llm_provider(resolved)

        _, disc_resolved = effective_llm_role_configs(config)
        if disc_resolved is not None:
            return create_llm_provider(disc_resolved)

    if config.anthropic_api_key:
        from pulse.llm.anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=LEGACY_ANTHROPIC_DISCOVERY_MODEL,
        )

    return None


def effective_llm_role_configs(
    config: PulseConfig,
) -> tuple[LLMRoleConfig | None, LLMRoleConfig | None]:
    """Return (summarization, discovery) after single-block fallback and `[llm]` defaults."""
    if config.llm is None:
        return (None, None)
    llm = config.llm
    summ_config = llm.summarization
    disc_config = llm.discovery
    if summ_config and not disc_config:
        disc_config = summ_config
    elif disc_config and not summ_config:
        summ_config = disc_config

    if summ_config is disc_config and summ_config is not None:
        resolved = _resolve_role(llm, summ_config)
        return (resolved, resolved)

    return (
        _resolve_role(llm, summ_config),
        _resolve_role(llm, disc_config),
    )


def summarization_model_for_digest(config: PulseConfig) -> str:
    """Model id passed to SourceSummarizer; matches the active summarization role."""
    summ_config, _ = effective_llm_role_configs(config)
    if summ_config is not None:
        return summ_config.model
    return LEGACY_ANTHROPIC_SUMMARIZATION_MODEL


def discovery_model_for_discovery(config: PulseConfig) -> str:
    """Discovery LLM model id; matches `[llm.discovery]` or legacy Anthropic default."""
    _, disc_config = effective_llm_role_configs(config)
    if disc_config is not None:
        return disc_config.model
    return LEGACY_ANTHROPIC_DISCOVERY_MODEL


def create_providers_from_config(config: PulseConfig) -> tuple[LLM | None, LLM | None]:
    """Returns (summarization_llm, discovery_llm) from config.

    Resolution order:
    1. config.llm (new-style per-role config)
    2. config.anthropic_api_key (legacy single-provider)
    3. (None, None) if nothing configured
    """
    if config.llm is not None:
        summ_config, disc_config = effective_llm_role_configs(config)

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
            model=LEGACY_ANTHROPIC_SUMMARIZATION_MODEL,
        )
        disc_llm = AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=LEGACY_ANTHROPIC_DISCOVERY_MODEL,
        )
        return (summ_llm, disc_llm)

    return (None, None)

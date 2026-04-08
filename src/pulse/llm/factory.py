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

_CONFIG_API_KEY_FIELD = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "ollama": "openai_api_key",
}


def _api_key_from_pulse_config(provider: str, pulse_config: PulseConfig | None) -> str | None:
    if pulse_config is None:
        return None
    field = _CONFIG_API_KEY_FIELD.get(provider)
    if not field:
        return None
    raw = getattr(pulse_config, field, None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


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


def create_llm_provider(
    role_config: LLMRoleConfig,
    *,
    pulse_config: PulseConfig | None = None,
) -> LLM:
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
    api_key = _api_key_from_pulse_config(provider, pulse_config)
    if not api_key:
        api_key = os.environ.get(env_var)

    # Ollama doesn't need a real API key
    if provider == "ollama" and not api_key:
        api_key = "ollama"

    if not api_key:
        raise ValueError(
            f"{provider.title()} provider requires {env_var} or the matching key in pulse.toml"
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
                return create_llm_provider(resolved, pulse_config=config)

        _, disc_resolved = effective_llm_role_configs(config)
        if disc_resolved is not None:
            return create_llm_provider(disc_resolved, pulse_config=config)

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


def summarization_model_for_source_summaries(config: PulseConfig) -> str | None:
    """Model id for SourceSummarizer when a summarization role resolves; else ``None``."""
    summ_config, _ = effective_llm_role_configs(config)
    if summ_config is None:
        return None
    return summ_config.model


def discovery_model_for_discovery(config: PulseConfig) -> str | None:
    """Model id for discovery when a discovery role resolves; else ``None``."""
    _, disc_config = effective_llm_role_configs(config)
    if disc_config is None:
        return None
    return disc_config.model


def create_providers_from_config(config: PulseConfig) -> tuple[LLM | None, LLM | None]:
    """Return ``(summarization_llm, discovery_llm)`` from ``[llm.*]`` roles, or ``(None, None)``."""
    if config.llm is None:
        return (None, None)

    summ_config, disc_config = effective_llm_role_configs(config)
    if not summ_config and not disc_config:
        return (None, None)

    summ_llm = (
        create_llm_provider(summ_config, pulse_config=config) if summ_config else None
    )
    disc_llm = (
        create_llm_provider(disc_config, pulse_config=config) if disc_config else None
    )
    return (summ_llm, disc_llm)

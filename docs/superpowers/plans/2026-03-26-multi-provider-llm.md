# Multi-Provider LLM Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenAI-compatible and Gemini LLM providers with per-role config so users can mix providers for summarization vs discovery.

**Architecture:** New `OpenAICompatibleProvider` and `GeminiProvider` classes satisfy the existing `LLM` protocol. A `create_providers_from_config` factory reads `[llm.summarization]` and `[llm.discovery]` TOML blocks (falling back to legacy `anthropic_api_key` config). All call sites switch from hardcoded Anthropic instantiation to the factory.

**Tech Stack:** Python 3.12+, `openai` SDK (optional), `google-genai` SDK (optional), existing `anthropic` SDK, Pydantic config

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/pulse/app/config.py` | Modified — adds `LLMRoleConfig`, `LLMConfig`, `llm` field to `PulseConfig` |
| `src/pulse/llm/openai_compat.py` | New — `OpenAICompatibleProvider` using `openai` SDK |
| `src/pulse/llm/gemini.py` | New — `GeminiProvider` using `google-genai` SDK |
| `src/pulse/llm/factory.py` | New — `create_llm_provider`, `create_providers_from_config` |
| `src/pulse/jobs/scheduler.py` | Modified — uses factory instead of hardcoded Anthropic |
| `src/pulse/app/cli.py` | Modified — uses factory instead of hardcoded Anthropic |
| `src/pulse/app/home_actions.py` | Modified — uses factory instead of hardcoded Anthropic |
| `pyproject.toml` | Modified — optional dependencies for openai, gemini |
| `pulse.toml.example` | Modified — example LLM config |

---

### Task 1: Add LLM config models to PulseConfig

**Files:**
- Modify: `src/pulse/app/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/unit/test_config.py

def test_pulse_config_parses_llm_config():
    from pulse.app.config import PulseConfig, LLMRoleConfig, LLMConfig

    config = PulseConfig(
        llm=LLMConfig(
            summarization=LLMRoleConfig(
                provider="ollama",
                model="llama3",
                base_url="http://localhost:11434/v1",
            ),
            discovery=LLMRoleConfig(
                provider="anthropic",
                model="claude-sonnet-4-5-20250514",
            ),
        )
    )
    assert config.llm.summarization.provider == "ollama"
    assert config.llm.summarization.model == "llama3"
    assert config.llm.summarization.base_url == "http://localhost:11434/v1"
    assert config.llm.discovery.provider == "anthropic"
    assert config.llm.discovery.model == "claude-sonnet-4-5-20250514"
    assert config.llm.discovery.base_url is None


def test_pulse_config_llm_defaults_to_none():
    config = PulseConfig()
    assert config.llm is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py::test_pulse_config_parses_llm_config -v`
Expected: FAIL — `LLMRoleConfig` not found

- [ ] **Step 3: Write minimal implementation**

```python
# src/pulse/app/config.py
from pydantic import BaseModel, ConfigDict


class ConnectorConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    poll_interval: str = "15m"


class LLMRoleConfig(BaseModel):
    provider: str  # "anthropic" | "openai" | "gemini" | "ollama"
    model: str
    base_url: str | None = None


class LLMConfig(BaseModel):
    summarization: LLMRoleConfig | None = None
    discovery: LLMRoleConfig | None = None


class PulseConfig(BaseModel):
    database_path: str = "data/pulse.db"
    vault_path: str = "Pulse-Vault"
    timezone: str = "UTC"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    anthropic_api_key: str | None = None
    summarization_model: str = "claude-haiku-4-5-20251001"
    discovery_model: str = "claude-sonnet-4-5-20250514"
    llm: LLMConfig | None = None
    connectors: dict[str, ConnectorConfig] = {}


# Backward compatibility alias
Settings = PulseConfig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/config.py tests/unit/test_config.py
git commit -m "feat: add LLMRoleConfig and LLMConfig to PulseConfig"
```

---

### Task 2: Build OpenAICompatibleProvider

**Files:**
- Create: `src/pulse/llm/openai_compat.py`
- Create: `tests/unit/test_openai_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_openai_provider.py
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
    # Should have system + user messages
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_openai_provider.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/llm/openai_compat.py
"""OpenAI-compatible LLM provider — covers OpenAI, Groq, Together, Mistral, Ollama, vLLM."""
from __future__ import annotations

try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "OpenAI provider requires the 'openai' package. "
        "Install with: pip install 'pulse[openai]'"
    )


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=model or self._model,
            messages=messages,
            max_tokens=4096,
        )
        return response.choices[0].message.content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_openai_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/llm/openai_compat.py tests/unit/test_openai_provider.py
git commit -m "feat: add OpenAI-compatible LLM provider"
```

---

### Task 3: Build GeminiProvider

**Files:**
- Create: `src/pulse/llm/gemini.py`
- Create: `tests/unit/test_gemini_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_gemini_provider.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gemini_provider.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/llm/gemini.py
"""Google Gemini LLM provider."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from google.genai import Client
    from google.genai.types import GenerateContentConfig
except ImportError:
    raise ImportError(
        "Gemini provider requires the 'google-genai' package. "
        "Install with: pip install 'pulse[gemini]'"
    )


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = Client(api_key=api_key)
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        config = GenerateContentConfig(
            system_instruction=system_prompt,
        )
        response = self._client.models.generate_content(
            model=model or self._model,
            contents=prompt,
            config=config,
        )
        return response.text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gemini_provider.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/llm/gemini.py tests/unit/test_gemini_provider.py
git commit -m "feat: add Google Gemini LLM provider"
```

---

### Task 4: Build provider factory

**Files:**
- Create: `src/pulse/llm/factory.py`
- Create: `tests/unit/test_llm_factory.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_llm_factory.py
import os

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

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm_factory.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/pulse/llm/factory.py
"""LLM provider factory — creates providers from config."""
from __future__ import annotations

import os

from pulse.app.config import LLMRoleConfig, PulseConfig

_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama": "OPENAI_API_KEY",  # Ollama uses OpenAI-compat API
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_llm_factory.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/llm/factory.py tests/unit/test_llm_factory.py
git commit -m "feat: add LLM provider factory with multi-provider and legacy support"
```

---

### Task 5: Wire factory into scheduler

**Files:**
- Modify: `src/pulse/jobs/scheduler.py`

- [ ] **Step 1: Update `_make_daily_digest_job`**

Replace the current `_make_daily_digest_job` function (lines 151-167) in `src/pulse/jobs/scheduler.py` with:

```python
def _make_daily_digest_job(config):
    async def job():
        day = _resolve_current_day(config)

        from pulse.llm.factory import create_providers_from_config
        summ_llm, _ = create_providers_from_config(config)

        return await run_daily_digest_job(
            day=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=summ_llm,
        )
    return job
```

- [ ] **Step 2: Update `_make_discovery_job`**

Replace the current `_make_discovery_job` function (lines 196-223) with:

```python
def _make_discovery_job(cadence, config):
    async def job():
        from pulse.jobs.runners import run_discovery_job
        from pulse.llm.factory import create_providers_from_config

        day = _resolve_current_day(config)
        _, disc_llm = create_providers_from_config(config)

        if disc_llm is None:
            return JobResult(
                status="skipped",
                detail=f"Discovery ({cadence}) skipped: no LLM provider configured",
            )

        channel = _build_telegram_channel(config)
        return await run_discovery_job(
            cadence=cadence,
            target_date=day,
            database_path=config.database_path,
            vault_path=config.vault_path,
            llm=disc_llm,
            notification_channel=channel,
        )
    return job
```

- [ ] **Step 3: Remove unused import**

Remove the `from pulse.llm.anthropic import AnthropicProvider` import that was inside `_make_discovery_job` (it's now handled by the factory). Also remove the `summarization_model` and `discovery_model` kwargs from `run_daily_digest_job` and `run_discovery_job` calls — the model is now baked into the provider instances.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/jobs/scheduler.py
git commit -m "refactor: wire LLM factory into scheduler jobs"
```

---

### Task 6: Wire factory into CLI commands

**Files:**
- Modify: `src/pulse/app/cli.py`

- [ ] **Step 1: Update `_discover` function**

In `src/pulse/app/cli.py`, find the `_discover` function (around line 591). Replace the Anthropic-specific code:

```python
# Old (remove):
from pulse.llm.anthropic import AnthropicProvider
...
if not config.anthropic_api_key:
    print("Error: PULSE_ANTHROPIC_API_KEY must be set for discovery.")
    sys.exit(1)
llm = AnthropicProvider(api_key=config.anthropic_api_key)
```

With:

```python
# New:
from pulse.llm.factory import create_providers_from_config
...
_, disc_llm = create_providers_from_config(config)
if disc_llm is None:
    print("Error: No LLM provider configured. Set [llm.discovery] in pulse.toml or PULSE_ANTHROPIC_API_KEY.")
    sys.exit(1)
```

Then use `disc_llm` instead of `llm` in the `run_discovery_job` call, and remove the `summarization_model`/`discovery_model` kwargs.

- [ ] **Step 2: Update `_init` function's discovery block**

In the `_init` function (around line 511), replace:

```python
# Old:
if config.anthropic_api_key:
    ...
    from pulse.llm.anthropic import AnthropicProvider
    llm = AnthropicProvider(api_key=config.anthropic_api_key)
```

With:

```python
# New:
from pulse.llm.factory import create_providers_from_config
_, disc_llm = create_providers_from_config(config)
if disc_llm is not None:
    print("\n--- Running Initial Discovery ---")
    ...
    result = asyncio.run(run_discovery_job(
        cadence="weekly",
        target_date=today,
        database_path=config.database_path,
        vault_path=config.vault_path,
        llm=disc_llm,
        notification_channel=channel,
    ))
    print(f"  {result.detail}")
else:
    print("\nSkipping discovery (no LLM provider configured)")
```

- [ ] **Step 3: Update `_digest` function**

In `_digest` (around line 571), add LLM support:

```python
from pulse.llm.factory import create_providers_from_config
summ_llm, _ = create_providers_from_config(config)

result = asyncio.run(run_daily_digest_job(
    day=target,
    database_path=config.database_path,
    vault_path=config.vault_path,
    llm=summ_llm,
))
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pulse/app/cli.py
git commit -m "refactor: wire LLM factory into CLI commands"
```

---

### Task 7: Wire factory into home_actions

**Files:**
- Modify: `src/pulse/app/home_actions.py`

- [ ] **Step 1: Update `run_discovery_action`**

In `src/pulse/app/home_actions.py`, replace the Anthropic-specific block in `run_discovery_action` (around line 93):

```python
# Old:
async def run_discovery_action(settings: PulseConfig) -> ActionResult:
    if not settings.anthropic_api_key:
        return ActionResult(query_key="error", token="discovery-not-configured")

    from pulse.llm.anthropic import AnthropicProvider
    ...
    llm=AnthropicProvider(api_key=settings.anthropic_api_key),
```

With:

```python
# New:
async def run_discovery_action(settings: PulseConfig) -> ActionResult:
    from pulse.llm.factory import create_providers_from_config

    _, disc_llm = create_providers_from_config(settings)
    if disc_llm is None:
        return ActionResult(query_key="error", token="discovery-not-configured")

    target_day = _resolve_current_day(settings)
    notification_channel = _build_telegram_channel(settings)
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        await run_aggregation_job(day=target_day, database_path=settings.database_path)
        await run_discovery_job(
            cadence="daily",
            target_date=target_day,
            database_path=settings.database_path,
            vault_path=settings.vault_path,
            llm=disc_llm,
            notification_channel=notification_channel,
        )
    except Exception:
        logger.exception("Discovery action failed")
        return ActionResult(query_key="error", token="discovery-failed")

    return ActionResult(query_key="notice", token="discovery-complete")
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/pulse/app/home_actions.py
git commit -m "refactor: wire LLM factory into home actions"
```

---

### Task 8: Add optional dependencies and update example config

**Files:**
- Modify: `pyproject.toml`
- Modify: `pulse.toml.example`

- [ ] **Step 1: Add optional dependencies to pyproject.toml**

Add after the `[project.scripts]` section:

```toml
[project.optional-dependencies]
openai = ["openai>=1.0"]
gemini = ["google-genai>=1.0"]
all-llm = ["openai>=1.0", "google-genai>=1.0"]
```

- [ ] **Step 2: Update pulse.toml.example**

Replace the contents of `pulse.toml.example` with:

```toml
# Pulse connector configuration.
# Copy to pulse.toml and adjust to your setup.
# Secrets (API keys, tokens) go in .env, not here.

[connectors.gmail]
enabled = true
poll_interval = "15m"

[connectors.calendar]
enabled = true
poll_interval = "30m"

[connectors.youtube]
enabled = true
poll_interval = "1h"

[connectors.spotify]
enabled = false
poll_interval = "30m"
supplementary_interval = "6h"

[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"  # or "firefox"

# --- LLM Configuration ---
# Configure providers for summarization (digest narratives) and
# discovery (cross-source pattern detection) independently.
#
# Supported providers: anthropic, openai, gemini, ollama
# API keys are read from environment variables:
#   ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY
#
# If only one role is configured, it is used for both.

# [llm.summarization]
# provider = "ollama"
# model = "llama3"
# base_url = "http://localhost:11434/v1"

# [llm.discovery]
# provider = "anthropic"
# model = "claude-sonnet-4-5-20250514"

# --- Legacy (still works) ---
# If you just want Anthropic for everything, set PULSE_ANTHROPIC_API_KEY
# in .env and skip the [llm] section entirely.
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml pulse.toml.example
git commit -m "feat: add optional LLM dependencies and update example config"
```

---

### Task 9: Run full test suite and verify end-to-end

**Files:**
- No new files

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from pulse.llm.factory import create_providers_from_config; print('Factory OK')"`
Expected: `Factory OK`

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git add -A
git commit -m "feat: complete multi-provider LLM support"
```

---

## Summary

| Task | Component | What it builds |
|------|-----------|---------------|
| 1 | PulseConfig | `LLMRoleConfig`, `LLMConfig`, `llm` field |
| 2 | OpenAICompatibleProvider | OpenAI/Groq/Together/Mistral/Ollama/vLLM support |
| 3 | GeminiProvider | Google Gemini support |
| 4 | Factory | `create_llm_provider`, `create_providers_from_config` |
| 5 | Scheduler | Wire factory into scheduled jobs |
| 6 | CLI | Wire factory into CLI commands |
| 7 | Home Actions | Wire factory into home actions |
| 8 | Dependencies | Optional deps in pyproject.toml, example config |
| 9 | Integration | Full test suite verification |

# Multi-Provider LLM Support

**Date:** 2026-03-26
**Status:** Approved

## Problem

Pulse is hardcoded to Anthropic. Users who want to use OpenAI, Gemini, local models (Ollama), or other providers cannot. The summarization and discovery roles have different cost/quality tradeoffs, so users should be able to mix providers — e.g., cheap local model for summarization, powerful cloud model for discovery.

## Solution

Add an OpenAI-compatible provider (covers OpenAI, Groq, Together, Mistral, Ollama, vLLM, and any OpenAI-API-compatible endpoint) and a Google Gemini provider. Introduce per-role LLM configuration so summarization and discovery can use different providers and models independently.

---

## Config Format

### New format (`pulse.toml`)

```toml
[llm.summarization]
provider = "ollama"
model = "llama3"
base_url = "http://localhost:11434/v1"

[llm.discovery]
provider = "anthropic"
model = "claude-sonnet-4-5-20250514"
```

### Config model

```python
class LLMRoleConfig(BaseModel):
    provider: str  # "anthropic" | "openai" | "gemini" | "ollama"
    model: str
    base_url: str | None = None  # required for ollama, optional for openai (custom endpoint)

class LLMConfig(BaseModel):
    summarization: LLMRoleConfig | None = None
    discovery: LLMRoleConfig | None = None
```

`PulseConfig` gains `llm: LLMConfig | None = None`.

### API keys

Read from environment variables by provider name convention:
- `ANTHROPIC_API_KEY` for `provider = "anthropic"`
- `OPENAI_API_KEY` for `provider = "openai"` and `provider = "ollama"` (Ollama ignores it but the SDK requires one)
- `GEMINI_API_KEY` for `provider = "gemini"`

No API keys in config files. The `ollama` provider sets `api_key = "ollama"` as a dummy value when `OPENAI_API_KEY` is not set.

### Backward compatibility

The existing fields (`anthropic_api_key`, `summarization_model`, `discovery_model`) continue to work. If `llm` is not configured but `anthropic_api_key` is set, behavior is identical to today. If both are present, `llm` takes precedence.

### Single-block shorthand

If only `[llm.summarization]` is configured, it's used for both roles. Same if only `[llm.discovery]` is configured. This avoids duplication when using one provider for everything.

---

## Provider Implementations

### OpenAICompatibleProvider (`src/pulse/llm/openai_compat.py`)

Uses the `openai` Python SDK with configurable `base_url`.

```python
class OpenAICompatibleProvider:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        ...

    async def complete(self, prompt: str, *, system_prompt: str | None = None, model: str | None = None) -> str:
        ...
```

- Uses `openai.OpenAI(api_key=..., base_url=...)` for sync client (the SDK handles async internally when needed, but our protocol is async-def with sync SDK calls — same pattern as AnthropicProvider)
- Maps `system_prompt` to the `system` message role
- Maps `prompt` to the `user` message role
- Returns `response.choices[0].message.content`

Covers: OpenAI (default base_url), Groq, Together, Mistral, Ollama (`http://localhost:11434/v1`), vLLM, any OpenAI-compatible endpoint.

### GeminiProvider (`src/pulse/llm/gemini.py`)

Uses the `google-genai` SDK.

```python
class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        ...

    async def complete(self, prompt: str, *, system_prompt: str | None = None, model: str | None = None) -> str:
        ...
```

- Uses `google.genai.Client(api_key=...)`
- Calls `client.models.generate_content(model=..., contents=..., config=GenerateContentConfig(system_instruction=...))`
- Returns `response.text`

### AnthropicProvider (existing, unchanged)

Already satisfies the `LLM` protocol with `model` parameter support. No changes needed.

---

## Provider Factory (`src/pulse/llm/factory.py`)

```python
def create_llm_provider(role_config: LLMRoleConfig) -> LLM:
    """Create an LLM provider from a role config. Raises on missing deps or keys."""
```

- Reads API key from environment by provider convention
- Instantiates the right provider class
- Raises `ImportError` with install instructions if optional dependency is missing
- Raises `ValueError` if required API key is not set (except ollama, which uses a dummy key)

Also:

```python
def create_providers_from_config(config: PulseConfig) -> tuple[LLM | None, LLM | None]:
    """Returns (summarization_llm, discovery_llm) from config. Handles backward compat."""
```

This handles the full resolution logic:
1. If `config.llm` is set, use it (with single-block fallback)
2. Else if `config.anthropic_api_key` is set, use legacy Anthropic config
3. Else return (None, None)

---

## Wiring Changes

### Call sites to update

All places that currently do `if config.anthropic_api_key: llm = AnthropicProvider(...)` switch to using `create_providers_from_config`:

- `src/pulse/jobs/scheduler.py` — `_make_daily_digest_job` and `_make_discovery_job`
- `src/pulse/app/cli.py` — `discover` and `digest` commands
- `src/pulse/app/home_actions.py` — discovery trigger

The summarization LLM is passed to digest jobs. The discovery LLM is passed to discovery jobs. Each already has its model baked in from config, so the `model` override on `complete()` is no longer needed for new-style config (but remains functional for backward compatibility).

### Config loader

`config_loader.py` needs to handle the nested `[llm.summarization]` and `[llm.discovery]` TOML tables. The current loader passes raw TOML dict to Pydantic, which already handles nested models — no parsing changes needed, just the config model additions.

---

## Dependencies

- `openai` — added as optional dependency in `pyproject.toml` under `[project.optional-dependencies]`
- `google-genai` — added as optional dependency
- `anthropic` — stays as core dependency (already installed)

```toml
[project.optional-dependencies]
openai = ["openai>=1.0"]
gemini = ["google-genai>=1.0"]
all-llm = ["openai>=1.0", "google-genai>=1.0"]
```

Providers import their SDK lazily and raise a clear error if not installed.

---

## File Changes

### New files
- `src/pulse/llm/openai_compat.py` — `OpenAICompatibleProvider`
- `src/pulse/llm/gemini.py` — `GeminiProvider`
- `src/pulse/llm/factory.py` — `create_llm_provider`, `create_providers_from_config`
- `tests/unit/test_openai_provider.py`
- `tests/unit/test_gemini_provider.py`
- `tests/unit/test_llm_factory.py`

### Modified files
- `src/pulse/app/config.py` — Add `LLMRoleConfig`, `LLMConfig`, and `llm` field to `PulseConfig`
- `src/pulse/jobs/scheduler.py` — Use `create_providers_from_config`
- `src/pulse/app/cli.py` — Use `create_providers_from_config`
- `src/pulse/app/home_actions.py` — Use `create_providers_from_config`
- `pyproject.toml` — Add optional dependencies
- `pulse.toml.example` — Add example LLM config

### Test updates
- `tests/unit/test_config.py` — Test new LLM config parsing
- `tests/unit/test_llm_provider.py` — Existing Anthropic tests unchanged

---

## Error Handling

- Missing optional dependency: `ImportError("OpenAI provider requires the 'openai' package. Install with: pip install pulse[openai]")`
- Missing API key: `ValueError("Anthropic provider requires ANTHROPIC_API_KEY environment variable")`
- Invalid provider name: `ValueError("Unknown LLM provider: 'foo'. Supported: anthropic, openai, gemini, ollama")`
- LLM call failure: Providers let SDK exceptions propagate (existing behavior)

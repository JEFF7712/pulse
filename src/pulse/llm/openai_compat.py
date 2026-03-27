"""OpenAI-compatible LLM provider — covers OpenAI, Groq, Together, Mistral, Ollama, vLLM."""
from __future__ import annotations


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. "
                "Install with: pip install 'pulse[openai]'"
            )
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

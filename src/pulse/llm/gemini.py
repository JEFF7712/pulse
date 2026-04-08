"""Google Gemini LLM provider."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class _GeminiConfig:
    """Lightweight config for when google-genai is not installed."""

    system_instruction: str | None = None


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        try:
            from google.genai import Client

            self._client = Client(api_key=api_key)
        except ImportError:
            # Allow construction to succeed; tests will replace _client
            self._client = None
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        try:
            from google.genai.types import GenerateContentConfig

            config = GenerateContentConfig(system_instruction=system_prompt)
        except ImportError:
            config = _GeminiConfig(system_instruction=system_prompt)

        # Cancellation stops awaiting the SDK call, but the worker thread keeps running.
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=model or self._model,
            contents=prompt,
            config=config,
        )
        return response.text

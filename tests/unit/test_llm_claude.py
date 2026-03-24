# tests/unit/test_llm_claude.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from pulse.llm.base import LLMProvider
from pulse.llm.claude import ClaudeProvider


@pytest.mark.asyncio
async def test_claude_provider_sends_message_and_returns_text():
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Here is your summary.")]
    mock_client.messages.create.return_value = mock_response

    provider = ClaudeProvider(client=mock_client, model="claude-sonnet-4-20250514")
    result = await provider.complete(
        system_prompt="You are a helpful assistant.",
        user_prompt="Summarize my day.",
    )

    assert result == "Here is your summary."
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "Summarize my day."}],
    )


def test_claude_provider_satisfies_llm_provider_protocol():
    # Structural typing check — ClaudeProvider should be assignable to LLMProvider
    provider: LLMProvider = ClaudeProvider(client=AsyncMock(), model="test")
    assert provider is not None

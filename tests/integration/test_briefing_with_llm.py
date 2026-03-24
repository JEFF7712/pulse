from datetime import date

import pytest

from pulse.analysis.briefing import build_morning_briefing


class FakeLLM:
    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "Light day ahead. 1 meeting at 9am. Check advisor email."


@pytest.mark.asyncio
async def test_build_morning_briefing_with_llm():
    notification = await build_morning_briefing(
        day=date(2026, 3, 22),
        digest_markdown="## Timeline\n- 09:00 Standup\n",
        llm=FakeLLM(),
    )
    assert "Light day ahead" in notification.body


@pytest.mark.asyncio
async def test_build_morning_briefing_without_llm_falls_back():
    notification = await build_morning_briefing(
        day=date(2026, 3, 22),
        digest_markdown="## Timeline\n- 09:00 Standup\n",
    )
    assert "09:00 Standup" in notification.body

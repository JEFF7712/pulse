import logging
from datetime import date

from pulse.domain.notifications import Notification

logger = logging.getLogger(__name__)

BRIEFING_SYSTEM_PROMPT = (
    "You are a personal assistant. Summarize this daily digest into a concise "
    "3-5 line morning briefing message. Use plain text, no markdown. "
    "Focus on what matters most for the day ahead."
)


async def build_morning_briefing(
    day: date, digest_markdown: str, llm=None
) -> Notification:
    if llm is not None:
        try:
            body = await llm.complete(
                system_prompt=BRIEFING_SYSTEM_PROMPT,
                user_prompt=digest_markdown,
            )
            return Notification(
                title=f"Morning briefing for {day.isoformat()}",
                body=body,
                category="morning_briefing",
                context_id=day.isoformat(),
            )
        except Exception:
            logger.warning("LLM call failed for briefing; using fallback.", exc_info=True)

    bullet_lines = [
        line.strip() for line in digest_markdown.splitlines() if line.startswith("- ")
    ]
    key_lines = bullet_lines[:3]

    body_lines = ["Here are the key points for your day."]
    if key_lines:
        body_lines.extend(["", *key_lines])
    else:
        body_lines.extend(["", "- No digest highlights available."])

    return Notification(
        title=f"Morning briefing for {day.isoformat()}",
        body="\n".join(body_lines),
        category="morning_briefing",
        context_id=day.isoformat(),
    )

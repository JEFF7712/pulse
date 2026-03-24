from datetime import date

from pulse.domain.notifications import Notification


def build_morning_briefing(day: date, digest_markdown: str) -> Notification:
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

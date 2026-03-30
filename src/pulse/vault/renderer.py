from datetime import date

from pulse.vault.wikilinks import format_daily_digest_nav_line


def _navigation_day_for_renderer(
    date_label: str, navigation_day: date | None
) -> date | None:
    if navigation_day is not None:
        return navigation_day
    try:
        return date.fromisoformat(date_label.strip())
    except ValueError:
        return None


def render_daily_digest(
    *,
    date_label: str,
    timeline_items: list[str],
    email_highlights: list[str],
    spending_items: list[str],
    health_items: list[str],
    media_items: list[str],
    browsing_items: list[str] | None = None,
    tags: list[str],
    navigation_day: date | None = None,
) -> str:
    if browsing_items is None:
        browsing_items = []
    sections = [
        ("Timeline", timeline_items, "No timeline entries."),
        ("Email Highlights", email_highlights, "No email highlights."),
        ("Spending", spending_items, "No spending recorded."),
        ("Health", health_items, "No health updates."),
        ("Media", media_items, "No media activity."),
        ("Browsing", browsing_items, "No browsing activity."),
        ("Tags", tags, "No tags."),
    ]
    lines = [f"# {date_label}", ""]
    nav_day = _navigation_day_for_renderer(date_label, navigation_day)
    if nav_day is not None:
        lines.extend([format_daily_digest_nav_line(nav_day), ""])

    for index, (title, items, fallback) in enumerate(sections):
        lines.append(f"## {title}")
        lines.extend(_render_items(items, fallback))
        if index < len(sections) - 1:
            lines.append("")

    return "\n".join(lines)


def _render_items(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [f"- {fallback}"]

    return [f"- {item}" for item in items]

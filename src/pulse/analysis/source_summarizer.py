"""SourceSummarizer — Haiku pass for per-source narrative summaries."""
from __future__ import annotations

import asyncio

from pulse.analysis.preprocessor import PreprocessedDay

_SOURCE_SUMMARIZER_SYSTEM = (
    "You summarize private personal activity logs for the user's timeline. "
    "Stay factual and concise; do not give medical, legal, or financial advice; "
    "do not moralize or lecture."
)


class SourceSummarizer:
    def __init__(self, llm, model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._model = model

    async def _complete(self, prompt: str) -> str:
        return await self._llm.complete(
            prompt,
            model=self._model,
            system_prompt=_SOURCE_SUMMARIZER_SYSTEM,
        )

    async def summarize(self, day: PreprocessedDay) -> dict[str, str]:
        """Summarize each active source into a short narrative. Returns {source: narrative}."""
        tasks: list[tuple[str, object]] = []

        if day.browsing_clusters:
            tasks.append(("browsing", self._summarize_browsing(day)))
        if day.email_threads:
            tasks.append(("email", self._summarize_email(day)))
        if day.calendar_blocks:
            tasks.append(("calendar", self._summarize_calendar(day)))
        if day.media_sessions:
            tasks.append(("media", self._summarize_media(day)))
        if day.dev_activities:
            tasks.append(("dev", self._summarize_dev(day)))
        if day.finance_summary is not None:
            tasks.append(("finance", self._summarize_finance(day)))
        if day.health_days or day.health_workouts:
            tasks.append(("health", self._summarize_health(day)))
        if day.notion_edits:
            tasks.append(("notion", self._summarize_notion(day)))

        if not tasks:
            return {}

        keys = [k for k, _ in tasks]
        results = await asyncio.gather(*(coro for _, coro in tasks))
        return dict(zip(keys, results))

    async def _summarize_browsing(self, day: PreprocessedDay) -> str:
        lines = []
        for cluster in day.browsing_clusters[:15]:
            titles = ", ".join(cluster.titles[:5])
            lines.append(
                f"- {cluster.domain}: {cluster.visit_count} pages, "
                f"~{cluster.estimated_minutes:.0f} min ({titles})"
            )

        prompt = (
            "Summarize this person's browsing activity into 2-3 paragraphs. "
            "Focus on what topics they explored, how long they spent, and anything notable.\n\n"
            f"Browsing clusters:\n" + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_email(self, day: PreprocessedDay) -> str:
        lines = []
        active = [t for t in day.email_threads if t.is_active]
        inactive = [t for t in day.email_threads if not t.is_active]

        if active:
            lines.append("Active conversations:")
            for t in active[:10]:
                senders = ", ".join(t.senders[:3])
                lines.append(f"- \"{t.subject}\" ({t.message_count} messages, with {senders})")

        if inactive:
            lines.append(f"\n{len(inactive)} other threads (newsletters, notifications, single messages)")
            for t in inactive[:5]:
                lines.append(f"- \"{t.subject}\" from {t.senders[0] if t.senders else 'unknown'}")

        prompt = (
            "Summarize this person's email activity into 2-3 paragraphs. "
            "Focus on what conversations were active and what seemed important.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_calendar(self, day: PreprocessedDay) -> str:
        total_minutes = sum(b.duration_minutes for b in day.calendar_blocks)
        back_to_back = sum(1 for b in day.calendar_blocks if b.back_to_back)

        lines = [f"Total: {len(day.calendar_blocks)} events, ~{total_minutes:.0f} min"]
        if back_to_back:
            lines.append(f"Back-to-back meetings: {back_to_back}")

        for block in day.calendar_blocks:
            time_str = block.start.strftime("%H:%M")
            b2b = " [back-to-back]" if block.back_to_back else ""
            lines.append(f"- {time_str} {block.title}{b2b}")

        prompt = (
            "Summarize this person's calendar into 2-3 paragraphs. "
            "Note meeting density, gaps, and what kind of day it was.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_media(self, day: PreprocessedDay) -> str:
        lines = []
        for session in day.media_sessions:
            items = ", ".join(session.items[:5])
            more = f" (+{len(session.items) - 5} more)" if len(session.items) > 5 else ""
            lines.append(
                f"- {session.source} session (~{session.duration_minutes:.0f} min): {items}{more}"
            )

        prompt = (
            "Summarize this person's media consumption into 1-2 paragraphs. "
            "Note what they listened to or watched and any themes.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_dev(self, day: PreprocessedDay) -> str:
        lines = []
        for act in day.dev_activities[:20]:
            lines.append(f"- [{act.provider}] {act.title}")
        prompt = (
            "Summarize this person's development activity (GitHub, GitLab, Linear) in 1-2 paragraphs. "
            "Focus on what they shipped, reviewed, or discussed.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_notion(self, day: PreprocessedDay) -> str:
        lines = []
        for n in day.notion_edits[:25]:
            lines.append(
                f"- {n.timestamp.strftime('%H:%M')} {n.object_type} ({n.via}): {n.title}"
            )
        prompt = (
            "Summarize this person's Notion activity for the day in 1-2 short paragraphs. "
            "Note which pages or databases changed and any themes — stay factual.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_health(self, day: PreprocessedDay) -> str:
        lines = []
        for h in day.health_days:
            bits = []
            if h.sleep_score is not None:
                bits.append(f"sleep {h.sleep_score}")
            if h.readiness_score is not None:
                bits.append(f"readiness {h.readiness_score}")
            if h.sleep_duration_seconds is not None:
                bits.append(f"~{h.sleep_duration_seconds / 3600:.1f}h asleep")
            if h.deep_sleep_seconds is not None:
                bits.append(f"deep {h.deep_sleep_seconds / 3600:.1f}h")
            if h.rem_sleep_seconds is not None:
                bits.append(f"REM {h.rem_sleep_seconds / 3600:.1f}h")
            if h.activity_score is not None:
                bits.append(f"activity {h.activity_score}")
            if h.steps is not None:
                bits.append(f"{h.steps} steps")
            if h.active_calories is not None:
                bits.append(f"{h.active_calories} active kcal")
            lines.append(f"- {h.day}: {', '.join(bits) if bits else 'data'}")
        for w in day.health_workouts[:12]:
            wc = f"{w.calories} kcal" if w.calories is not None else ""
            lines.append(
                f"- workout {w.start.strftime('%H:%M')} {w.title} "
                f"~{w.duration_minutes:.0f}m {wc}".strip()
            )
        prompt = (
            "Summarize this person's sleep, readiness, daily activity, and workouts in 2-3 short factual paragraphs. "
            "Do not diagnose; describe scores and patterns only.\n\n"
            + "\n".join(lines)
        )
        return await self._complete(prompt)

    async def _summarize_finance(self, day: PreprocessedDay) -> str:
        fs = day.finance_summary
        if fs is None:
            return ""
        if fs.omit_amounts:
            body = (
                f"{fs.transaction_count} transactions; top merchants by count: "
                + ", ".join(f"{n} ({c})" for n, c in fs.merchant_counts[:6])
            )
        else:
            body = (
                f"Total outflow ${fs.total_outflow:,.2f} over {fs.transaction_count} transactions. "
                "Top merchants by spend: "
                + ", ".join(f"{n} (${s:,.2f})" for n, s in fs.merchant_spend[:6])
            )
        prompt = (
            "Summarize this person's spending day in 1-2 short paragraphs. "
            "Do not moralize; stay factual.\n\n"
            f"{body}"
        )
        return await self._complete(prompt)

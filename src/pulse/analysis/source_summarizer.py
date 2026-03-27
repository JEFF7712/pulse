"""SourceSummarizer — Haiku pass for per-source narrative summaries."""
from __future__ import annotations

from pulse.analysis.preprocessor import PreprocessedDay


class SourceSummarizer:
    def __init__(self, llm, model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._model = model

    async def summarize(self, day: PreprocessedDay) -> dict[str, str]:
        """Summarize each active source into a short narrative. Returns {source: narrative}."""
        narratives: dict[str, str] = {}

        if day.browsing_clusters:
            narratives["browsing"] = await self._summarize_browsing(day)
        if day.email_threads:
            narratives["email"] = await self._summarize_email(day)
        if day.calendar_blocks:
            narratives["calendar"] = await self._summarize_calendar(day)
        if day.media_sessions:
            narratives["media"] = await self._summarize_media(day)

        return narratives

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
        return await self._llm.complete(prompt, model=self._model)

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
        return await self._llm.complete(prompt, model=self._model)

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
        return await self._llm.complete(prompt, model=self._model)

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
        return await self._llm.complete(prompt, model=self._model)

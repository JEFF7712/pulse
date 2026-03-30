"""DigestBuilder — renders narrative daily digest markdown."""
from __future__ import annotations

from datetime import date

from pulse.analysis.preprocessor import PreprocessedDay
from pulse.vault.wikilinks import format_daily_digest_nav_line


def _fmt_hours(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    try:
        return f"{float(seconds) / 3600:.1f}h"
    except (TypeError, ValueError):
        return None

_BLOCK_LABELS = {
    0: "Late Night (12am-2am)",
    1: "Early Morning (2am-4am)",
    2: "Early Morning (4am-6am)",
    3: "Morning (6am-8am)",
    4: "Morning (8am-10am)",
    5: "Late Morning (10am-12pm)",
    6: "Afternoon (12pm-2pm)",
    7: "Afternoon (2pm-4pm)",
    8: "Late Afternoon (4pm-6pm)",
    9: "Evening (6pm-8pm)",
    10: "Evening (8pm-10pm)",
    11: "Night (10pm-12am)",
}


class DigestBuilder:
    def build(
        self,
        day: date,
        preprocessed: PreprocessedDay,
        narratives: dict[str, str] | None = None,
    ) -> str:
        sections: list[str] = [
            f"# {day.isoformat()}",
            "",
            format_daily_digest_nav_line(day),
            "",
        ]

        # Day at a Glance (only with LLM narratives)
        if narratives:
            glance = self._build_glance(narratives)
            sections.extend(["## Day at a Glance", glance, ""])

        # Timeline (chronological, grouped by time block)
        timeline = self._build_timeline(preprocessed)
        if timeline:
            sections.extend(["## Timeline", timeline, ""])

        # Email
        if preprocessed.email_threads:
            sections.extend(["## Email", self._build_email(preprocessed), ""])

        # Media
        if preprocessed.media_sessions:
            sections.extend(["## Media", self._build_media(preprocessed), ""])

        # Browsing
        if preprocessed.browsing_clusters:
            sections.extend(["## Browsing", self._build_browsing(preprocessed), ""])

        if preprocessed.dev_activities:
            sections.extend(["## Development", self._build_development(preprocessed), ""])

        if preprocessed.finance_summary is not None:
            sections.extend(["## Spending", self._build_spending(preprocessed), ""])

        if preprocessed.health_days or preprocessed.health_workouts:
            sections.extend(["## Health (Oura)", self._build_health(preprocessed), ""])

        if preprocessed.notion_edits:
            sections.extend(["## Notion", self._build_notion(preprocessed), ""])

        return "\n".join(sections)

    def _build_glance(self, narratives: dict[str, str]) -> str:
        # Combine first sentence of each narrative
        parts = []
        for source in (
            "calendar",
            "email",
            "browsing",
            "media",
            "dev",
            "finance",
            "health",
            "notion",
        ):
            text = narratives.get(source, "")
            if text:
                # Take first sentence
                first = text.split(". ")[0].rstrip(".")
                parts.append(first + ".")
        return " ".join(parts) if parts else "Quiet day."

    def _build_timeline(self, day: PreprocessedDay) -> str:
        # Collect all timestamped items
        items: list[tuple[int, str]] = []

        for block in day.calendar_blocks:
            time_str = block.start.strftime("%H:%M")
            b2b = " (back-to-back)" if block.back_to_back else ""
            items.append((block.start.hour, f"- {time_str} {block.title}{b2b}"))

        # Add browsing cluster summaries at their start time
        for cluster in day.browsing_clusters[:10]:
            time_str = cluster.first_visit.strftime("%H:%M")
            items.append((
                cluster.first_visit.hour,
                f"- {time_str} Browsing: {cluster.domain} "
                f"({cluster.visit_count} pages, ~{cluster.estimated_minutes:.0f} min)",
            ))

        # Add media sessions
        for session in day.media_sessions:
            time_str = session.first_item.strftime("%H:%M")
            item_preview = session.items[0] if session.items else session.source
            count = f" (+{len(session.items) - 1} more)" if len(session.items) > 1 else ""
            items.append((
                session.first_item.hour,
                f"- {time_str} {session.source.title()}: {item_preview}{count}",
            ))

        for act in day.dev_activities[:15]:
            time_str = act.timestamp.strftime("%H:%M")
            prov = act.provider.title()
            items.append((
                act.timestamp.hour,
                f"- {time_str} {prov}: {act.title}",
            ))

        if day.finance_summary and day.finance_summary.transaction_count:
            fs = day.finance_summary
            label = (
                f"{fs.transaction_count} transactions"
                if fs.omit_amounts
                else f"{fs.transaction_count} transactions, ~${fs.total_outflow:,.2f} outflow"
            )
            items.append((12, f"- Spending: {label}"))

        for h in day.health_days[:3]:
            parts = []
            if h.sleep_score is not None:
                parts.append(f"sleep {h.sleep_score}")
            if h.readiness_score is not None:
                parts.append(f"readiness {h.readiness_score}")
            ah = _fmt_hours(h.sleep_duration_seconds)
            if ah:
                parts.append(f"asleep ~{ah}")
            if h.steps is not None:
                parts.append(f"{h.steps:,} steps")
            if parts:
                items.append((8, f"- Oura ({h.day}): {', '.join(parts)}"))

        for w in day.health_workouts[:8]:
            time_str = w.start.strftime("%H:%M")
            dur = f", ~{w.duration_minutes:.0f} min" if w.duration_minutes else ""
            items.append((
                w.start.hour,
                f"- {time_str} Workout: {w.title}{dur}",
            ))

        for n in day.notion_edits[:15]:
            time_str = n.timestamp.strftime("%H:%M")
            kind = n.object_type or "page"
            src = f" ({n.via})" if n.via else ""
            items.append((
                n.timestamp.hour,
                f"- {time_str} Notion{src}: {n.title} [{kind}]",
            ))

        if not items:
            return ""

        items.sort(key=lambda x: x[0])

        # Group by 2-hour blocks
        lines = []
        current_block = -1
        for hour, text in items:
            block = hour // 2
            if block != current_block:
                current_block = block
                label = _BLOCK_LABELS.get(block, f"Block {block}")
                lines.append(f"### {label}")
            lines.append(text)

        return "\n".join(lines)

    def _build_email(self, day: PreprocessedDay) -> str:
        lines = []
        active = [t for t in day.email_threads if t.is_active]
        inactive = [t for t in day.email_threads if not t.is_active]

        for thread in active:
            senders = ", ".join(thread.senders[:3])
            lines.append(
                f"- **{thread.subject}** ({thread.message_count} messages with {senders})"
            )

        for thread in inactive:
            lines.append(f"- {thread.subject} ({thread.message_count} message, inactive)")

        return "\n".join(lines) if lines else "No email activity."

    def _build_media(self, day: PreprocessedDay) -> str:
        lines = []
        for session in day.media_sessions:
            items = ", ".join(session.items[:5])
            more = f" (+{len(session.items) - 5} more)" if len(session.items) > 5 else ""
            lines.append(
                f"- {session.source.title()}: {items}{more} (~{session.duration_minutes:.0f} min)"
            )
        return "\n".join(lines) if lines else "No media activity."

    def _build_browsing(self, day: PreprocessedDay) -> str:
        lines = []
        for cluster in day.browsing_clusters[:10]:
            titles = ", ".join(cluster.titles[:3])
            more = f" (+{len(cluster.titles) - 3} more)" if len(cluster.titles) > 3 else ""
            lines.append(
                f"- {cluster.domain}: {titles}{more} (~{cluster.estimated_minutes:.0f} min)"
            )
        return "\n".join(lines) if lines else "No browsing activity."

    def _build_development(self, day: PreprocessedDay) -> str:
        lines = []
        for act in day.dev_activities[:25]:
            repo = f" ({act.repo})" if act.repo else ""
            lines.append(f"- **{act.provider}**{repo}: {act.title}")
        return "\n".join(lines) if lines else "No development activity."

    def _build_notion(self, day: PreprocessedDay) -> str:
        lines = [
            f"- **{len(day.notion_edits)} update(s)** in connected pages and databases.",
            "",
        ]
        for n in day.notion_edits[:30]:
            time_str = n.timestamp.strftime("%H:%M")
            via = f" _({n.via})_" if n.via else ""
            kind = f" `{n.object_type}`" if n.object_type else ""
            link = f" — {n.url}" if n.url else ""
            lines.append(f"- {time_str}{via}{kind} **{n.title}**{link}")
        return "\n".join(lines)

    def _build_health(self, day: PreprocessedDay) -> str:
        blocks: list[str] = []

        if day.health_days:
            blocks.append("### Daily summary")
            for h in day.health_days:
                blocks.append(f"#### {h.day}")
                if h.sleep_score is not None:
                    blocks.append(f"- Sleep score **{h.sleep_score}**")
                asleep = _fmt_hours(h.sleep_duration_seconds)
                if asleep:
                    blocks.append(f"- Time asleep **~{asleep}**")
                in_bed = _fmt_hours(h.time_in_bed_seconds)
                if in_bed:
                    blocks.append(f"- Time in bed **~{in_bed}**")
                if h.sleep_efficiency is not None:
                    blocks.append(f"- Sleep efficiency **{h.sleep_efficiency}%**")
                stages: list[str] = []
                ds = _fmt_hours(h.deep_sleep_seconds)
                if ds:
                    stages.append(f"deep {ds}")
                rs = _fmt_hours(h.rem_sleep_seconds)
                if rs:
                    stages.append(f"REM {rs}")
                ls = _fmt_hours(h.light_sleep_seconds)
                if ls:
                    stages.append(f"light {ls}")
                if stages:
                    blocks.append("- Stages: " + ", ".join(stages))
                if h.readiness_score is not None:
                    blocks.append(f"- Readiness **{h.readiness_score}**")
                act: list[str] = []
                if h.activity_score is not None:
                    act.append(f"activity score **{h.activity_score}**")
                if h.steps is not None:
                    act.append(f"**{h.steps:,}** steps")
                if h.active_calories is not None:
                    act.append(f"**{h.active_calories}** active kcal")
                dist = h.equivalent_walking_distance_meters
                if dist is not None:
                    act.append(f"~**{dist / 1000:.1f}** km walk equiv.")
                if act:
                    blocks.append("- " + " · ".join(act))
                blocks.append("")

        if day.health_workouts:
            blocks.append("### Workouts")
            for w in day.health_workouts:
                time_str = w.start.strftime("%H:%M")
                bits = [f"**{w.title}** at {time_str}"]
                if w.duration_minutes and w.duration_minutes > 0:
                    bits.append(f"~{w.duration_minutes:.0f} min")
                if w.calories is not None:
                    bits.append(f"{w.calories} kcal")
                if w.intensity:
                    bits.append(f"intensity {w.intensity}")
                blocks.append("- " + " · ".join(bits))
            blocks.append("")

        text = "\n".join(blocks).strip()
        return text if text else "No Oura data."

    def _build_spending(self, day: PreprocessedDay) -> str:
        fs = day.finance_summary
        if fs is None:
            return "No finance activity."
        lines = []
        if fs.omit_amounts:
            lines.append(
                f"- {fs.transaction_count} transactions (amounts hidden per connector setting)."
            )
            for name, cnt in fs.merchant_counts[:8]:
                lines.append(f"- {name}: {cnt} tx")
        else:
            lines.append(
                f"- Total outflow (debits): ${fs.total_outflow:,.2f} across "
                f"{fs.transaction_count} transactions."
            )
            for name, spent in fs.merchant_spend[:8]:
                lines.append(f"- {name}: ${spent:,.2f}")
        return "\n".join(lines)

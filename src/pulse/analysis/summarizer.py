from dataclasses import dataclass
from datetime import date

from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.digest_builder import DigestBuilder
from pulse.domain.events import Event
from pulse.vault.renderer import render_daily_digest


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def __init__(self, llm=None, summarization_model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._summarization_model = summarization_model

    async def summarize_async(self, day: date, events: list[Event]) -> DailySummary:
        """Async summarization with LLM narratives when available."""
        preprocessor = EventPreprocessor()
        preprocessed = preprocessor.preprocess(events)

        narratives = None
        if self._llm is not None:
            from pulse.analysis.source_summarizer import SourceSummarizer
            summarizer = SourceSummarizer(llm=self._llm, model=self._summarization_model)
            narratives = await summarizer.summarize(preprocessed)

        builder = DigestBuilder()
        markdown = builder.build(day, preprocessed, narratives)
        return DailySummary(day=day, markdown=markdown)

    def summarize(self, day: date, events: list[Event]) -> DailySummary:
        """Sync fallback — uses preprocessor but no LLM narratives."""
        preprocessor = EventPreprocessor()
        preprocessed = preprocessor.preprocess(events)
        builder = DigestBuilder()
        markdown = builder.build(day, preprocessed, narratives=None)
        return DailySummary(day=day, markdown=markdown)


def _event_text(event: Event, preferred_key: str | None = None) -> str:
    if preferred_key is not None:
        value = event.data.get(preferred_key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return event.event_type

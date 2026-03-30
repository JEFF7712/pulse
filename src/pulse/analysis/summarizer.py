from dataclasses import dataclass
from datetime import date

from pulse.analysis.preprocessor import EventPreprocessor
from pulse.analysis.digest_builder import DigestBuilder
from pulse.domain.events import Event


@dataclass(slots=True)
class DailySummary:
    day: date
    markdown: str


class DailySummarizer:
    def __init__(self, llm=None, summarization_model: str = "") -> None:
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

from typing import Protocol


class LLM(Protocol):
    def complete(self, prompt: str, *, system_prompt: str | None = None) -> str: ...

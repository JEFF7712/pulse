from __future__ import annotations

import hashlib
import math
from typing import Protocol

from pulse.domain.events import Event


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def event_text(event: Event) -> str:
    """Build the text to embed for an event: source + event_type + stringy data values."""
    parts: list[str] = [event.source, event.event_type]

    def collect(value: object) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    collect(event.data)
    return " ".join(p for p in parts if p).strip()


class FakeEmbedder:
    """Deterministic hash-based embedder for tests (no model, no network)."""

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * self._dim
            for token in t.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % self._dim] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


class Model2VecEmbedder:
    """Real local embedder (optional `model2vec` extra). Lazily imported."""

    def __init__(self, model_name: str = "minishlab/potion-base-32M") -> None:
        from model2vec import StaticModel  # optional dep; import only when used

        self._model = StaticModel.from_pretrained(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        arr = self._model.encode(list(texts))
        return [list(map(float, row)) for row in arr]

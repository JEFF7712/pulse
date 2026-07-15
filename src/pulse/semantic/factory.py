from pulse.app.config import PulseConfig


def semantic_enabled(config: PulseConfig) -> bool:
    return bool(config.semantic and config.semantic.enabled)


def load_embedder(config: PulseConfig):
    """Return a real embedder when semantic is enabled and model2vec is importable, else None."""
    if not semantic_enabled(config):
        return None
    try:
        from pulse.semantic.embedder import Model2VecEmbedder

        return Model2VecEmbedder(config.semantic.model)
    except Exception:
        return None  # extra not installed / model unavailable → graceful degrade

from pulse.app.config import PulseConfig, SemanticConfig
from pulse.semantic.embedder import FakeEmbedder
from pulse.semantic.factory import load_embedder, semantic_enabled


def test_load_embedder_returns_none_when_semantic_absent():
    assert load_embedder(PulseConfig()) is None
    assert semantic_enabled(PulseConfig()) is False


def test_load_embedder_returns_none_when_semantic_disabled():
    config = PulseConfig(semantic=SemanticConfig(enabled=False))
    assert load_embedder(config) is None
    assert semantic_enabled(config) is False


def test_load_embedder_returns_injected_fake_when_enabled(monkeypatch):
    fake = FakeEmbedder(dim=8)

    class _Injected:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def embed(self, texts: list[str]) -> list[list[float]]:
            return fake.embed(texts)

    monkeypatch.setattr(
        "pulse.semantic.embedder.Model2VecEmbedder",
        _Injected,
    )
    config = PulseConfig(semantic=SemanticConfig(enabled=True, model="test-model"))
    emb = load_embedder(config)
    assert emb is not None
    assert isinstance(emb, _Injected)
    assert emb.model_name == "test-model"
    assert semantic_enabled(config) is True


def test_semantic_config_defaults():
    sc = SemanticConfig()
    assert sc.enabled is False
    assert sc.model == "minishlab/potion-base-32M"

from pulse.semantic.search import cosine, rank_ids


def test_cosine_basic():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero vector safe


def test_rank_ids_returns_closest_first_limited():
    q = [1.0, 0.0]
    cands = [("a", [0.9, 0.1]), ("b", [0.0, 1.0]), ("c", [1.0, 0.0])]
    assert rank_ids(q, cands, limit=2) == ["c", "a"]

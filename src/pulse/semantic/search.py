import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def rank_ids(
    query: list[float], candidates: list[tuple[str, list[float]]], limit: int
) -> list[str]:
    scored = [(eid, cosine(query, vec)) for eid, vec in candidates]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [eid for eid, _ in scored[:limit]]

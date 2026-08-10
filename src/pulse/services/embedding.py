"""Keep event embeddings in step with ingest."""

from __future__ import annotations

import aiosqlite

# Bound the work per pass so a large backlog cannot stall a scheduled run.
DEFAULT_BATCH_LIMIT = 5000


async def embed_missing(
    db: aiosqlite.Connection, embedder, *, limit: int | None = None
) -> int:
    """Embed events that have no stored embedding. Returns how many were embedded."""
    from pulse.semantic.embedder import event_text
    from pulse.store.embeddings import EmbeddingRepository
    from pulse.store.events import EventRepository

    events_repo = EventRepository(db)
    emb_repo = EmbeddingRepository(db)

    missing = await emb_repo.missing_ids(await events_repo.all_ids())
    if not missing:
        return 0
    if limit is not None:
        missing = missing[:limit]

    by_id = await events_repo.get_events_by_ids(missing)
    ordered = [by_id[i] for i in missing if i in by_id]
    if not ordered:
        return 0
    vectors = embedder.embed([event_text(e) for e in ordered])
    await emb_repo.upsert_embeddings([(e.id, vec) for e, vec in zip(ordered, vectors)])
    return len(ordered)

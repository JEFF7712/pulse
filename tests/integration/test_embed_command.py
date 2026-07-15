import asyncio
from datetime import UTC, datetime


def test_backfill_embeddings_populates_missing(tmp_path):
    async def exercise() -> None:
        from pulse.app.commands.ops import _backfill_embeddings
        from pulse.domain.events import Event
        from pulse.semantic.embedder import FakeEmbedder
        from pulse.store.db import connect_db
        from pulse.store.embeddings import EmbeddingRepository
        from pulse.store.events import EventRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "embed.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EventRepository(db)
            await repo.upsert_events(
                [
                    Event(
                        id="e1",
                        timestamp=datetime(2026, 7, 1, tzinfo=UTC),
                        source="gmail",
                        event_type="email.received",
                        data={"subject": "hello"},
                    ),
                    Event(
                        id="e2",
                        timestamp=datetime(2026, 7, 2, tzinfo=UTC),
                        source="github",
                        event_type="commit",
                        data={"message": "fix"},
                    ),
                ]
            )

            count = await _backfill_embeddings(db, FakeEmbedder(dim=32))
            assert count == 2

            stored = dict(await EmbeddingRepository(db).load_all())
            assert set(stored) == {"e1", "e2"}
            assert len(stored["e1"]) == 32

            # second run embeds nothing new
            again = await _backfill_embeddings(db, FakeEmbedder(dim=32))
            assert again == 0

    asyncio.run(exercise())

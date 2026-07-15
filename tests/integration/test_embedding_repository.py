import asyncio
from array import array


def test_embedding_repository_upserts_load_all_and_missing_ids(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.embeddings import EmbeddingRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "embeddings.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = EmbeddingRepository(db)

            vec_a = [0.1, 0.2, 0.3, 0.4]
            vec_b = [1.0, 0.0, -0.5, 0.25]
            await repository.upsert_embeddings(
                [
                    ("evt-a", vec_a),
                    ("evt-b", vec_b),
                ]
            )

            loaded = await repository.load_all()
            by_id = dict(loaded)
            assert set(by_id) == {"evt-a", "evt-b"}
            # float32 packing: values round-trip within float32 precision
            assert by_id["evt-a"] == list(array("f", vec_a))
            assert by_id["evt-b"] == list(array("f", vec_b))

            # upsert replaces existing vector
            vec_a2 = [9.0, 8.0, 7.0, 6.0]
            await repository.upsert_embeddings([("evt-a", vec_a2)])
            by_id = dict(await repository.load_all())
            assert by_id["evt-a"] == list(array("f", vec_a2))
            assert by_id["evt-b"] == list(array("f", vec_b))

            missing = await repository.missing_ids(["evt-a", "evt-c", "evt-b", "evt-d"])
            assert missing == ["evt-c", "evt-d"]

            assert await repository.missing_ids([]) == []
            assert await repository.upsert_embeddings([]) is None

    asyncio.run(exercise())


def test_load_for_ids_returns_only_requested(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.embeddings import EmbeddingRepository
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "emb_ids.db"
        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repo = EmbeddingRepository(db)
            await repo.upsert_embeddings([("a", [1.0, 0.0]), ("b", [0.0, 1.0]), ("c", [1.0, 1.0])])
            got = dict(await repo.load_for_ids(["a", "c", "missing"]))
            assert set(got) == {"a", "c"}
            assert got["a"] == [1.0, 0.0]

    asyncio.run(exercise())

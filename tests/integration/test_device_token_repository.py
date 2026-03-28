import asyncio


def test_device_token_repository_stores_and_retrieves_tokens(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 1
            assert tokens[0]["token"] == "fcm-token-abc"
            assert tokens[0]["platform"] == "ios"

    asyncio.run(exercise())


def test_device_token_repository_upsert_replaces_existing_token(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")
            await repo.upsert("fcm-token-abc", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 1

    asyncio.run(exercise())


def test_device_token_repository_supports_multiple_tokens(tmp_path):
    async def exercise() -> None:
        from pulse.store.db import connect_db
        from pulse.store.device_tokens import DeviceTokenRepository
        from pulse.store.schema import bootstrap_schema

        async with connect_db(tmp_path / "tokens.db") as db:
            await bootstrap_schema(db)
            repo = DeviceTokenRepository(db)

            await repo.upsert("fcm-token-abc", "ios")
            await repo.upsert("fcm-token-def", "ios")

            tokens = await repo.list_active()
            assert len(tokens) == 2

    asyncio.run(exercise())

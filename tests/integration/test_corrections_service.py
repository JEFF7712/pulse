import asyncio


def test_correction_service_records_and_returns_reply(tmp_path):
    async def exercise() -> None:
        from pulse.services.corrections import CorrectionService
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            repository = CorrectionRepository(db)
            service = CorrectionService(repository)

            correction = await service.record_correction(
                context_id="ctx-123",
                message_text="Please use the updated project name.",
            )

            assert correction.context_id == "ctx-123"
            assert correction.message_text == "Please use the updated project name."
            assert correction.id
            assert correction.created_at

            cursor = await db.execute(
                "SELECT id, context_id, message_text FROM corrections WHERE id = ?",
                (correction.id,),
            )
            row = await cursor.fetchone()
            await cursor.close()

            assert row == (
                correction.id,
                "ctx-123",
                "Please use the updated project name.",
            )

        import aiosqlite

        raw_db = await aiosqlite.connect(db_path)
        try:
            cursor = await raw_db.execute("SELECT COUNT(*) FROM corrections")
            row = await cursor.fetchone()
            await cursor.close()
        finally:
            await raw_db.close()

        assert row == (1,)

    asyncio.run(exercise())

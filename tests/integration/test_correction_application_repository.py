import asyncio
from datetime import UTC, datetime, timedelta, timezone


def test_correction_application_repository_round_trips_records(tmp_path) -> None:
    async def exercise() -> None:
        from pulse.domain.correction_applications import CorrectionApplication
        from pulse.domain.corrections import Correction
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        created_at = datetime(2026, 3, 27, 14, 0, tzinfo=timezone(timedelta(hours=2)))
        updated_at = datetime(2026, 3, 27, 9, 5, tzinfo=timezone(timedelta(hours=-5)))
        application = CorrectionApplication(
            id="app-1",
            correction_id="corr-1",
            status="applied",
            target_type="file",
            target_ref="src/pulse/app.py",
            operation="replace",
            summary="Applied naming correction",
            error_message=None,
            created_at=created_at,
            updated_at=updated_at,
        )

        db_path = tmp_path / "correction-applications.db"
        async with connect_db(db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await bootstrap_schema(db)
            corrections = CorrectionRepository(db)
            repository = CorrectionApplicationRepository(db)

            await corrections.add(
                Correction(
                    id="corr-1",
                    context_id="ctx-1",
                    message_text="Apply the naming correction.",
                    created_at=datetime(2026, 3, 27, 11, 55, tzinfo=UTC),
                )
            )

            await repository.add(application)

            applications = await repository.list_for_correction("corr-1")
            assert applications == [
                CorrectionApplication(
                    id="app-1",
                    correction_id="corr-1",
                    status="applied",
                    target_type="file",
                    target_ref="src/pulse/app.py",
                    operation="replace",
                    summary="Applied naming correction",
                    error_message=None,
                    created_at=datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 3, 27, 14, 5, tzinfo=UTC),
                )
            ]

            cursor = await db.execute(
                "SELECT created_at, updated_at FROM correction_applications WHERE id = ?",
                ("app-1",),
            )
            row = await cursor.fetchone()
            await cursor.close()

            assert datetime.fromisoformat(row[0]) == datetime(
                2026, 3, 27, 12, 0, tzinfo=UTC
            )
            assert datetime.fromisoformat(row[1]) == datetime(
                2026, 3, 27, 14, 5, tzinfo=UTC
            )
            assert row[0].endswith("+00:00")
            assert row[1].endswith("+00:00")

            cursor = await db.execute("PRAGMA index_list('correction_applications')")
            indexes = await cursor.fetchall()
            await cursor.close()

            assert any(
                index[1] == "idx_correction_applications_correction_id_created_at_id"
                for index in indexes
            )

    asyncio.run(exercise())


def test_open_pulse_context_exposes_correction_application_repository(tmp_path) -> None:
    async def exercise() -> None:
        from pulse.mcp.context import open_pulse_context

        async with open_pulse_context(
            db_path=str(tmp_path / "test.db"),
            vault_path=str(tmp_path / "vault"),
        ) as ctx:
            assert ctx.correction_applications is not None

    asyncio.run(exercise())

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


class FakeLLM:
    def __init__(self, response: str):
        self._response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        return self._response


class RaisingLLM:
    async def complete(self, prompt, *, system_prompt=None, model=None):
        raise RuntimeError("LLM unavailable")


def test_correction_service_iso_date_context_records_needs_review(tmp_path):
    """YYYY-MM-DD-only contexts were legacy; they are no longer supported."""

    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        vault = VaultMemory(vault_path)

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(FakeLLM("{}"))
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=vault,
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="2026-03-22",
                message_text="The walk happened after lunch, not in the morning.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )

            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].operation == "needs_review"
            assert "no longer supported" in applications[0].summary.lower()

    asyncio.run(exercise())


def test_correction_service_records_skipped_audit_without_corrections_llm(tmp_path):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
            )

            correction = await service.record_correction(
                context_id="2026-03-22",
                message_text="Please use the corrected time.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )

            assert len(applications) == 1
            assert applications[0].status == "skipped"
            assert applications[0].target_type == "none"
            assert applications[0].target_ref == "2026-03-22"
            assert applications[0].operation == "none"
            assert (
                applications[0].summary
                == "Correction application skipped: no corrections LLM configured"
            )
            assert applications[0].error_message is None

    asyncio.run(exercise())


def test_correction_service_records_needs_review_for_invalid_interpreter_output(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        vault = VaultMemory(vault_path)
        pattern_path = (
            vault_path / "02-Insights" / "patterns" / "morning-walk.md"
        )
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Morning walk\n\n**Status:** active\n**Confidence:** 0.5\n"
            "**First seen:** 2026-03-22\n**Last updated:** 2026-03-22\n\n"
            "## Observation\nWalk before work.\n\n## Evidence Log\n- 2026-03-22: 20 min\n\n"
            "## Trend\nStable.\n\n## User Notes\n_Note._\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(FakeLLM("not json"))
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=vault,
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:morning-walk",
                message_text="The walk happened after lunch, not in the morning.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )

            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].target_type == "none"
            assert applications[0].target_ref == "pattern:morning-walk"
            assert applications[0].operation == "needs_review"
            assert (
                applications[0].summary == "LLM correction output could not be parsed"
            )
            assert applications[0].error_message is None

    asyncio.run(exercise())


def test_correction_service_records_needs_review_when_context_resolution_raises(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        class BrokenVaultMemory(VaultMemory):
            def read_pattern_by_slug(self, slug: str) -> str:
                raise OSError("vault read failed")

        db_path = tmp_path / "corrections.db"
        pattern_path = tmp_path / "vault" / "02-Insights" / "patterns" / "x.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text("# Pattern\n\n**Status:** active\n", encoding="utf-8")

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    '{"target_type":"pattern","operation":"update_pattern_notes","target_ref":"x","section":"User Notes","content":"Later.","summary":"Note.","confidence":0.9}'
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=BrokenVaultMemory(tmp_path / "vault"),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:x",
                message_text="The walk happened later.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].operation == "needs_review"
            assert (
                applications[0].summary
                == "Correction context could not be resolved safely"
            )
            assert applications[0].error_message == "vault read failed"

    asyncio.run(exercise())


def test_correction_service_records_needs_review_when_interpreter_raises(tmp_path):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        pattern_path = vault_path / "02-Insights" / "patterns" / "y.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Y\n\n**Status:** active\n**Confidence:** 0.5\n"
            "**First seen:** 2026-03-22\n**Last updated:** 2026-03-22\n\n"
            "## Observation\nTest.\n\n## Evidence Log\n\n## Trend\n\n## User Notes\n_Note._\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
                interpreter=LLMCorrectionInterpreter(RaisingLLM()),
            )

            correction = await service.record_correction(
                context_id="pattern:y",
                message_text="The walk happened later.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].operation == "needs_review"
            assert (
                applications[0].summary
                == "Correction interpretation could not be completed safely"
            )
            assert applications[0].error_message == "LLM unavailable"

    asyncio.run(exercise())


def test_correction_service_records_needs_review_when_apply_raises(tmp_path):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        class BrokenVaultMemory(VaultMemory):
            def update_pattern_notes(self, slug: str, notes: str):
                raise RuntimeError("disk full")

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        pattern_path = vault_path / "02-Insights" / "patterns" / "z.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Z\n\n**Status:** active\n**Confidence:** 0.5\n"
            "**First seen:** 2026-03-22\n**Last updated:** 2026-03-22\n\n"
            "## Observation\nTest.\n\n## Evidence Log\n\n## Trend\n\n## User Notes\n_Note._\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    '{"target_type":"pattern","operation":"update_pattern_notes","target_ref":"z","section":"User Notes","content":"Later.","summary":"Append correction.","confidence":0.9}'
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=BrokenVaultMemory(vault_path),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:z",
                message_text="The walk happened later.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "failed"
            assert applications[0].target_type == "pattern"
            assert applications[0].operation == "update_pattern_notes"
            assert applications[0].summary == "Append correction."
            assert applications[0].error_message == "disk full"

    asyncio.run(exercise())


def test_correction_service_applies_routines_correction_and_records_audit_row(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        routines_path = vault_path / "03-Life" / "routines.md"
        routines_path.parent.mkdir(parents=True, exist_ok=True)
        routines_path.write_text(
            "# Routines\n\n## Morning\nTea first.\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    """
                    {
                      "target_type": "routines",
                      "operation": "replace_section",
                      "target_ref": "routines",
                      "section": "## Correction Updates",
                      "content": "Use a shorter shutdown routine.",
                      "summary": "Update routines corrections.",
                      "confidence": 0.89
                    }
                    """
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="routines",
                message_text="Use a shorter shutdown routine.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "applied"
            assert applications[0].target_type == "routines"
            assert applications[0].target_ref == "routines"
            assert applications[0].operation == "replace_section"
            assert applications[0].summary == "Update routines corrections."

        routines_text = routines_path.read_text(encoding="utf-8")
        assert "## Morning\nTea first." in routines_text
        assert "## Correction Updates\nUse a shorter shutdown routine." in routines_text

    asyncio.run(exercise())


def test_correction_service_applies_pattern_status_correction_and_records_audit_row(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        pattern_path = vault_path / "02-Insights" / "patterns" / "focus-sessions.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Focus sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nDeep work improves in quiet mornings.\n\n## Evidence Log\n- 2026-03-20: 2 h focus block\n\n## Trend\nStable.\n\n## User Notes\nKeep this note.\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    """
                    {
                      "target_type": "pattern",
                      "operation": "update_pattern_status",
                      "target_ref": "focus-sessions",
                      "section": "Status",
                      "content": "confirmed",
                      "summary": "Update the pattern status.",
                      "confidence": 0.87
                    }
                    """
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:focus-sessions",
                message_text="This pattern is confirmed.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "applied"
            assert applications[0].target_type == "pattern"
            assert applications[0].operation == "update_pattern_status"

        pattern_text = pattern_path.read_text(encoding="utf-8")
        assert "**Status:** confirmed" in pattern_text
        assert "## User Notes\nKeep this note." in pattern_text

    asyncio.run(exercise())


def test_correction_service_records_needs_review_when_interpreter_retargets_context(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        pattern_path = vault_path / "02-Insights" / "patterns" / "retarget-me.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Retarget me\n\n**Status:** active\n**Confidence:** 0.5\n"
            "**First seen:** 2026-03-22\n**Last updated:** 2026-03-22\n\n"
            "## Observation\nWalk.\n\n## Evidence Log\n\n## Trend\n\n## User Notes\n_Note._\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    """
                    {
                      "target_type": "profile",
                      "operation": "replace_section",
                      "target_ref": "profile",
                      "section": "## Learned Corrections",
                      "content": "Retargeted content.",
                      "summary": "Try to update profile instead.",
                      "confidence": 0.9
                    }
                    """
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:retarget-me",
                message_text="This was after lunch.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].operation == "needs_review"
            assert (
                applications[0].summary
                == "Correction action did not match the resolved target"
            )

    asyncio.run(exercise())


def test_correction_service_records_needs_review_for_invalid_pattern_status(
    tmp_path,
):
    async def exercise() -> None:
        from pulse.analysis.vault_memory import VaultMemory
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter
        from pulse.services.corrections import CorrectionService
        from pulse.store.correction_applications import CorrectionApplicationRepository
        from pulse.store.corrections import CorrectionRepository
        from pulse.store.db import connect_db
        from pulse.store.schema import bootstrap_schema

        db_path = tmp_path / "corrections.db"
        vault_path = tmp_path / "vault"
        pattern_path = vault_path / "02-Insights" / "patterns" / "focus-sessions.md"
        pattern_path.parent.mkdir(parents=True, exist_ok=True)
        pattern_path.write_text(
            "# Pattern: Focus sessions\n\n**Status:** active\n**Confidence:** 0.82\n**First seen:** 2026-01-10\n**Last updated:** 2026-03-20\n\n## Observation\nDeep work improves in quiet mornings.\n\n## Evidence Log\n- 2026-03-20: 2 h focus block\n\n## Trend\nStable.\n\n## User Notes\nKeep this note.\n",
            encoding="utf-8",
        )

        async with connect_db(db_path) as db:
            await bootstrap_schema(db)
            correction_repository = CorrectionRepository(db)
            application_repository = CorrectionApplicationRepository(db)
            interpreter = LLMCorrectionInterpreter(
                FakeLLM(
                    """
                    {
                      "target_type": "pattern",
                      "operation": "update_pattern_status",
                      "target_ref": "focus-sessions",
                      "section": "Status",
                      "content": "definitely-maybe",
                      "summary": "Update the pattern status.",
                      "confidence": 0.87
                    }
                    """
                )
            )
            service = CorrectionService(
                correction_repository,
                correction_applications=application_repository,
                vault_memory=VaultMemory(vault_path),
                interpreter=interpreter,
            )

            correction = await service.record_correction(
                context_id="pattern:focus-sessions",
                message_text="This pattern is confirmed.",
            )

            applications = await application_repository.list_for_correction(
                correction.id
            )
            assert len(applications) == 1
            assert applications[0].status == "needs_review"
            assert applications[0].operation == "needs_review"
            assert (
                applications[0].summary
                == "LLM correction output had invalid pattern status"
            )

        pattern_text = pattern_path.read_text(encoding="utf-8")
        assert "**Status:** active" in pattern_text

    asyncio.run(exercise())

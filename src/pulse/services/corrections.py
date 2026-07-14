from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any, Protocol
from uuid import uuid4

from pulse.analysis.vault_memory import VaultMemory
from pulse.app.config import PulseConfig
from pulse.domain.correction_applications import CorrectionApplication
from pulse.domain.corrections import Correction
from pulse.llm.factory import create_corrections_provider_from_config
from pulse.services.correction_interpreter import (
    CorrectionAction,
    LLMCorrectionInterpreter,
)

# YYYY-MM-DD alone was used for removed per-day file corrections; reject without LLM/vault work.
_LEGACY_DATE_ONLY_CONTEXT_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PROFILE_SECTION = "## Learned Corrections"
_ROUTINES_SECTION = "## Correction Updates"


class CorrectionRecorder(Protocol):
    async def add(self, correction: Correction) -> None: ...


class CorrectionApplicationRecorder(Protocol):
    async def add(self, application: CorrectionApplication) -> None: ...


@dataclass(slots=True)
class _ResolvedContext:
    payload: dict[str, Any] | None
    review_summary: str | None = None
    error_message: str | None = None


class CorrectionService:
    def __init__(
        self,
        repository: CorrectionRecorder,
        *,
        correction_applications: CorrectionApplicationRecorder | None = None,
        vault_memory: VaultMemory | None = None,
        interpreter: LLMCorrectionInterpreter | None = None,
        initialization_error: str | None = None,
    ) -> None:
        self._repository = repository
        self._correction_applications = correction_applications
        self._vault_memory = vault_memory
        self._interpreter = interpreter
        self._initialization_error = initialization_error

    async def record_correction(self, context_id: str, message_text: str) -> Correction:
        correction = Correction(
            id=str(uuid4()),
            context_id=context_id,
            message_text=message_text,
            created_at=datetime.now(UTC),
        )
        await self._repository.add(correction)
        await self._apply_if_configured(correction)
        return correction

    async def record_reply(self, context_id: str, message_text: str) -> Correction:
        return await self.record_correction(context_id, message_text)

    async def _apply_if_configured(self, correction: Correction) -> None:
        if self._correction_applications is None:
            return

        if self._initialization_error is not None:
            await self._record_application(
                correction,
                status="needs_review",
                target_type="none",
                target_ref=correction.context_id,
                operation="needs_review",
                summary="Correction application could not be initialized safely",
                error_message=self._initialization_error,
            )
            return

        if self._interpreter is None:
            await self._record_application(
                correction,
                status="skipped",
                target_type="none",
                target_ref=correction.context_id,
                operation="none",
                summary="Correction application skipped: no corrections LLM configured",
            )
            return

        if self._vault_memory is None:
            await self._record_application(
                correction,
                status="skipped",
                target_type="none",
                target_ref=correction.context_id,
                operation="none",
                summary="Correction application skipped: vault context unavailable",
            )
            return

        try:
            resolved = self._resolve_context_payload(correction.context_id)
        except Exception as exc:
            await self._record_application(
                correction,
                status="needs_review",
                target_type="none",
                target_ref=correction.context_id,
                operation="needs_review",
                summary="Correction context could not be resolved safely",
                error_message=str(exc),
            )
            return

        if resolved.review_summary is not None:
            await self._record_application(
                correction,
                status="needs_review",
                target_type="none",
                target_ref=correction.context_id,
                operation="needs_review",
                summary=resolved.review_summary,
                error_message=resolved.error_message,
            )
            return

        try:
            action = await self._interpreter.interpret(
                context_id=correction.context_id,
                message_text=correction.message_text,
                context_payload=resolved.payload or {},
            )
        except Exception as exc:
            await self._record_application(
                correction,
                status="needs_review",
                target_type="none",
                target_ref=correction.context_id,
                operation="needs_review",
                summary="Correction interpretation could not be completed safely",
                error_message=str(exc),
            )
            return

        if action.target_type == "none" or action.operation == "needs_review":
            await self._record_application(
                correction,
                status="needs_review",
                target_type=action.target_type,
                target_ref=action.target_ref,
                operation=action.operation,
                summary=action.summary,
            )
            return

        if not self._action_matches_resolved_target(action, resolved.payload or {}):
            await self._record_application(
                correction,
                status="needs_review",
                target_type="none",
                target_ref=correction.context_id,
                operation="needs_review",
                summary="Correction action did not match the resolved target",
            )
            return

        try:
            await self._apply_action(action)
        except ValueError as exc:
            await self._record_application(
                correction,
                status="needs_review",
                target_type=action.target_type,
                target_ref=action.target_ref,
                operation=action.operation,
                summary=str(exc),
            )
            return
        except Exception as exc:
            await self._record_application(
                correction,
                status="failed",
                target_type=action.target_type,
                target_ref=action.target_ref,
                operation=action.operation,
                summary=action.summary,
                error_message=str(exc),
            )
            return

        await self._record_application(
            correction,
            status="applied",
            target_type=action.target_type,
            target_ref=action.target_ref,
            operation=action.operation,
            summary=action.summary,
        )

    def _resolve_context_payload(self, context_id: str) -> _ResolvedContext:
        if self._vault_memory is None:
            raise RuntimeError("Initialize correction vault memory")

        if _LEGACY_DATE_ONLY_CONTEXT_RE.fullmatch(context_id):
            return _ResolvedContext(
                payload=None,
                review_summary=(
                    "Date-only correction contexts (YYYY-MM-DD) are no longer supported; "
                    "use pattern:, profile, or routines context IDs."
                ),
            )

        if context_id.startswith("pattern:"):
            slug = context_id.split(":", 1)[1].strip()
            if not slug:
                return _ResolvedContext(
                    payload=None,
                    review_summary="Correction context could not be resolved safely",
                )
            if not self._vault_memory.pattern_exists(slug):
                return _ResolvedContext(
                    payload=None,
                    review_summary="Correction target file is missing",
                )
            return _ResolvedContext(
                payload={
                    "target_type": "pattern",
                    "target_ref": slug,
                    "file": f"02-Insights/patterns/{slug}.md",
                    "content": self._vault_memory.read_pattern_by_slug(slug),
                }
            )

        if context_id == "profile":
            if not self._vault_memory.config_file_exists("profile.md"):
                return _ResolvedContext(
                    payload=None,
                    review_summary="Correction target file is missing",
                )
            return _ResolvedContext(
                payload={
                    "target_type": "profile",
                    "target_ref": "profile",
                    "file": "04-Config/profile.md",
                    "content": self._vault_memory.read_config_file("profile.md"),
                }
            )

        if context_id == "routines":
            if not self._vault_memory.life_file_exists("routines.md"):
                return _ResolvedContext(
                    payload=None,
                    review_summary="Correction target file is missing",
                )
            return _ResolvedContext(
                payload={
                    "target_type": "routines",
                    "target_ref": "routines",
                    "file": "03-Life/routines.md",
                    "content": self._vault_memory.read_life_file("routines.md"),
                }
            )

        return _ResolvedContext(
            payload=None,
            review_summary="Correction context could not be resolved safely",
        )

    async def _apply_action(self, action: CorrectionAction) -> None:
        if self._vault_memory is None:
            raise RuntimeError("Initialize correction vault memory")

        if (
            action.target_type == "pattern"
            and action.operation == "update_pattern_notes"
        ):
            self._vault_memory.update_pattern_notes(action.target_ref, action.content)
            return

        if (
            action.target_type == "pattern"
            and action.operation == "update_pattern_status"
        ):
            section = _normalize_section_heading(action.section)
            if section != "## Status":
                raise ValueError("Correction action could not be applied safely")
            self._vault_memory.update_pattern_status(action.target_ref, action.content)
            return

        if action.target_type == "profile" and action.operation == "replace_section":
            section = _normalize_section_heading(action.section)
            if section != _PROFILE_SECTION:
                raise ValueError("Correction action could not be applied safely")
            self._vault_memory.upsert_config_section(
                "profile.md",
                section,
                action.content,
            )
            return

        if action.target_type == "routines" and action.operation == "replace_section":
            section = _normalize_section_heading(action.section)
            if section != _ROUTINES_SECTION:
                raise ValueError("Correction action could not be applied safely")
            self._vault_memory.upsert_life_section(
                "routines.md",
                section,
                action.content,
            )
            return

        raise ValueError("Correction action could not be applied safely")

    def _action_matches_resolved_target(
        self, action: CorrectionAction, context_payload: dict[str, Any]
    ) -> bool:
        return action.target_type == context_payload.get(
            "target_type"
        ) and action.target_ref == context_payload.get("target_ref")

    async def _record_application(
        self,
        correction: Correction,
        *,
        status: str,
        target_type: str,
        target_ref: str,
        operation: str,
        summary: str,
        error_message: str | None = None,
    ) -> None:
        if self._correction_applications is None:
            raise RuntimeError("Initialize correction application recorder")

        timestamp = datetime.now(UTC)
        await self._correction_applications.add(
            CorrectionApplication(
                id=str(uuid4()),
                correction_id=correction.id,
                status=status,
                target_type=target_type,
                target_ref=target_ref,
                operation=operation,
                summary=summary,
                error_message=error_message,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )


def build_correction_service(
    repository: CorrectionRecorder,
    *,
    config: PulseConfig | None = None,
    correction_applications: CorrectionApplicationRecorder | None = None,
    vault_path: str | None = None,
) -> CorrectionService:
    vault_memory = VaultMemory(vault_path) if vault_path else None
    llm = None
    interpreter = None
    initialization_error = None
    if config is not None:
        try:
            llm = create_corrections_provider_from_config(config)
            interpreter = LLMCorrectionInterpreter(llm) if llm is not None else None
        except Exception as exc:
            initialization_error = str(exc)
    return CorrectionService(
        repository,
        correction_applications=correction_applications,
        vault_memory=vault_memory,
        interpreter=interpreter,
        initialization_error=initialization_error,
    )


def _normalize_section_heading(section: str) -> str:
    normalized = section.strip()
    if not normalized:
        return normalized
    if normalized.startswith("## "):
        return normalized
    return f"## {normalized.lstrip('#').strip()}"

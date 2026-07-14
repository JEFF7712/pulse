from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from pulse.connectors.github import GitHubConnector
from pulse.connectors.oura import OuraConnector
from pulse.domain.corrections import Correction
from pulse.services.correction_interpreter import CorrectionAction
from pulse.services.corrections import CorrectionService


class _Repository:
    async def add(self, correction: Correction) -> None:
        return None


def test_github_headers_require_auth_manager() -> None:
    connector = GitHubConnector(auth_manager=None)

    with pytest.raises(RuntimeError, match="Initialize GitHub auth manager"):
        connector._headers()


def test_oura_bearer_requires_auth_manager_without_personal_token() -> None:
    connector = OuraConnector(auth_manager=None, personal_access_token=None)

    with pytest.raises(RuntimeError, match="Initialize Oura auth manager"):
        connector._bearer()


def test_correction_service_resolve_context_requires_vault_memory() -> None:
    service = CorrectionService(repository=_Repository(), vault_memory=None)

    with pytest.raises(RuntimeError, match="Initialize correction vault memory"):
        service._resolve_context_payload("profile")


def test_correction_service_apply_action_requires_vault_memory() -> None:
    service = CorrectionService(repository=_Repository(), vault_memory=None)
    action = CorrectionAction(
        target_type="profile",
        operation="replace_section",
        target_ref="profile",
        section="## Learned Corrections",
        content="Updated",
        summary="Update profile",
        confidence=1.0,
    )

    with pytest.raises(RuntimeError, match="Initialize correction vault memory"):
        asyncio.run(service._apply_action(action))


def test_correction_service_record_application_requires_recorder() -> None:
    service = CorrectionService(repository=_Repository(), correction_applications=None)
    correction = Correction(
        id="corr-1",
        context_id="profile",
        message_text="Fix it",
        created_at=datetime.now(UTC),
    )

    with pytest.raises(
        RuntimeError, match="Initialize correction application recorder"
    ):
        asyncio.run(
            service._record_application(
                correction,
                status="skipped",
                target_type="none",
                target_ref="profile",
                operation="none",
                summary="Skipped",
            )
        )

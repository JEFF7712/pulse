from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pulse.domain.corrections import Correction


class CorrectionRecorder(Protocol):
    async def add(self, correction: Correction) -> None: ...


class CorrectionService:
    def __init__(self, repository: CorrectionRecorder) -> None:
        self._repository = repository

    async def record_correction(self, context_id: str, message_text: str) -> Correction:
        correction = Correction(
            id=str(uuid4()),
            context_id=context_id,
            message_text=message_text,
            created_at=datetime.now(UTC),
        )
        await self._repository.add(correction)
        return correction

    async def record_reply(self, context_id: str, message_text: str) -> Correction:
        return await self.record_correction(context_id, message_text)

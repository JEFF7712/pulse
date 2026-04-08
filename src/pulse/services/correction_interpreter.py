import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from pulse.domain.pattern_statuses import (
    PATTERN_STATUS_CHOICES,
    normalize_pattern_status,
)
from pulse.domain.llm import LLM

_ALLOWED_OPERATIONS: dict[str, set[str]] = {
    "pattern": {"update_pattern_notes", "update_pattern_status"},
    "profile": {"replace_section"},
    "routines": {"replace_section"},
    "none": {"needs_review"},
}

_REQUIRED_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("pattern", "update_pattern_notes"): (
        "target_ref",
        "section",
        "content",
        "summary",
    ),
    ("pattern", "update_pattern_status"): (
        "target_ref",
        "section",
        "content",
        "summary",
    ),
    ("profile", "replace_section"): ("target_ref", "section", "content", "summary"),
    ("routines", "replace_section"): ("target_ref", "section", "content", "summary"),
    ("none", "needs_review"): ("target_ref", "summary"),
}

_PATTERN_STATUS_CHOICES = " | ".join(PATTERN_STATUS_CHOICES)

_SYSTEM_PROMPT = """You interpret user corrections into one bounded JSON action.
Return JSON only. Do not include markdown fences.
Allowed target_type values: pattern, profile, routines, none.
Allowed operations by target:
- pattern: update_pattern_notes, update_pattern_status
- profile: replace_section
- routines: replace_section
- none: needs_review
Allowed pattern status content for update_pattern_status: PLACEHOLDER_PATTERN_STATUSES.
Required fields: target_type, operation, target_ref, section, content, summary, confidence.
confidence must be either numeric between 0 and 1, or a non-empty string label.
If the message is unclear or unsupported, return target_type=none and operation=needs_review.""".replace(
    "PLACEHOLDER_PATTERN_STATUSES", _PATTERN_STATUS_CHOICES
)


@dataclass(slots=True)
class CorrectionAction:
    target_type: str
    operation: str
    target_ref: str
    section: str
    content: str
    summary: str
    confidence: float | str

    @classmethod
    def needs_review(cls, target_ref: str, summary: str) -> "CorrectionAction":
        return cls(
            target_type="none",
            operation="needs_review",
            target_ref=target_ref,
            section="",
            content="",
            summary=summary,
            confidence=0.0,
        )


class LLMCorrectionInterpreter:
    def __init__(self, llm: LLM, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def interpret(
        self,
        *,
        context_id: str,
        message_text: str,
        context_payload: Mapping[str, Any],
    ) -> CorrectionAction:
        prompt = self._build_prompt(
            context_id=context_id,
            message_text=message_text,
            context_payload=context_payload,
        )
        raw_response = await self._llm.complete(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            model=self._model,
        )
        parsed = self._parse_json_object(raw_response)
        if parsed is None:
            return CorrectionAction.needs_review(
                target_ref=context_id,
                summary="LLM correction output could not be parsed",
            )
        return self._to_action(parsed, context_id=context_id)

    def _build_prompt(
        self,
        *,
        context_id: str,
        message_text: str,
        context_payload: Mapping[str, Any],
    ) -> str:
        rendered_payload = json.dumps(context_payload, indent=2, sort_keys=True)
        return (
            "Interpret this correction into one bounded action.\n"
            f"context_id: {context_id}\n"
            "message_text:\n<<<\n"
            f"{message_text}\n"
            ">>>\n"
            f"context_payload: {rendered_payload}\n"
        )

    def _to_action(
        self, payload: Mapping[str, Any], *, context_id: str
    ) -> CorrectionAction:
        target_type = str(payload.get("target_type", "")).strip()
        operation = str(payload.get("operation", "")).strip()
        if operation not in _ALLOWED_OPERATIONS.get(target_type, set()):
            return CorrectionAction.needs_review(
                target_ref=context_id,
                summary="LLM correction output used an unsupported target or operation",
            )

        normalized = {
            "target_ref": self._required_text_field(payload.get("target_ref")),
            "section": self._required_text_field(payload.get("section")),
            "content": self._required_text_field(payload.get("content")),
            "summary": self._required_text_field(payload.get("summary")),
        }
        required_fields = _REQUIRED_FIELDS.get((target_type, operation), ())
        if any(not normalized[field] for field in required_fields):
            return CorrectionAction.needs_review(
                target_ref=context_id,
                summary="LLM correction output was missing required fields",
            )
        confidence = self._validate_confidence(payload.get("confidence"))
        if confidence is None:
            return CorrectionAction.needs_review(
                target_ref=context_id,
                summary="LLM correction output had invalid confidence",
            )

        content = self._optional_text_field(payload.get("content"))
        if target_type == "pattern" and operation == "update_pattern_status":
            try:
                content = normalize_pattern_status(content)
            except ValueError:
                return CorrectionAction.needs_review(
                    target_ref=context_id,
                    summary="LLM correction output had invalid pattern status",
                )

        return CorrectionAction(
            target_type=target_type,
            operation=operation,
            target_ref=normalized["target_ref"],
            section=self._optional_text_field(payload.get("section")),
            content=content,
            summary=normalized["summary"],
            confidence=confidence,
        )

    def _parse_json_object(self, raw_response: str) -> dict[str, Any] | None:
        candidate = raw_response.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) >= 3:
                candidate = "\n".join(lines[1:-1]).strip()

        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            return None

        if not isinstance(decoded, dict):
            return None
        return decoded

    def _validate_confidence(self, value: Any) -> float | str | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            return normalized
        if not isinstance(value, int | float):
            return None
        confidence = float(value)
        if math.isnan(confidence):
            return None
        if confidence < 0.0 or confidence > 1.0:
            return None
        return confidence

    def _required_text_field(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    def _optional_text_field(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

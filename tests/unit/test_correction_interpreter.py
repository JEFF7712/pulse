import asyncio


class FakeLLM:
    def __init__(self, response: str):
        self.calls: list[dict[str, object]] = []
        self._response = response

    async def complete(self, prompt, *, system_prompt=None, model=None):
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": model,
            }
        )
        return self._response


def test_interpreter_returns_valid_profile_action():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        llm = FakeLLM(
            """
            {
              "target_type": "profile",
              "operation": "replace_section",
              "target_ref": "profile",
              "section": "Learned Corrections",
              "content": "Prefer short daily plans over long checklists.",
              "summary": "Update the profile correction notes.",
              "confidence": 0.93
            }
            """
        )
        interpreter = LLMCorrectionInterpreter(llm=llm)

        action = await interpreter.interpret(
            context_id="profile",
            message_text="Please note that I do better with short daily plans.",
            context_payload={"target_type": "profile", "file": "04-Config/profile.md"},
        )

        assert action.target_type == "profile"
        assert action.operation == "replace_section"
        assert action.target_ref == "profile"
        assert action.section == "Learned Corrections"
        assert action.content == "Prefer short daily plans over long checklists."
        assert action.summary == "Update the profile correction notes."
        assert action.confidence == 0.93
        assert len(llm.calls) == 1
        assert "context_id: profile" in llm.calls[0]["prompt"]
        assert "message_text:\n<<<" in llm.calls[0]["prompt"]
        assert (
            "Please note that I do better with short daily plans."
            in llm.calls[0]["prompt"]
        )
        assert ">>>" in llm.calls[0]["prompt"]

    asyncio.run(exercise())


def test_interpreter_returns_review_needed_action_for_invalid_json():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(llm=FakeLLM("not valid json"))

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="That happened in the afternoon, not morning.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.section == ""
        assert action.content == ""
        assert action.confidence == 0.0
        assert action.summary == "LLM correction output could not be parsed"

    asyncio.run(exercise())


def test_interpreter_accepts_fenced_json():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """```json
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The walk happened after lunch.",
                  "summary": "Append a correction note to the daily digest.",
                  "confidence": 0.88
                }
                ```"""
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The walk happened after lunch, not before.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "digest"
        assert action.operation == "append_note"
        assert action.target_ref == "2026-03-27"
        assert action.section == "Corrections"
        assert action.content == "The walk happened after lunch."
        assert action.summary == "Append a correction note to the daily digest."
        assert action.confidence == 0.88

    asyncio.run(exercise())


def test_interpreter_rejects_unsupported_target_or_operation():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "calendar",
                  "operation": "delete_file",
                  "target_ref": "private",
                  "section": "",
                  "content": "",
                  "summary": "Delete the incorrect entry.",
                  "confidence": 0.99
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="ctx-unsupported",
            message_text="Delete that wrong calendar note.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "ctx-unsupported"
        assert (
            action.summary
            == "LLM correction output used an unsupported target or operation"
        )
        assert action.confidence == 0.0

    asyncio.run(exercise())


def test_interpreter_rejects_parseable_json_with_missing_required_fields():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "   ",
                  "summary": "",
                  "confidence": 0.71
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="Please fix the note.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output was missing required fields"
        assert action.confidence == 0.0

    asyncio.run(exercise())


def test_interpreter_rejects_extra_prose_wrapped_around_json():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                "Here is the action you asked for:\n"
                '{"target_type":"digest","operation":"append_note","target_ref":"2026-03-27","section":"Corrections","content":"Wrong time.","summary":"Append correction.","confidence":0.9}'
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event was later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output could not be parsed"

    asyncio.run(exercise())


def test_interpreter_rejects_missing_confidence():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note."
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output had invalid confidence"

    asyncio.run(exercise())


def test_interpreter_accepts_string_confidence_label():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note.",
                  "confidence": "high"
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "digest"
        assert action.operation == "append_note"
        assert action.target_ref == "2026-03-27"
        assert action.confidence == "high"

    asyncio.run(exercise())


def test_interpreter_rejects_empty_string_confidence_label():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note.",
                  "confidence": "   "
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output had invalid confidence"

    asyncio.run(exercise())


def test_interpreter_rejects_boolean_confidence():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note.",
                  "confidence": true
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output had invalid confidence"

    asyncio.run(exercise())


def test_interpreter_rejects_out_of_range_confidence():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note.",
                  "confidence": 1.2
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output had invalid confidence"

    asyncio.run(exercise())


def test_interpreter_rejects_nan_confidence():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": "2026-03-27",
                  "section": "Corrections",
                  "content": "The event happened later.",
                  "summary": "Append a correction note.",
                  "confidence": NaN
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output had invalid confidence"

    asyncio.run(exercise())


def test_interpreter_rejects_non_string_required_text_fields():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "digest",
                  "operation": "append_note",
                  "target_ref": 20260327,
                  "section": ["Corrections"],
                  "content": {"text": "The event happened later."},
                  "summary": 42,
                  "confidence": 0.8
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="2026-03-27",
            message_text="The event happened later.",
            context_payload={"target_type": "digest", "file": "01-Daily/2026-03-27.md"},
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "2026-03-27"
        assert action.summary == "LLM correction output was missing required fields"

    asyncio.run(exercise())


def test_interpreter_accepts_valid_review_needed_action_with_empty_optional_text():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "none",
                  "operation": "needs_review",
                  "target_ref": "pattern:focus-sessions",
                  "section": null,
                  "content": null,
                  "summary": "The correction is ambiguous and needs manual review.",
                  "confidence": 0.42
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="pattern:focus-sessions",
            message_text="This needs a human to review it.",
            context_payload={
                "target_type": "pattern",
                "file": "02-Insights/patterns/focus-sessions.md",
            },
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "pattern:focus-sessions"
        assert action.section == ""
        assert action.content == ""
        assert action.summary == "The correction is ambiguous and needs manual review."
        assert action.confidence == 0.42

    asyncio.run(exercise())


def test_interpreter_accepts_pattern_status_action():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "pattern",
                  "operation": "update_pattern_status",
                  "target_ref": "focus-sessions",
                  "section": "Status",
                  "content": "confirmed",
                  "summary": "Update the pattern status.",
                  "confidence": 0.81
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="pattern:focus-sessions",
            message_text="This pattern is confirmed.",
            context_payload={
                "target_type": "pattern",
                "file": "02-Insights/patterns/focus-sessions.md",
            },
        )

        assert action.target_type == "pattern"
        assert action.operation == "update_pattern_status"
        assert action.target_ref == "focus-sessions"
        assert action.section == "Status"
        assert action.content == "confirmed"
        assert action.summary == "Update the pattern status."
        assert action.confidence == 0.81

    asyncio.run(exercise())


def test_interpreter_rejects_invalid_pattern_status_action_content():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "pattern",
                  "operation": "update_pattern_status",
                  "target_ref": "focus-sessions",
                  "section": "Status",
                  "content": "done",
                  "summary": "Update the pattern status.",
                  "confidence": 0.81
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="pattern:focus-sessions",
            message_text="This pattern is done.",
            context_payload={
                "target_type": "pattern",
                "file": "02-Insights/patterns/focus-sessions.md",
            },
        )

        assert action.target_type == "none"
        assert action.operation == "needs_review"
        assert action.target_ref == "pattern:focus-sessions"
        assert action.section == ""
        assert action.content == ""
        assert action.summary == "LLM correction output had invalid pattern status"
        assert action.confidence == 0.0

    asyncio.run(exercise())


def test_interpreter_system_prompt_advertises_bounded_pattern_statuses():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        llm = FakeLLM(
            """
            {
              "target_type": "pattern",
              "operation": "update_pattern_status",
              "target_ref": "focus-sessions",
              "section": "Status",
              "content": "strengthening",
              "summary": "Update the pattern status.",
              "confidence": 0.81
            }
            """
        )
        interpreter = LLMCorrectionInterpreter(llm=llm)

        await interpreter.interpret(
            context_id="pattern:focus-sessions",
            message_text="This pattern is strengthening.",
            context_payload={
                "target_type": "pattern",
                "file": "02-Insights/patterns/focus-sessions.md",
            },
        )

        system_prompt = llm.calls[0]["system_prompt"]
        assert isinstance(system_prompt, str)
        assert (
            "Allowed pattern status content for update_pattern_status: "
            "emerging | active | strengthening | confirmed | weakening | inactive | invalidated."
            in system_prompt
        )

    asyncio.run(exercise())


def test_interpreter_accepts_routines_replace_section_action():
    async def exercise() -> None:
        from pulse.services.correction_interpreter import LLMCorrectionInterpreter

        interpreter = LLMCorrectionInterpreter(
            llm=FakeLLM(
                """
                {
                  "target_type": "routines",
                  "operation": "replace_section",
                  "target_ref": "routines",
                  "section": "Correction Updates",
                  "content": "Use a shorter shutdown routine.",
                  "summary": "Update routines corrections.",
                  "confidence": 0.77
                }
                """
            )
        )

        action = await interpreter.interpret(
            context_id="routines",
            message_text="Use a shorter shutdown routine.",
            context_payload={
                "target_type": "routines",
                "file": "03-Life/routines.md",
            },
        )

        assert action.target_type == "routines"
        assert action.operation == "replace_section"
        assert action.target_ref == "routines"
        assert action.section == "Correction Updates"
        assert action.content == "Use a shorter shutdown routine."
        assert action.summary == "Update routines corrections."
        assert action.confidence == 0.77

    asyncio.run(exercise())

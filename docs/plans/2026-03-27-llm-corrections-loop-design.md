# LLM Corrections Loop Design

**Date:** 2026-03-27
**Status:** Approved
**Source Context:** `DESIGN.md`, `docs/plans/2026-03-27-v1-full-release-checklist.md`

---

## Goal

Turn Pulse corrections from "stored only" into "stored and applied" while keeping the user experience free-form.

The first release should allow a user to reply naturally to a Telegram message or submit a correction through MCP, have Pulse persist the raw correction, interpret it with an LLM, and then apply only bounded, auditable updates to approved vault targets.

## Why this slice first

The corrections loop is the smallest missing full-v1 gap that fits the existing backend architecture.

Pulse already has:

- correction persistence,
- Telegram reply intake,
- MCP correction intake,
- vault file helpers,
- LLM abstraction.

This design extends those surfaces instead of introducing a mobile app, geofence system, or new push connector family first.

## Product constraints

- Users should be able to reply in natural language.
- The LLM must not receive open-ended file write access.
- The system must preserve the original correction even if application fails.
- Applied changes must remain inspectable and auditable.
- The first release should stay within the current vault structure and backend surfaces.

## Chosen approach

Use an LLM to interpret free-form corrections into a strict, schema-shaped action plan, then apply those actions with deterministic code.

This is intentionally hybrid:

- **LLM for interpretation** of ambiguous human text,
- **deterministic code for execution** of bounded vault changes.

The design explicitly rejects open-ended LLM file editing.

## Supported targets in the first release

The first release allows the interpreter to target only these destinations:

1. `01-Daily/<date>.md` daily digest files
2. `02-Insights/patterns/<slug>.md` pattern files
3. `04-Config/profile.md`
4. `03-Life/routines.md`

Anything outside those targets must be rejected or marked for review.

## Runtime flow

1. Pulse receives a correction from Telegram or MCP.
2. `CorrectionService` stores the raw correction in the existing `corrections` table.
3. Pulse resolves context from `context_id`.
4. Pulse loads the allowed target content for that context.
5. An `LLMCorrectionInterpreter` receives:
   - the raw correction,
   - the context id,
   - target metadata,
   - bounded file content,
   - a prompt that demands strict JSON output.
6. Pulse validates the returned JSON against an internal schema.
7. A deterministic applier executes only approved actions.
8. Pulse records the result in an audit table.

This preserves a clean separation between interpretation and mutation.

## Context model

The correction system needs stronger target routing than it has today.

### Existing contexts

- `YYYY-MM-DD` already identifies morning briefing / daily digest notifications.

### New contexts

- Discovery notifications should start carrying explicit pattern contexts like `pattern:<slug>`.

### Fallback behavior

- Unknown or malformed contexts should not block persistence.
- They should produce an application result of `needs_review` instead of guessing a target.

## Interpreter contract

Add a new corrections interpreter module, likely `src/pulse/services/correction_interpreter.py`.

It should return a small structured payload with fields like:

- `target_type` — `digest`, `pattern`, `profile`, `routines`, `none`
- `operation` — `append_note`, `replace_section`, `update_pattern_notes`, `update_pattern_status`, `needs_review`
- `target_ref` — date slug, pattern slug, or fixed file name
- `content` — bounded patch content or note text
- `summary` — short audit summary
- `confidence` — numeric confidence or label

The interpreter may propose only one action in the first release. Multi-action workflows can be added later if needed.

## File mutation rules

The LLM must not rewrite whole files.

The deterministic applier should support only reserved sections or known metadata slots:

- **Daily digests** — append under a new `## Corrections` section.
- **Pattern files** — update `## User Notes`, and optionally metadata status if the action is explicit and validated.
- **Profile** — write to a reserved section such as `## Learned Corrections`.
- **Routines** — write to a reserved section such as `## Correction Updates`.

Everything else remains untouched.

## Vault memory changes

`VaultMemory` should grow explicit helpers for bounded section operations, for example:

- ensure a named section exists,
- replace a named section,
- append a bullet or paragraph to a named section,
- update pattern notes without disturbing user-authored content.

These helpers become the only file-writing boundary for correction application.

## Config and model selection

Add a dedicated corrections LLM role to config.

Resolution order:

1. `llm.corrections`
2. `llm.discovery`
3. legacy `PULSE_ANTHROPIC_API_KEY`

This keeps corrections configurable without forcing a brand-new provider choice.

## Audit and persistence

Keep the existing `corrections` table unchanged for raw user input.

Add a new `correction_applications` table to record application outcomes, including:

- `id`
- `correction_id`
- `status` (`applied`, `skipped`, `needs_review`, `failed`)
- `target_type`
- `target_ref`
- `operation`
- `summary`
- `error_message`
- `created_at`
- `updated_at`

This keeps correction storage immutable while making application outcomes visible.

## Failure behavior

- **No corrections LLM configured** — store the correction, record `skipped`.
- **Unknown context** — store the correction, record `needs_review`.
- **Malformed or invalid LLM output** — store the correction, record `needs_review`.
- **Target file missing or unsupported action** — store the correction, record `needs_review` or `failed` depending on the error class.
- **Successful bounded write** — record `applied`.

The core rule is that the original correction is never lost.

## Testing strategy

### Unit tests

- config and provider resolution for `llm.corrections`
- interpreter output parsing and validation
- vault section helpers
- pattern-note and reserved-section updates

### Integration tests

- Telegram reply stores and applies a correction to a daily digest
- Telegram reply against `pattern:<slug>` updates that pattern file
- MCP `pulse_correct` follows the same store-and-apply path
- missing model configuration stores but does not apply
- invalid LLM output records review-needed status

## Non-goals for this slice

- companion app work
- geofence or location ingestion
- health data ingestion
- open-ended vault rewriting
- autonomous correction side effects outside the approved vault files

## Result

After this slice, Pulse will move from passive correction logging to an auditable correction-application loop with natural-language UX and bounded writes.

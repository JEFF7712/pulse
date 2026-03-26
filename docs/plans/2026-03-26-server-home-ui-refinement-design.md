# Server Home UI Refinement Design

**Date:** 2026-03-26
**Status:** Approved
**Source Context:** `src/pulse/app/homepage.py`, `site/index.html`

---

## Goal

Refine the server homepage at `/` so it feels more functional and less verbose while adding a subtle pulse animation borrowed from the marketing site.

The page should work as a compact operational surface, not a narrative landing page.

## Approach

Keep the existing server-rendered HTML route and inline CSS structure, but simplify the visible content to a single compact block. Remove the overview copy and descriptive cards, and keep only the smallest amount of framing text needed to orient an operator.

Add only one motion system: slow expanding pulse rings with a soft center-dot glow inspired by `site/index.html`. The motion should stay ambient and low-distraction rather than theatrical.

## Information Architecture

The page should present only these visible items:

- `Pulse`
- `server online`
- `self-hosted node`
- `/health`
- `POST /webhooks/telegram`

No explanatory paragraphs or secondary overview section should remain.

## Visual Direction

- Keep the dark black/cream/green palette already established
- Preserve the serif headline and mono utility text pairing
- Keep the page centered and compact
- Let the pulse rings provide most of the visual energy
- Avoid extra labels, stats, or descriptive cards

## Motion

Adopt the restrained pulse treatment from `site/index.html`:

- expanding concentric rings behind the mark,
- a softly pulsing center dot,
- no entrance choreography,
- no motion on the endpoint list itself.

The result should read as active but calm.

## Runtime Behavior

- `/health` remains a clickable operator link
- Telegram webhook remains shown as `POST /webhooks/telegram` text only
- The page stays static HTML with inline CSS and no JavaScript requirement

## Testing Strategy

Update the existing root route integration test so it reflects the stripped-down functional homepage.

- Keep assertions for `Pulse`, `server online`, and `/health`
- Keep the assertion that `/webhooks/telegram` is not rendered as a clickable link
- Remove dependence on the old explanatory prose
- Add a stable assertion for the retained minimal descriptor, `self-hosted node`

Visual animation itself does not need browser automation coverage; it is sufficient to verify the HTML surface and key strings.

## Success Criteria

The refinement is successful when:

1. the homepage is visibly more compact and functional,
2. most descriptive text is removed,
3. the pulse motif is subtly animated,
4. `/health` remains clickable and `POST /webhooks/telegram` remains plain text,
5. the focused integration tests still pass.

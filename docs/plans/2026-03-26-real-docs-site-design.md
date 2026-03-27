# Real Docs Site Design

**Date:** 2026-03-26
**Status:** Approved
**Reference:** `https://docs.openclaw.ai/`

---

## Goal

Turn Pulse documentation into a real docs experience served under `/docs/`, with repo markdown as the source of truth.

The target experience is closer to a docs product like OpenClaw's docs site than to a simple landing page: structured navigation, a dedicated docs homepage, readable content pages, and stable internal docs routes.

## Problem

The current docs work is split between useful markdown content and a lightweight static `/docs` portal concept.

- The markdown docs are becoming useful for operators, but they are not yet presented as a navigable docs site.
- The current site architecture is optimized for a single marketing page, not a true documentation experience.
- Linking out to GitHub is acceptable as a stopgap, but it does not satisfy the goal of a first-class docs product.

## Approved Product Direction

Pulse should have a dedicated docs experience under `/docs/`.

- `/` remains the marketing/product homepage.
- `/docs/` becomes the docs homepage.
- `/docs/...` child routes become the primary way users read Pulse documentation.
- Repo markdown remains the source of truth for the docs content.

This keeps content authoring simple while upgrading presentation, navigation, and discoverability.

## Information Architecture

The first version of the docs site should stay focused on self-hosted operators.

### Core pages

- `docs/index.md` - docs homepage
- `docs/self-hosting/quickstart.md` - first-run setup path
- `docs/reference/configuration.md` - config and env reference
- `docs/operations/runbook.md` - operating and troubleshooting Pulse
- `docs/connectors/index.md` - connector setup and caveats

### Docs homepage behavior

`docs/index.md` should act as a true docs front door.

It should include:

- a short framing section explaining what Pulse is,
- quickstart-oriented entry cards,
- a practical first path into setup,
- links into the core docs groups.

This page should feel like a product manual homepage rather than a file index.

### Navigation shape

The docs site should expose a stable sidebar or equivalent structured navigation with these top-level sections:

- Home
- Self-Hosting
- Configuration
- Operations
- Connectors

The navigation should be generated from a small amount of explicit metadata, not hard-coded across many HTML files.

## Implementation Direction

Use a real docs generator on top of repo markdown.

### Why this approach

This approach best satisfies the requirements:

- repo markdown stays canonical,
- docs pages render into a docs-native UI,
- navigation and layout are handled by the docs system,
- the site gains a real `/docs/` section without hand-maintaining every page.

### Preferred architecture

Introduce a dedicated docs app or docs workspace alongside the existing static site.

- The current `site/` root marketing page remains lightweight.
- A docs build system reads from `docs/` and produces static output for `/docs/`.
- The generated docs output is published with the rest of the site.

This avoids forcing the current handwritten `site/index.html` setup to become a custom docs framework.

### Content source of truth

The repo markdown under `docs/` is authoritative.

- Editing docs should continue to mean editing markdown files in this repository.
- The docs system may use a small config file, frontmatter, or navigation metadata to define grouping and ordering.
- The docs site should not become a second independent content store.

## Visual Direction

The docs site should share the Pulse visual identity without copying the marketing homepage literally.

### Shared identity

- dark background treatment,
- cream body text,
- green accent,
- serif display typography,
- mono support/body typography,
- subtle texture and restrained motion.

### Docs-specific adjustments

- tighter reading layout,
- denser information hierarchy,
- stable navigation chrome,
- lower visual drama than the landing page,
- clear heading rhythm and code-block readability.

The goal is "same product family, different reading mode."

## Migration Strategy

Migrate incrementally rather than rewriting everything.

### Phase 1

- keep the current markdown docs,
- add a docs homepage in markdown,
- wire the docs generator,
- publish real docs routes,
- replace the temporary static `/docs` portal with the generated docs experience.

### Phase 2

- refine navigation,
- improve docs homepage content and section intros,
- add contributor docs later if needed.

The first milestone is a usable docs site, not a maximal docs platform.

## Out of Scope for First Version

- docs versioning,
- blog/news content,
- API reference generation,
- contributor documentation overhaul,
- a custom-built docs frontend from scratch.

These can be considered later if the docs surface grows.

## Testing and Verification

The implementation should verify both content and delivery.

### Content checks

- required docs pages exist,
- docs homepage includes expected entry points,
- navigation includes the expected top-level sections,
- key routes render the intended markdown content.

### Site checks

- `/` still serves the marketing site,
- `/docs/` serves the docs homepage,
- key child routes under `/docs/` return `200`,
- packaging/build steps include the docs output.

### Stability goal

Tests should validate the real built site, not a mocked or alternate path.

## Success Criteria

The work is successful when:

1. Pulse has a real docs site under `/docs/`,
2. repo markdown remains the source of truth,
3. users can navigate the docs without leaving the site,
4. the docs homepage feels like a real product manual,
5. the main marketing homepage remains intact.

## Notes

- This design intentionally moves beyond the earlier GitHub-linked `/docs` portal.
- I did not create a git commit for this design doc because you have not asked for one.

# Server Home UI Design

**Date:** 2026-03-26
**Status:** Approved
**Source Context:** `README.md`, `DESIGN.md`, `site/index.html`, `src/pulse/app/main.py`

---

## Goal

Add a very simple UI to the FastAPI server at `/` so the root URL feels intentional and useful when Pulse is running locally.

The page should act as an operator-facing home screen, not a marketing landing page. It should immediately communicate that Pulse is alive on this machine, what the service does, and where a developer can go next.

## Approach

Implement `/` as a server-rendered HTML page returned directly by the FastAPI app. The page should be static in structure and copy, with no frontend framework and little to no JavaScript.

Visually, the page should borrow the tone of `site/index.html`: dark background, cream text, green accent, serif headline plus mono support text, pulse-ring motif, and restrained motion. The runtime homepage should be much smaller and more practical than the full site.

## Information Architecture

The page should contain three compact sections.

### 1. Hero

- Pulse name and a short product line
- One sentence that frames Pulse as a self-hosted, push-first personal intelligence agent
- A compact status chip such as "server online"

### 2. Operator Overview

- Short explanation of the core local loop: events, analysis, vault, notifications
- A few small cards that summarize what this server is for
- Copy should stay tight and technical enough for a local operator

### 3. Useful Endpoints

- Link to `/health`
- Reference the Telegram webhook path at `/webhooks/telegram`
- Present these as operational entry points, not product features

## Visual Direction

The page should keep the visual DNA from `site/index.html` while simplifying it for the app server.

- **Palette:** reuse the black, cream, dim, and green accent family
- **Typography:** keep the serif + mono pairing from the site
- **Motion:** one subtle pulse-ring background treatment is enough
- **Density:** fewer sections, less copy, smaller layout footprint than the site
- **Responsiveness:** stack cleanly on mobile and avoid decorative clutter in narrow viewports

## Implementation Shape

Keep the FastAPI route lightweight.

- Add a new `GET /` route in `src/pulse/app/main.py`
- Return an `HTMLResponse`
- Move the HTML generation into a small helper module such as `src/pulse/app/homepage.py` so `main.py` stays readable
- Use inline CSS inside the rendered document to avoid introducing a static asset pipeline for this one page

## Error Handling And Runtime Behavior

The homepage should not depend on the database, connector registry, or external services. It should render successfully even if the rest of the system is minimally configured.

Links may point to routes that are not human-browsable or are POST-only, but the copy should make that clear.

## Testing Strategy

Cover the new behavior with a focused integration test.

- `GET /` returns `200`
- response content type includes `text/html`
- response body includes stable strings such as `Pulse`, `server online`, and `/health`

This keeps the test tied to behavior rather than to brittle visual details.

## Success Criteria

The change is successful when:

1. visiting `/` in the running server shows a readable, styled homepage,
2. the page visibly matches the aesthetic direction of `site/index.html`,
3. the root route remains simple and has no extra frontend toolchain,
4. automated tests prove the route returns the expected HTML shell.

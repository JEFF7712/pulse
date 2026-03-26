# Self-Hosted Docs and Site Docs Portal Design

**Date:** 2026-03-26
**Status:** Approved
**Source Context:** `README.md`, `DESIGN.md`, `src/pulse/app/cli.py`, `src/pulse/app/config.py`, `src/pulse/app/config_loader.py`, `site/index.html`, `site/nginx.conf`

---

## Goal

Create an operator-first documentation set for self-hosted Pulse users, then add a `/docs` page on the marketing site that serves as a clean entry point into those docs.

The docs should help a new self-hosting user get Pulse running quickly, understand how to configure and operate it, and know where to go when something breaks.

## Problem

Pulse already has strong architecture and planning documentation, but the day-1 user workflow is under-documented.

- `README.md` explains the product and repo layout well, but it does not cover the real CLI-driven operator flow end to end.
- The implementation in `src/pulse/app/cli.py` exposes significantly more functionality than the current docs surface.
- Config documentation has drift relative to the live config model.
- The site has no `/docs` route, so there is no obvious web entry point for documentation.

## Approved Approach

Use a quickstart-first documentation structure in the repo and keep the site docs page lightweight.

- The repo remains the source of truth for operational documentation.
- The new docs focus on task completion rather than architecture explanation.
- The site `/docs` page acts as a polished portal into the repo docs rather than duplicating them.

This keeps onboarding clear, reduces long-term doc drift, and matches the current implementation maturity of the project.

## Documentation Information Architecture

### 1. `README.md` as the front door

Keep `README.md` concise and product-oriented.

- Explain what Pulse is and how it works at a high level.
- Keep minimal setup instructions for cloning, installing, and testing.
- Add clear links to the new operator docs so users can move into the right workflow immediately.

`README.md` should stop short of being the entire operator manual.

### 2. Self-hosted quickstart

Add a primary operator guide at `docs/self-hosting/quickstart.md`.

This page should optimize for first success on a local machine and follow the real CLI happy path:

1. install the package,
2. copy and edit `.env`,
3. review and edit `pulse.toml`,
4. run auth flows such as `pulse auth google` and `pulse auth spotify`,
5. initialize storage and vault state,
6. start Pulse,
7. verify the service is healthy and doing useful work.

The tone should be practical, direct, and user-facing.

### 3. Configuration reference

Add `docs/reference/configuration.md` as the source of truth for runtime configuration.

This doc should explain:

- supported environment variables,
- what belongs in `.env` versus `pulse.toml`,
- connector configuration structure,
- where token files are written,
- how database and vault paths are resolved,
- any current limitations or implementation nuances that matter to operators.

This page should be grounded in the live config code rather than in aspirational design text.

### 4. Operations runbook

Add `docs/operations/runbook.md` to cover operating and recovering a running Pulse instance.

This page should answer:

- how to tell whether Pulse is healthy,
- what scheduled jobs exist,
- how to inspect status, logs, and insights,
- how Telegram corrections and webhook handling work,
- what to do when auth, ingestion, or scheduling is not behaving as expected,
- which reset and re-initialization commands are safe to use.

The runbook should be written for operators rather than contributors.

### 5. Connector setup guide

Add `docs/connectors/index.md` with short, focused sections for currently meaningful integrations.

Initial sections should cover:

- Google connectors,
- Spotify,
- browser history.

This content should explain prerequisites, setup steps, what data Pulse pulls, and any notable caveats. It should stay shorter than the full config reference and serve as a task-oriented companion to the quickstart.

## Site `/docs` Page

Add a static docs landing page at `site/docs/index.html`.

### Purpose

The page should introduce the documentation set, explain who it is for, and route visitors to the right starting point.

It should not duplicate the full docs corpus or try to become a second documentation system.

### Structure

The page should include:

1. a compact hero that frames the docs as the self-hosting manual for Pulse,
2. audience or task entry points such as Run Pulse, Configure Pulse, Operate Pulse, and Connect Data Sources,
3. a short context section that explains what Pulse actually does,
4. direct links to the repo-authored docs.

### Visual Direction

The page should stay within the visual family of `site/index.html` while feeling calmer and more utilitarian.

- Reuse the dark, cream, and green palette.
- Reuse the serif headline and mono support typography.
- Keep motion subtle.
- Prefer readable layout density over dramatic landing-page composition.

### Routing and Hosting Shape

Because the site is currently a static nginx-served page, the cleanest solution is a real static route:

- create `site/docs/index.html`,
- ensure the Docker image copies the docs directory,
- rely on the existing nginx `root` plus directory-based path handling so `/docs/` resolves naturally.

No frontend framework or routing layer is needed.

## Content Principles

All new docs should follow these principles:

- prefer operator tasks over architecture exposition,
- document the implemented system rather than the aspirational one,
- keep examples concrete and command-driven,
- make file paths and runtime artifacts explicit,
- keep the site summary light and the repo docs authoritative.

## Expected File Changes

The implementation is expected to touch at least these areas:

- `README.md`
- `docs/self-hosting/quickstart.md`
- `docs/reference/configuration.md`
- `docs/operations/runbook.md`
- `docs/connectors/index.md`
- `site/docs/index.html`
- `site/Dockerfile`
- `site/tests/static-site-smoke.sh`

## Testing Strategy

Documentation work should still be verified.

### Repo docs

- check that all new doc links resolve,
- ensure command examples match real CLI commands,
- verify documented config fields against the implementation in the config loader and CLI.

### Site docs page

- verify the static site image still builds,
- verify `/` still serves correctly,
- extend smoke coverage to verify `/docs/` serves and contains stable, meaningful markers,
- keep tests focused on user-visible content rather than brittle layout details.

## Success Criteria

The change is successful when:

1. a new self-hosted user can follow the repo docs to get Pulse running without reading design documents,
2. the docs accurately reflect the implemented CLI and configuration model,
3. the site exposes a clean `/docs` entry point without introducing a new frontend stack,
4. doc and site smoke checks provide confidence that the experience remains intact.

## Notes

- The repo docs are the authoritative source; the site docs page is a navigation layer.
- I did not create a git commit for this design doc because you have not asked for one.

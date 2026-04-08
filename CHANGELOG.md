# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.1] - 2026-04-08

### Fixed

- **Release Docker image:** root `Dockerfile` copies `dist/` and installs the latest `pulse_agent-*.whl` (the previous `build-arg` + `COPY` glob produced an invalid wheel path in CI).
- **Site smoke test:** assert the current homepage line (“unique and actionable insights”).
- **Site Docker workflow YAML:** restore valid `on:` / `permissions:` structure.

### Added

- [PyPI trusted publishing](docs/operations/pypi-trusted-publishing.md) operator note (configure PyPI for tag-based `release-publish.yml`).

## [2.0.0] - 2026-04-08

### Removed (breaking)

- Daily digest pipeline (scheduled job, CLI `digest`, MCP digest tools, vault `01-Daily` output, digest-only modules).
- Morning briefing scheduled job.
- Companion HTTP routes `GET /api/digests/latest` and `GET /api/digests/{date}`.
- Correction targets that are only a calendar date (`YYYY-MM-DD`); use `pattern:slug`, `profile`, or `routines`.

### Added

- MCP tools `pulse_discovery`, `pulse_insights`, and `pulse_read_pattern`.
- Companion HTTP `GET /api/insights` and `GET /api/insights/{id}` (pattern metadata and markdown body).
- Hardened discovery response parsing (noisy JSON extraction, partial apply, optional repair completion).
- Canonical `event_type` registry (`src/pulse/domain/event_types.py`) for connector alignment.

### Fixed

- E2E operator-flow test targets `/actions/discover` when no LLM is configured (digest route removed).

### Changed

- Config key `summarization_model_for_digest` renamed to `summarization_model_for_source_summaries`.
- Plaid and event payloads prefer `omit_amounts_in_summary` / `omit_amount_in_summary` (legacy digest-era keys still accepted).
- Flutter companion app loads patterns via the new insights API and sends corrections with `pattern:{id}` contexts.

## [1.0.0] - 2026-04-08

First stable release of **Pulse** (`pulse-agent` on PyPI).

### Added

- **CLI** — `pulse configure` (hub-style menus for core, connectors, notifications, and model settings), `pulse onboard` (walkthrough plus connector auth), `pulse init` (vault profile, initial pulls, discovery when configured), `pulse run`, `pull`, `discover`, `status`, `insights`, `logs`, and related commands.
- **Connectors** — Pluggable sources (e.g. Gmail, Calendar, YouTube, Spotify, Microsoft 365, GitHub, GitLab, Linear, Notion, Plaid, browser history, RSS/Atom, Oura) with OAuth / token flows where applicable.
- **Event store** — SQLite-backed events and sync cursors.
- **Vault** — Obsidian-compatible markdown output (insights, profile scaffolding).
- **Notifications** — Multiple channels (Telegram, ntfy, webhooks, Discord, Slack, Pushover, Gotify, SMTP, companion/FCM, and related configuration).
- **LLM** — Configurable providers and roles for summarization, discovery, and corrections; MCP-oriented tooling where documented.
- **MCP server** — `pulse-mcp` for agent integration (tools and resources as documented in the README).
- **Distribution** — PyPI package, Docker image workflow, and install script documented for self-hosting.

### Notes for operators

- Configuration lives primarily in **`pulse.toml`** (with `PULSE_*` and documented API key env overrides). See `pulse.toml.example` and the self-hosting quickstart.
- **Breaking changes** after 1.0 will be called out in this file and reflected in semver (MAJOR for incompatible behavior or config schema changes, MINOR for backward-compatible features, PATCH for fixes).

[2.0.1]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.1
[2.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.0
[1.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v1.0.0

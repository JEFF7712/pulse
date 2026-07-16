# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.1.0] - 2026-07-16

### Added

- **Optional proactive review:** on a schedule, Pulse invokes your own agent headless (default `claude -p`) to review recent data and delivers the result to your notification channel. Configured via `[proactive]` (off by default); run on demand with `pulse review`. Uses your agent subscription, not an API key.

### Removed

- Dead insight-storage left over from the removed discovery engine: the `insights` table and `AnalyticsRepository.upsert_insight`/`get_insight`/`delete_insights`/`list_insights`, plus the unused `insights_panel` CLI helper.

## [3.0.0] - 2026-07-16

Pulse is refocused as an **MCP-first personal-data context layer**: it ingests a curated set of
high-signal sources and exposes them to your own agent, which does the reasoning. Pulse no longer
calls an LLM and needs no LLM API key. This is a breaking release; the mobile companion app, the
built-in discovery/corrections engines, and several connectors are removed.

### Added

- **MCP context surface:** `pulse_query_events` (range/source/text, paginated, trimmed), `pulse_digest` (deterministic day rollup), `pulse_coverage`, and vault-memory tools (`pulse_vault_read`/`list`/`write`/`append_section`), plus `pulse://digest/today`, `pulse://coverage`, `pulse://vault/index` resources.
- **Agent skills** (`skills/`): `pulse-review` and `pulse-recall`.
- **NixOS module** (`nixosModules.default`): systemd service for `pulse run`.
- **Tier-1 ingest normalization:** deterministic, lossless stripping of URL tracking params and zero-width characters at ingest.
- **Optional local semantic search** (`pip install pulse-agent[semantic]`, [model2vec](https://github.com/MinishLab/model2vec)) behind `[semantic] enabled`; `pulse embed` backfills embeddings and `pulse_query_events(text=...)` then ranks by similarity. Off by default; no new base dependencies.

### Removed

- **Mobile companion app:** the Flutter `companion_app/`, its connector, REST API, token auth, and the FCM push / device-token store (all mobile-only).
- **Low-yield connectors:** Microsoft mail & calendar, GitLab, RSS feeds, Linear, Notion (duplicates of, or lower-signal than, the retained sources).
- **Bespoke analysis/discovery engine:** the LLM discovery pipeline, prompts, and source/event summarizers.
- **LLM-powered corrections subsystem:** the corrections service, interpreter, webhook, and stores (a feedback loop for the removed discovery engine).
- **LLM provider layer:** the entire `pulse/llm/` (Anthropic/OpenAI/Gemini) surface, the `[llm]` config roles, LLM API-key settings, and the `anthropic` / `feedparser` dependencies.
- **Reasoning-era MCP tools:** `pulse_discovery`, `pulse_insights`, `pulse_read_pattern`, `pulse_correct`.

### Changed

- **Connectors** curated to a core spine (Gmail, Calendar, GitHub, Browser) enabled by default, with Spotify, YouTube, Plaid, and Oura available but off by default.
- **`pulse discover`** is now aggregation-only (deterministic daily stats), with no LLM step.
- **Nix flake** drops the Flutter/JDK companion devShell.

## [2.0.3] - 2026-04-10

### Added

- **Docker:** Multi-stage root `Dockerfile` — builds the `pulse_agent` wheel with **uv** inside the image (clone-only `docker build`, no local `dist/`).
- **`compose.yaml`** at repo root for `docker compose up --build` (port 8000, named volumes for config and data).
- **CI:** `release-publish.yml` publishes the app image to **GitHub Container Registry** (`ghcr.io/<owner>/<repo>`, lowercase) on `v*` tags, with semver and `latest` tags via `docker/metadata-action`.
- **Docs:** Docker pull/run, first-time `pulse onboard` / `pulse configure`, Compose, GHCR auth, and volume lifecycle in [self-hosting quickstart](docs/self-hosting/quickstart.md) and **README** Install section.

### Changed

- **Release workflow:** `publish-docker` no longer downloads the `dist` artifact for the image build; the Docker build produces the wheel in a builder stage (PyPI publish still uses the same tested artifact as before).

### Fixed

- **Release workflow:** Docker job now logs in to GHCR, sets image metadata, and **pushes** the image (previously ran `build-push-action` without `push` or registry tags).

### Developer

- **`.gitignore`:** `build/` and `dist/` for local setuptools / `uv build` outputs.

## [2.0.2] - 2026-04-09

### Added

- **`pulse internal-install`** — Rich output hook for the curl installer (`ready` / `noninteractive` phases).
- **Install script (`scripts/install.sh`):** CLI-aligned colors/banner, step labels, quieter `pipx install`, automatic **`pulse onboard`** when a TTY is available (including **`curl | bash`** via `/dev/tty` when possible).

### Fixed

- **Google OAuth on headless / SSH:** retry without auto-opening a browser; optional ports via `PULSE_GOOGLE_OAUTH_PORT`, `PULSE_GOOGLE_OAUTH_FALLBACK_PORT`, `PULSE_OAUTH_NO_BROWSER` (see [configuration reference](https://pulseagent.dev/docs/reference/configuration.html)).

### Changed

- **CLI:** `pulse.app.cli` logic split into a `pulse.app.commands` subpackage (behavior preserved; easier navigation).

## [2.0.1] - 2026-04-08

### Fixed

- **Release Docker image:** root `Dockerfile` copies `dist/` and installs the latest `pulse_agent-*.whl` (the previous `build-arg` + `COPY` glob produced an invalid wheel path in CI).
- **Site smoke test:** assert the current homepage line (“unique and actionable insights”).
- **Site Docker workflow YAML:** restore valid `on:` / `permissions:` structure.

### Added

- [PyPI trusted publishing](https://pulseagent.dev/docs/operations/pypi-trusted-publishing.html) operator note (configure PyPI for tag-based `release-publish.yml`).

## [2.0.0] - 2026-04-08

### Removed (breaking)

- Scheduled per-day vault markdown pipeline (job, CLI subcommand, MCP tools, vault day-folder output, related-only modules).
- Morning briefing scheduled job.
- Companion HTTP routes for latest and date-keyed per-day vault markdown.
- Correction targets that are only a calendar date (`YYYY-MM-DD`); use `pattern:slug`, `profile`, or `routines`.

### Added

- MCP tools `pulse_discovery`, `pulse_insights`, and `pulse_read_pattern`.
- Companion HTTP `GET /api/insights` and `GET /api/insights/{id}` (pattern metadata and markdown body).
- Hardened discovery response parsing (noisy JSON extraction, partial apply, optional repair completion).
- Canonical `event_type` registry (`src/pulse/domain/event_types.py`) for connector alignment.

### Fixed

- E2E operator-flow test targets `/actions/discover` when no LLM is configured (legacy per-day route removed).

### Changed

- Source summarization model setting renamed to `summarization_model_for_source_summaries` (legacy key no longer read).
- Plaid and event payloads prefer `omit_amounts_in_summary` / `omit_amount_in_summary` (legacy alternate keys still accepted).
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

[Unreleased]: https://github.com/JEFF7712/pulse/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v3.0.0
[2.0.3]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.3
[2.0.2]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.2
[2.0.1]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.1
[2.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v2.0.0
[1.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v1.0.0

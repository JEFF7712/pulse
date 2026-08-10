# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The scheduled daily review is replaced by **change-triggered pattern discovery**. The old
design woke a cold agent every morning with one day of data and pushed whatever prose came
back. A day is too short a window for a pattern to exist in, and the agent had no access to
what it had already concluded, so the only thing it could reliably produce was a restatement
of the day — or a manufactured connection between unrelated events. Both halves are inverted:
a deterministic check decides *whether* to wake an agent, and recorded vault state decides
*whether to notify*.

### Added

- **`pulse_change_surface` (MCP tool) and the change-surface layer.** Deterministic, no LLM.
  Reports entities that are new, returning after dormancy, or well off their usual rate versus
  the user's own trailing baseline, plus clusters of events whose embeddings sit far from
  anything in that baseline. The embedding lane is shape-agnostic: it can surface a kind of
  activity no rule was written for. An empty surface is a normal result and means no agent runs.
- **Pattern tools over MCP:** `pulse_pattern_list`, `pulse_pattern_read`, `pulse_pattern_upsert`,
  `pulse_pattern_set_status`. `VaultMemory` had a full pattern lifecycle (evidence merging,
  confidence, status, archiving) that was never exposed, so an agent had no way to know what it
  had already recorded. It does now.
- **Novelty gate on pattern writes.** `pulse_pattern_upsert` rejects a proposal too similar to an
  existing pattern (duplicate) and an update that merely restates the current observation
  (restatement), using the local embedder when present and token overlap otherwise.
- **`[discovery]` config** replacing `[proactive]`, with `window_days` (default 7 — a pattern needs
  repetition) and `baseline_days` (default 56).
- **Scheduled embedding job.** `pulse embed` was a manual one-off backfill with nothing keeping it
  current, so every event ingested after the last manual run was unembedded — including the recent
  events any discovery pass is about. With `[semantic]` and `[discovery]` enabled, embeddings now
  refresh every 6 hours.

### Changed

- **Notifications are derived from vault state, not agent output.** After a discovery run Pulse
  diffs recorded patterns and notifies only on a genuine create or material change. An agent that
  produces pages of prose and records nothing now produces silence. The volatile `Last updated`
  field is excluded from the comparison so a re-save is not mistaken for a change.
- **`pulse review`** forces a discovery pass (bypassing the change gate) rather than running a
  daily review.
- **Browsing entities keep their full host**, with same-status siblings collapsed under one
  registrable domain. `parchment.com` + `auth.parchment.com` + `registration.parchment.com` going
  new together report as one finding, while a genuinely new subdomain of a site whose parent is not
  new still stands on its own.
- **`pulse-review` skill** rewritten for discovery: start from what changed rather than from a
  digest, check against recorded patterns, and record nothing when nothing is new.

### Fixed

- **Weekly baselines were never refreshed.** `aggregate_day` updated daily stats and time blocks but
  not `weekly_baselines`, so on a live install the table stopped four months before the current day
  and every "versus normal" comparison ran against stale numbers. It now refreshes the containing
  ISO week.
- **Transactional email was classified as promotional.** The digest treated every Gmail category
  except `primary` as bulk, so payment confirmations and bank security notices were binned
  alongside marketing. `updates` now falls through to the sender heuristic; on a real inbox this
  moved a $1,500 payment notice and a bank contact-change alert from "promotional" to signal.
- **GitHub pushes always reported "0 commits".** The user events feed omits or truncates
  `payload.commits`; the authoritative count is `payload.size`.
- **Calendar expanded recurring events without bound.** `singleEvents=True` with no `timeMax`
  materialised one instance per year out to 2055, burying the real calendar and pinning
  `pulse_coverage`'s `last_event` three decades in the future. Both the incremental and resync paths
  are now capped at a 180-day horizon.

### Removed

- **`[proactive]` config and the scheduled daily review.** Pulse now fails to start with a migration
  message if the section is still present, rather than silently ignoring it and leaving the user
  believing a review is configured. Rename to `[discovery]`; `command`, `prompt`, `at` and
  `timeout_seconds` carry over.
- **Cross-source co-occurrence links.** Pairing same-day entities is a cartesian product: on real
  data it produced 565 "links" for one week, none meaningful. Deciding that two changes are related
  is interpretation, and that is the agent's job.

## [3.1.1] - 2026-07-16

### Fixed

- **Browser pulls crashed** on real history: the Tier-1 URL normalizer raised `ValueError: Invalid IPv6 URL` on any URL with an unmatched `[`, aborting the entire pull batch. Normalization is now lossless-or-identity and never raises. (Affected the highest-volume connector in 3.0.0–3.1.0.)
- **GitHub connector returned 404**: it requested `/user/events` (not a real endpoint). It now resolves the authenticated login and pulls from `/users/{login}/events`.
- **Browsing time estimates were inflated**: the digest summed inter-visit gaps as on-site time, so domains revisited across the day (e.g. Google) reported hours instead of minutes. Time is now sessionized, gaps beyond a session threshold count only a small dwell.

### Added

- **Email signal/noise separation in the digest**: the Gmail connector captures Gmail's own category (`primary`/`promotions`/`social`/`updates`/`forums`), and `EventPreprocessor` flags promotional/bulk threads (`is_promotional`, with a sender heuristic fallback for mail ingested before categories), sorting real correspondence first.

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

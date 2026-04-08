# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-08

First stable release of **Pulse** (`pulse-agent` on PyPI).

### Added

- **CLI** — `pulse configure` (hub-style menus for core, connectors, notifications, and model settings), `pulse onboard` (walkthrough plus connector auth), `pulse init` (vault profile, initial pulls, discovery when configured), `pulse run`, `pull`, `digest`, `discover`, `status`, `insights`, `logs`, and related commands.
- **Connectors** — Pluggable sources (e.g. Gmail, Calendar, YouTube, Spotify, Microsoft 365, GitHub, GitLab, Linear, Notion, Plaid, browser history, RSS/Atom, Oura) with OAuth / token flows where applicable.
- **Event store** — SQLite-backed events and sync cursors.
- **Vault** — Obsidian-compatible markdown output (digests, insights, profile scaffolding).
- **Notifications** — Multiple channels (Telegram, ntfy, webhooks, Discord, Slack, Pushover, Gotify, SMTP, companion/FCM, and related configuration).
- **LLM** — Configurable providers and roles for summarization, discovery, and corrections; MCP-oriented tooling where documented.
- **MCP server** — `pulse-mcp` for agent integration (tools and resources as documented in the README).
- **Distribution** — PyPI package, Docker image workflow, and install script documented for self-hosting.

### Notes for operators

- Configuration lives primarily in **`pulse.toml`** (with `PULSE_*` and documented API key env overrides). See `pulse.toml.example` and the self-hosting quickstart.
- **Breaking changes** after 1.0 will be called out in this file and reflected in semver (MAJOR for incompatible behavior or config schema changes, MINOR for backward-compatible features, PATCH for fixes).

[1.0.0]: https://github.com/JEFF7712/pulse/releases/tag/v1.0.0

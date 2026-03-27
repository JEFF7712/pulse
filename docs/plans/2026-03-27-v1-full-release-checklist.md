# V1 Full Release Checklist

**Date:** 2026-03-27
**Scope:** Compare the current repository state to the broader full-v1 scope in `DESIGN.md`, not just the narrower backend/operator milestone reflected in `README.md` and `tests/e2e/test_backend_first_mvp.py`.

---

## Current verdict

Pulse looks close to a solid backend/operator release, but it is not yet ready for the original full-v1 product scope described in `DESIGN.md`.

The backend foundations are in good shape: the repo is on `main`, `uv run pytest` passes, and the standalone app, MCP server, SQLite store, digest pipeline, Telegram delivery, and pull connector stack are all real.

The biggest gap between the current codebase and the full-v1 vision is the missing mobile/location side of the product: companion app, location ingestion, geofences, health data, and richer correction workflows.

---

## Done

- [x] Core event store and persistence layer exist in `src/pulse/store/schema.py`, `src/pulse/store/events.py`, and `src/pulse/store/sync_state.py`.
- [x] Standalone backend surface exists: CLI, onboarding/auth flows, FastAPI app, homepage, scheduler, and health endpoint in `src/pulse/app/cli.py`, `src/pulse/app/main.py`, and `src/pulse/jobs/scheduler.py`.
- [x] Daily digest generation works and writes markdown to the vault via `src/pulse/jobs/runners.py` and `src/pulse/vault/writer.py`.
- [x] Morning briefing delivery exists through Telegram in `src/pulse/jobs/runners.py`, `src/pulse/analysis/briefing.py`, and `src/pulse/notifications/telegram.py`.
- [x] Google OAuth plus Gmail and Google Calendar connectors are implemented via `src/pulse/connectors/google_auth.py`, `src/pulse/connectors/gmail.py`, and `src/pulse/connectors/calendar.py`.
- [x] LLM provider abstraction exists, including Anthropic, OpenAI-compatible, Gemini, and Ollama-compatible wiring in `src/pulse/llm/factory.py`.
- [x] Connector plugin infrastructure exists through `src/pulse/domain/connectors.py` and `src/pulse/connectors/registry.py`.
- [x] Broader-than-MVP pull connector coverage exists and is documented in `docs/connectors/index.md` and registered in `src/pulse/connectors/__init__.py`.

## Partial

- [ ] Correction intake exists, but corrections are only stored, not clearly applied back into vault state, preferences, or other product state. See `src/pulse/app/main.py`, `src/pulse/services/corrections.py`, and `tests/integration/test_corrections_service.py`.
- [ ] Morning briefing exists, but it is currently a small digest-derived notification rather than a richer assistant-style briefing. See `src/pulse/analysis/briefing.py`.
- [ ] Vault support exists for daily digests and discovery/pattern files, but not the fuller vault/config loop implied by the design. See `src/pulse/vault/writer.py` and `src/pulse/analysis/discovery.py`.
- [ ] Push connector infrastructure exists as an abstraction and test surface, but no real shipped push connectors are registered by default. See `src/pulse/domain/connectors.py`, `src/pulse/connectors/registry.py`, `src/pulse/connectors/__init__.py`, and `tests/integration/test_push_webhook.py`.
- [ ] Insight generation exists through discovery and pattern writing, but the broader full-v1 cross-source intelligence story still appears incomplete. See `src/pulse/analysis/discovery.py` and the post-MVP/full-v1 expectations in `DESIGN.md`.

## Missing

- [ ] Companion app / Flutter client described in `DESIGN.md` section 8.
- [ ] Location tracking ingestion pipeline described in `DESIGN.md:898` and `DESIGN.md:908`.
- [ ] Geofence management, including manual creation and auto-detection, described in `DESIGN.md:910`.
- [ ] Health data ingestion (HealthKit / Health Connect bridge) described in `DESIGN.md:629`.
- [ ] Companion-app push notifications to replace Telegram for production, described in `DESIGN.md:630` and `DESIGN.md:949`.
- [ ] Mobile bidirectional messaging and manual input flow described in `DESIGN.md:631` and `DESIGN.md:632`.
- [ ] Android support listed in `DESIGN.md:931`.
- [ ] Telegram bot command support for `/status`, `/today`, and `/ask`, described in `DESIGN.md:618`.
- [ ] Full correction application loop, including updates to vault/profile/geofence state, implied by the current correction flow in `src/pulse/services/corrections.py` and the wider design.

## Release blockers for full v1

- [ ] Ship a real companion app surface.
- [ ] Ship location + geofence ingestion and storage.
- [ ] Ship health ingestion if the full-v1 definition still includes it.
- [ ] Make corrections apply meaningful state changes, not just record text.
- [ ] Decide whether full v1 still requires companion-app push notifications or whether Telegram remains acceptable for the first full release.

---

## Important scope note

If the project redefines v1 around the narrower backend/operator milestone reflected in `README.md` and `tests/e2e/test_backend_first_mvp.py`, the checklist changes substantially.

Under that narrower definition, Pulse is much closer: the main open gap is turning corrections from "stored" into "stored and applied," plus any optional bot-command polish the team decides to include.

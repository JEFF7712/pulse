# Google OAuth2 & LLM-Powered Summarization

**Date:** 2026-03-23
**Status:** Approved
**Builds on:** Backend-First MVP (`backend-first-mvp` branch)

---

## Goal

Enable real data ingestion from Google Calendar and Gmail via OAuth2, and upgrade the daily summarizer to produce LLM-powered digests with insights using Claude as the default provider.

## Part 1: Google OAuth2 Flow

### Auth Flow

1. User visits `GET /auth/google` → backend generates a random `state` token, stores it in-memory, and redirects to Google consent screen with the `state` parameter
2. Google redirects to `GET /auth/google/callback` with an auth code and `state`
3. Backend validates `state` matches what was generated, rejects the request otherwise (CSRF protection per RFC 6749 §10.12)
4. Backend exchanges code for access + refresh tokens via Google's token endpoint
5. Tokens stored in SQLite `oauth_tokens` table
6. On each connector pull, auth module checks expiry and auto-refreshes

### Security Notes

- The `state` parameter prevents CSRF on the callback endpoint
- Auth endpoints have no access control beyond being localhost-only — this is a single-user self-hosted system. Network exposure is the user's responsibility (reverse proxy, firewall, etc.)
- Token encryption at rest is out of scope for this iteration

### Token Storage

New `oauth_tokens` table in SQLite:

| Column | Type | Notes |
|--------|------|-------|
| provider | TEXT PRIMARY KEY | e.g. "google" |
| access_token | TEXT NOT NULL | Current access token |
| refresh_token | TEXT NOT NULL | Long-lived refresh token |
| expires_at | TEXT NOT NULL | ISO timestamp of access token expiry |
| scopes | TEXT NOT NULL | Space-separated granted scopes |
| updated_at | TEXT NOT NULL | Last refresh timestamp |

### Key Decisions

- Use `httpx` (already a project dependency) for all OAuth HTTP calls — no `google-auth` or `google-api-python-client` dependencies
- Google client ID/secret read from existing Settings placeholders (`google_client_id`, `google_client_secret`)
- Scopes: `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/gmail.readonly`
- Single-user system — one token row per provider, no user table

### Files

- Replace: `src/pulse/connectors/google_auth.py` (currently a stub)
- Create: `src/pulse/store/oauth.py`
- Modify: `src/pulse/app/main.py` (add `/auth/google` and `/auth/google/callback` endpoints)
- Modify: `src/pulse/store/schema.py` (add `oauth_tokens` table)
- Modify: `src/pulse/app/config.py` (add `google_redirect_uri` with default `http://localhost:8000/auth/google/callback`)

## Part 2: Real Google API Clients

### Google Calendar Client

- Calls Calendar v3 REST API via `httpx`
- Fetches events for a time range, handles pagination via `nextPageToken`
- Auto-refreshes expired tokens before each request

### Gmail Client

- Calls Gmail v1 REST API via `httpx`
- Lists messages with `after:` query for incremental pulls
- Fetches message metadata (headers, labels)
- Auto-refreshes expired tokens before each request

### Connector Changes

- Add `async classmethod GoogleCalendarConnector.from_settings(settings: Settings, db: aiosqlite.Connection) -> GoogleCalendarConnector` — reads OAuth tokens from SQLite, constructs a real `GoogleCalendarClient`, returns a configured connector
- Add `async classmethod GmailConnector.from_settings(settings: Settings, db: aiosqlite.Connection) -> GmailConnector` — same pattern
- Both `from_settings` methods are async because they read tokens from SQLite via `aiosqlite`
- `db` parameter is of type `aiosqlite.Connection` (returned by the existing `connect_db` context manager in `store/db.py`)
- Both fall back gracefully if no tokens exist (log warning, return empty list on `pull()`)
- Existing fake-client injection for tests stays untouched — constructor still accepts `client` param
- After successful pull, connectors update `SyncStateRepository` with latest cursor

### Files

- Modify: `src/pulse/connectors/calendar.py`
- Modify: `src/pulse/connectors/gmail.py`

Note: Wiring the connector factory methods into `runners.py` happens in Part 4 alongside the LLM integration, so both changes ship together.

## Part 3: LLM Provider & Claude Adapter

### Architecture

- New `LLMProvider` protocol in `src/pulse/llm/base.py`:
  ```python
  class LLMProvider(Protocol):
      async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str: ...
  ```
- This is a **breaking change** from the existing sync protocol in `domain/llm.py` (which uses `def complete(self, prompt: str, *, system_prompt: str | None = None) -> str`). Migration: delete `src/pulse/domain/llm.py`, update all imports to `pulse.llm.base.LLMProvider`, update `FakeLLM` in tests to match the new async signature.
- `ClaudeProvider` in `src/pulse/llm/claude.py` implements protocol using `anthropic` async SDK
- New config fields: `PULSE_ANTHROPIC_API_KEY`, `PULSE_LLM_MODEL` (default: `claude-sonnet-4-20250514` — set in Settings, used by ClaudeProvider)

### Testing

- All summarizer tests use `FakeLLM` (updated to async signature)
- Separate integration test for `ClaudeProvider` gated behind `PULSE_ANTHROPIC_API_KEY` env var

### Files

- Create: `src/pulse/llm/__init__.py`
- Create: `src/pulse/llm/base.py`
- Create: `src/pulse/llm/claude.py`
- Modify: `src/pulse/app/config.py` (add LLM settings)
- Delete: `src/pulse/domain/llm.py` (protocol moves to `llm/base.py`, update imports in `analysis/summarizer.py` and test files)

## Part 4: LLM-Powered Summarizer

### Changes to DailySummarizer

- `DailySummarizer.summarize()` becomes `async def summarize()` — this is a cascading change that requires updating `_build_daily_summary` in `runners.py` to `await` the call
- Accepts optional `LLMProvider` in constructor
- When LLM present: sends day's events as structured context with a system prompt requesting:
  - Natural language summaries per section (Timeline, Email Highlights, Spending, Health, Media)
  - An **Insights** section with patterns, anomalies, notable observations
- LLM response uses `## Section` headers for reliable parsing
- When no LLM available: falls back to current raw event listing behavior

### Prompt Design

- System prompt: "You are a personal assistant summarizing one day's activity for a single user."
- Emphasis on brevity (bullet points, not paragraphs)
- Pattern recognition focus ("3 meetings back-to-back", "no emails after 6pm — unusual")

### Vault Renderer Changes

- `render_daily_digest` gains optional `insights: list[str] | None` parameter
- Insights section renders after Media and before Tags as `## Insights` with bullet points

### Morning Briefing Changes

- `build_morning_briefing` accepts an optional `LLMProvider` parameter
- When present, sends the digest markdown to the LLM to produce a concise 3-5 line Telegram summary
- When absent, falls back to current behavior (event counts)

### Files

- Modify: `src/pulse/analysis/summarizer.py`
- Modify: `src/pulse/analysis/briefing.py`
- Modify: `src/pulse/vault/renderer.py`
- Modify: `src/pulse/jobs/runners.py` (wire LLMProvider into digest/briefing jobs, await async summarizer, use connector factory methods)

## Error Handling

- OAuth token refresh failure → log error, skip connector pull, job returns `partial_success`
- OAuth `state` mismatch on callback → return 400 error
- LLM call failure → fall back to raw event listing, log warning
- Missing OAuth tokens → connector returns empty list with warning log
- Missing LLM API key → summarizer uses fallback (no LLM) mode

## Testing Strategy

- **Unit tests:** OAuth token refresh logic (mock HTTP), OAuth state validation, LLM provider with fake responses, summarizer with/without LLM, prompt construction, insights rendering
- **Integration tests:** OAuth token storage round-trip in SQLite, connector factory methods with fake clients, full digest job with LLM
- **Gated tests:** Real Google API calls (requires `PULSE_GOOGLE_CLIENT_ID`), real Claude API calls (requires `PULSE_ANTHROPIC_API_KEY`)

## New Dependencies

- `anthropic` — Claude SDK for LLM provider
- (`httpx` is already a project dependency)

## Out of Scope

- Multi-user auth / user accounts
- Auth endpoint access control (single-user, localhost assumption)
- OpenAI or local LLM adapters (protocol supports them, but only Claude is implemented)
- Action item extraction from digests
- Google OAuth token encryption at rest

# Google OAuth2 & LLM-Powered Summarization

**Date:** 2026-03-23
**Status:** Approved
**Builds on:** Backend-First MVP (`backend-first-mvp` branch)

---

## Goal

Enable real data ingestion from Google Calendar and Gmail via OAuth2, and upgrade the daily summarizer to produce LLM-powered digests with insights using Claude as the default provider.

## Part 1: Google OAuth2 Flow

### Auth Flow

1. User visits `GET /auth/google` → redirected to Google consent screen
2. Google redirects to `GET /auth/google/callback` with an auth code
3. Backend exchanges code for access + refresh tokens via Google's token endpoint
4. Tokens stored in SQLite `oauth_tokens` table
5. On each connector pull, auth module checks expiry and auto-refreshes

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

- Use `httpx` for all OAuth HTTP calls — no `google-auth` or `google-api-python-client` dependencies
- Google client ID/secret read from existing Settings placeholders (`google_client_id`, `google_client_secret`)
- Scopes: `https://www.googleapis.com/auth/calendar.readonly`, `https://www.googleapis.com/auth/gmail.readonly`
- Single-user system — one token row per provider, no user table

### Files

- Replace: `src/pulse/connectors/google_auth.py` (currently a stub)
- Create: `src/pulse/store/oauth.py`
- Modify: `src/pulse/app/main.py` (add `/auth/google` and `/auth/google/callback` endpoints)
- Modify: `src/pulse/store/schema.py` (add `oauth_tokens` table)
- Modify: `src/pulse/app/config.py` (add `google_redirect_uri` setting)

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

- Add `GoogleCalendarConnector.from_settings(settings, db)` factory method — constructs real client from stored OAuth tokens
- Add `GmailConnector.from_settings(settings, db)` factory method
- Both fall back gracefully if no tokens exist (log warning, return empty list)
- Existing fake-client injection for tests stays untouched
- After successful pull, connectors update `SyncStateRepository` with latest cursor

### Files

- Modify: `src/pulse/connectors/calendar.py`
- Modify: `src/pulse/connectors/gmail.py`

## Part 3: LLM Provider & Claude Adapter

### Architecture

- `LLMProvider` protocol in `src/pulse/llm/base.py`: `async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str`
- `ClaudeProvider` in `src/pulse/llm/claude.py` implements protocol using `anthropic` async SDK
- Default model: `claude-sonnet-4-20250514`
- New config fields: `PULSE_ANTHROPIC_API_KEY`, `PULSE_LLM_MODEL`

### Testing

- All summarizer tests use `FakeLLM`
- Separate integration test for `ClaudeProvider` gated behind `PULSE_ANTHROPIC_API_KEY` env var

### Files

- Create: `src/pulse/llm/__init__.py`
- Create: `src/pulse/llm/base.py`
- Create: `src/pulse/llm/claude.py`
- Modify: `src/pulse/app/config.py` (add LLM settings)
- Remove or redirect: `src/pulse/domain/llm.py` (move protocol to `llm/base.py`)

## Part 4: LLM-Powered Summarizer

### Changes to DailySummarizer

- Accepts optional `LLMProvider`
- When present: sends day's events as structured context to the LLM with a system prompt requesting:
  - Natural language summaries per section (Timeline, Email Highlights, Spending, Health, Media)
  - An **Insights** section with patterns, anomalies, notable observations
- LLM response uses `## Section` headers for reliable parsing
- When no LLM available: falls back to current raw event listing behavior

### Prompt Design

- System prompt: "You are a personal assistant summarizing one day's activity for a single user."
- Emphasis on brevity (bullet points, not paragraphs)
- Pattern recognition focus ("3 meetings back-to-back", "no emails after 6pm — unusual")

### Vault Renderer Changes

- `render_daily_digest` gains optional `insights` parameter for the Insights section

### Morning Briefing Changes

- `build_morning_briefing` gets optional LLM access to produce concise 3-5 line Telegram message instead of raw event counts

### Files

- Modify: `src/pulse/analysis/summarizer.py`
- Modify: `src/pulse/analysis/briefing.py`
- Modify: `src/pulse/vault/renderer.py`

## Error Handling

- OAuth token refresh failure → log error, skip connector pull, job returns `partial_success`
- LLM call failure → fall back to raw event listing, log warning
- Missing OAuth tokens → connector returns empty list with warning log
- Missing LLM API key → summarizer uses fallback (no LLM) mode

## Testing Strategy

- **Unit tests:** OAuth token refresh logic (mock HTTP), LLM provider with fake responses, summarizer with/without LLM, prompt construction
- **Integration tests:** OAuth token storage round-trip in SQLite, connector factory methods with fake clients, full digest job with LLM
- **Gated tests:** Real Google API calls (requires `PULSE_GOOGLE_CLIENT_ID`), real Claude API calls (requires `PULSE_ANTHROPIC_API_KEY`)

## New Dependencies

- `anthropic` — Claude SDK for LLM provider

## Out of Scope

- Multi-user auth / user accounts
- OpenAI or local LLM adapters (protocol supports them, but only Claude is implemented)
- Action item extraction from digests
- Google OAuth token encryption at rest

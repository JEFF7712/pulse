# Analytics & Insight Engine — Design Spec

**Date:** 2026-03-25
**Status:** Approved
**Scope:** Analytics layer, discovery engine, vault-based LLM memory, push notifications

---

## 1. Goal

Build an analytics and insight engine that finds cross-source patterns and correlations in the user's personal data — things that are hard for humans to notice on their own. The system is push-based: it proactively notifies the user of discoveries via Telegram. The user never asks questions; the system comes to them.

## 2. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary insight type | Cross-source correlations | The unique value of aggregating many data sources |
| Pattern detection | LLM-assisted discovery | LLM finds patterns, not just narrates code-detected ones |
| Insight memory | Stateful with evolution | Patterns are tracked, updated, strengthened/weakened over time |
| LLM memory storage | Obsidian vault | Markdown files the LLM reads/writes; user can see and annotate |
| Discovery cadences | Configurable (daily/weekly/monthly) | Each cadence serves a different analytical purpose |
| Entity extraction | Deferred to LLM during discovery | No enrichment jobs; LLM handles entity recognition in context |

## 3. Architecture

```
Connectors → Raw Events (SQLite) → Aggregation Jobs (code) → Analytics Tables (SQLite)
                                                                      ↓
                                                              Discovery Engine
                                                              ├── Read: analytics tables (stats)
                                                              ├── Read: vault memory (active patterns, baselines, user profile)
                                                              ├── Read: event summaries (condensed from raw events)
                                                              │
                                                              ├── LLM: "what's new, changed, or surprising?"
                                                              │
                                                              └── Write back:
                                                                  ├── Vault: new/updated pattern files, baselines
                                                                  ├── SQLite: insights table (tracking/dedup)
                                                                  └── Telegram: push notifications
```

**What changes from today:**
- New: Analytics tables in SQLite (aggregated stats only — no entity tables)
- New: Discovery engine (scheduled LLM discovery passes)
- New: Vault insight files as LLM read/write memory
- Modified: Schema gets indexes and new tables
- Unchanged: Raw events table, all connectors, ingestion pipeline

**What we are NOT building:**
- Entity extraction tables or enrichment jobs
- Embedding/vector store
- Code-based pattern detectors
- Query builder / LLM-generated SQL

## 4. Analytics Tables

Pre-computed by aggregation jobs (pure SQL/Python, no LLM). Purpose: compress raw events into a format that fits in the LLM's context window.

### `daily_source_stats`

One row per source per event type per day.

```sql
CREATE TABLE daily_source_stats (
    date       TEXT NOT NULL,
    source     TEXT NOT NULL,
    event_type TEXT NOT NULL,
    count      INTEGER NOT NULL,
    first_at   TEXT,
    last_at    TEXT,
    PRIMARY KEY (date, source, event_type)
);
```

### `time_blocks`

Activity per 2-hour block of the day. Gives the LLM a sense of daily rhythm.

```sql
CREATE TABLE time_blocks (
    date       TEXT NOT NULL,
    block      INTEGER NOT NULL,   -- 0-11 (0=00:00-02:00, 6=12:00-14:00, etc.)
    source     TEXT NOT NULL,
    count      INTEGER NOT NULL,
    PRIMARY KEY (date, block, source)
);
```

### `weekly_baselines`

Rolling averages for comparison. Updated weekly.

```sql
CREATE TABLE weekly_baselines (
    week_start TEXT NOT NULL,      -- Monday date, e.g. "2026-03-17"
    source     TEXT NOT NULL,
    event_type TEXT NOT NULL,
    avg_daily  REAL NOT NULL,
    total      INTEGER NOT NULL,
    PRIMARY KEY (week_start, source, event_type)
);
```

### `insights`

Tracks the LLM's discovered patterns for deduplication and lifecycle management.

```sql
CREATE TABLE insights (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL,     -- "active", "weakening", "invalidated", "archived"
    confidence  TEXT NOT NULL,     -- "low", "medium", "high"
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    vault_path  TEXT NOT NULL,     -- path to the pattern markdown file
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes on `events` table

Currently missing from the schema. Required for efficient aggregation:

```sql
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
```

### Aggregation job

Runs hourly, idempotent. Recomputes stats for the current day from raw events. Ensures analytics tables stay fresh as new events arrive.

## 5. Discovery Engine

### 5.1 Cadences

| Cadence | Schedule | Data Window | Purpose |
|---------|----------|-------------|---------|
| Daily | 11 PM | Last 24 hours | Quick anomaly check — "anything notable today?" |
| Weekly | Sunday 8 PM | Last 7 days | Cross-source correlation discovery |
| Monthly | 1st of month, 10 AM | Last 30 days | Long-term trend review, pattern lifecycle updates |

### 5.2 Discovery Pass Flow

Each pass follows the same 5-step flow:

**Step 1 — Gather context:**

- Query analytics tables for the relevant time window (`daily_source_stats`, `time_blocks`, `weekly_baselines`)
- Generate event summaries from raw events (condensed natural language, grouped by source)
- Read vault memory: active pattern files, baselines, user profile

**Step 2 — Build prompt:**

System prompt defines the LLM's role, rules, and output schema. User prompt contains: stats, event summaries, active patterns, baselines, user profile.

**Step 3 — LLM call (STRONG tier):**

The LLM analyzes the data in context of its memory and produces structured JSON output.

**Step 4 — Parse response:**

LLM returns:
- `new_patterns`: list of newly discovered patterns (title, observation, confidence, supporting data)
- `updated_patterns`: updates to existing patterns (id, new status, new confidence, update note)
- `notifications`: findings worth pushing to the user (title, body, priority)

**Step 5 — Write back:**

- Vault: create new pattern files, update existing ones (status, confidence, evidence log)
- Vault: update `03-Life/` files if baselines shifted
- SQLite: upsert `insights` table
- Telegram: send notifications for significant findings

### 5.3 Event Summary Generation

The bridge between raw events and LLM context. Converts raw event JSON into condensed natural language summaries grouped by source. Example output:

```
## Gmail (March 19-25)
- 47 emails received (avg 6.7/day, baseline 5.2/day — up 29%)
- Top senders: alice@company.com (12), bob@company.com (8), newsletters (15)
- Notable subjects: "Project Atlas deadline", "Q2 planning", "Team offsite RSVP"

## Spotify (March 19-25)
- 143 plays (avg 20.4/day, baseline 18/day)
- Peak listening: 10pm-midnight on Mon, Tue, Thu
- No listening on Wednesday

## Browser (March 19-25)
- 89 page visits
- Top domains: github.com (23), stackoverflow.com (15), docs.python.org (12)
- Late night browsing (after 10pm): 4 of 7 nights
```

The summarizer pulls from both analytics tables (for counts and baselines) and raw events (for specific content like email subjects, track names, page titles).

### 5.4 Prompt Structure

```
SYSTEM: You are Pulse's insight engine. You analyze personal data
to find cross-source patterns and correlations the user wouldn't
notice on their own. You maintain a set of tracked patterns that
evolve over time.

Rules:
- Only surface genuinely interesting or actionable findings
- Update existing patterns with new evidence (strengthening/weakening)
- Mark patterns as "invalidated" if the data no longer supports them
- Be specific — cite actual data points, not vague observations
- Output valid JSON matching the schema below

[output JSON schema]

USER:
## Current Data ({date_range})
{event_summaries}

## Your Active Patterns
{active_pattern_files_from_vault}

## Known Baselines
{routines_md_from_vault}

## User Profile
{profile_md_from_vault}

What new patterns do you see? How have existing patterns changed?
```

## 6. Vault Memory Structure

The Obsidian vault serves as the LLM's persistent, human-readable memory.

### 6.1 Pattern Files (`02-Insights/patterns/<slug>.md`)

Written and updated by the discovery engine:

```markdown
# Pattern: Late-Night Browsing Correlates with Heavy Meeting Days

**Status:** active
**Confidence:** medium
**First seen:** 2026-03-18
**Last updated:** 2026-03-25

## Observation
On days with 4+ meetings, you browse the web after 10pm 80% of the time,
compared to 20% on lighter days.

## Evidence Log
- 2026-03-25: 5 meetings → browsing until 11:42pm (YouTube, Reddit)
- 2026-03-21: 4 meetings → browsing until 11:15pm (news sites)
- 2026-03-20: 2 meetings → no late browsing

## Trend
Strengthening. Consistent over 3 weeks of data.

## User Notes
_None yet._
```

The `User Notes` section is user-editable in Obsidian. The LLM reads it on the next pass and incorporates the feedback.

### 6.2 Life Knowledge Files (`03-Life/`)

Updated by the discovery engine when baselines shift:

```markdown
# Routines

## Weekday Rhythm
- Email activity peaks 9am-11am and 2pm-4pm
- Meetings cluster 10am-12pm
- Spotify listening typically 6pm-10pm

## Weekly Baselines (rolling 4-week average)
- Email received: 5.2/day
- Meetings: 2.8/day
- Spotify plays: 18/day
- Browser visits: 12/day

_Last updated: 2026-03-25 by weekly discovery pass_
```

### 6.3 Read/Write Permissions

| File | Discovery Engine Reads | Discovery Engine Writes |
|------|----------------------|------------------------|
| `02-Insights/patterns/*.md` | Every pass | Creates new, updates existing |
| `03-Life/routines.md` | Every pass | Weekly/monthly when baselines shift |
| `03-Life/interests.md` | Weekly/monthly | When new interests detected |
| `03-Life/contacts.md` | Weekly/monthly | When recurring people emerge |
| `04-Config/profile.md` | Every pass | Never — user-maintained only |

### 6.4 Pattern Lifecycle

```
discovered → active → strengthening/weakening → invalidated → archived
```

- **discovered**: First seen, low confidence
- **active**: Confirmed across multiple passes
- **strengthening/weakening**: Trend direction noted
- **invalidated**: Data no longer supports it
- **archived**: Moved to `02-Insights/archive/`

The `insights` SQLite table mirrors the lifecycle for querying, but the vault files are the source of truth for LLM memory.

## 7. Integration with Existing Codebase

### 7.1 New Modules

| Module | Purpose |
|--------|---------|
| `src/pulse/store/analytics.py` | Aggregation queries — populate analytics tables from raw events |
| `src/pulse/analysis/discovery.py` | Discovery engine — orchestrates gather → prompt → LLM → write-back |
| `src/pulse/analysis/event_summarizer.py` | Converts raw events into condensed natural language summaries |
| `src/pulse/analysis/vault_memory.py` | Reads/writes vault pattern files and life knowledge files |
| `src/pulse/analysis/prompts.py` | Prompt templates for daily/weekly/monthly passes |

### 7.2 Modified Modules

| Module | Change |
|--------|--------|
| `src/pulse/store/schema.py` | Add analytics tables and indexes |
| `src/pulse/jobs/scheduler.py` | Register aggregation and discovery jobs |
| `src/pulse/jobs/runners.py` | Add `run_aggregation_job()` and `run_discovery_job()` runners |
| `src/pulse/domain/llm.py` | Flesh out LLM protocol with actual provider implementation (Anthropic) |
| `src/pulse/vault/writer.py` | Add methods for writing/updating insight pattern files |

### 7.3 Unchanged

- All connectors (Gmail, Calendar, YouTube, Spotify, Browser)
- Event model and EventRepository
- Config, CLI, MCP server
- Telegram notification channel (reused by discovery engine)

### 7.4 Job Scheduling

```python
# Aggregation — hourly, idempotent
scheduler.add_job(run_aggregation_job, "interval", hours=1, id="aggregation")

# Discovery passes
scheduler.add_job(run_discovery_daily, "cron", hour=23, id="discovery_daily")
scheduler.add_job(run_discovery_weekly, "cron", day_of_week="sun", hour=20, id="discovery_weekly")
scheduler.add_job(run_discovery_monthly, "cron", day=1, hour=10, id="discovery_monthly")
```

### 7.5 LLM Provider

The `domain/llm.py` currently has a one-line protocol stub. Needs a real Anthropic provider implementation supporting the STRONG tier (Claude Sonnet/Opus) for discovery passes.

### 7.6 Relationship to Existing Daily Digest/Briefing

The existing summarizer and morning briefing jobs stay as-is. They work and serve a different purpose (structured daily recap vs. pattern discovery). Over time the discovery engine's daily pass could subsume the morning briefing, but that's a future optimization outside this spec.

## 8. Testing Strategy

### 8.1 Unit Tests

| Test | Verifies |
|------|----------|
| `test_aggregation.py` | Aggregation queries produce correct stats from sample events |
| `test_event_summarizer.py` | Raw events are condensed into readable summaries with correct format |
| `test_vault_memory.py` | Pattern files round-trip correctly; updates preserve user notes |
| `test_prompts.py` | Prompt templates produce well-formed prompts from sample inputs |
| `test_discovery.py` | Discovery engine orchestration with mocked LLM — correct context in, correct routing out |

### 8.2 Integration Tests

| Test | Verifies |
|------|----------|
| `test_aggregation_from_events.py` | Insert raw events → run aggregation → verify analytics tables |
| `test_discovery_cycle.py` | Full cycle with fake LLM: events → aggregation → discovery → vault files + insights table |
| `test_pattern_evolution.py` | Multi-pass: discovery creates pattern → more events → discovery updates pattern status |
| `test_notification_delivery.py` | Discovery findings trigger Telegram notifications via existing channel |

### 8.3 LLM Mock Strategy

The `LLM` protocol enables clean mocking. Tests inject a fake that returns canned JSON responses matching the expected output schema. All orchestration is tested without real API calls. LLM output quality is a prompt engineering concern, not a code testing concern.

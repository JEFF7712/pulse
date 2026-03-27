# Smarter Outputs: Pre-processing, Two-pass LLM Pipeline & Narrative Digests

**Date:** 2026-03-26
**Status:** Partially implemented

## Current state

Most of this design is live in code: Pulse now preprocesses events, generates source narratives, builds smarter digests, and feeds discovery with the richer pipeline. The remaining mismatch is rollout consistency: CLI and scheduled jobs can use the configured summarization/discovery providers, but `src/pulse/app/home_actions.py` still calls the digest job without a summarization LLM and `src/pulse/mcp/server.py` still uses the sync `DailySummarizer()` path.

## Problem

Pulse's current outputs have two weaknesses:

1. **Discovery sees too little data.** The EventSummarizer gives the LLM only 5 highlights per source. With hundreds of events, the LLM pattern-matches on a thin slice and produces a mix of genuinely interesting insights and obvious observations ("you use email regularly").

2. **Digests are flat bullet lists.** The daily digest is a mechanical dump — 100 emails become 100 bullet points, browsing is raw URLs. No narrative, no grouping, no sense of how the day actually felt.

## Solution

A three-stage pipeline: code pre-processing, Haiku summarization, and Sonnet discovery.

---

## Stage 1: EventPreprocessor (Code)

New `EventPreprocessor` class replaces `EventSummarizer` with richer code-side analysis.

### Per-source processing

**Browsing:**
- Group visits by domain
- Cluster by topic using title keywords (e.g., 15 visits to Rust docs + tutorials = "Rust learning session")
- Deduplicate repeated visits to the same page
- Estimate time spent per cluster using gaps between consecutive visits
- Output: topic clusters with estimated duration

**Email:**
- Group by thread/conversation (same subject minus Re:/Fwd: prefixes)
- Identify senders with most messages
- Flag threads with many back-and-forth exchanges as "active conversations"
- Output: thread summaries rather than individual messages

**Calendar:**
- Existing title + time handling stays
- Add: meeting density (back-to-back detection), total meeting hours, gap identification
- Output: meeting blocks with density annotations

**Media (Spotify/YouTube):**
- Group by listening session (consecutive plays within 30 min gap)
- Identify artist/genre clusters for Spotify
- Group YouTube by topic similarity in titles
- Output: session summaries with duration

### Cross-source timeline

Build a time-of-day activity map: what sources were active in each 2-hour block. This is the raw material for cross-source observations (e.g., "browsed tech articles during the gap between meetings").

### Output

A structured `PreprocessedDay` dataclass with:
- `browsing_clusters: list[TopicCluster]`
- `email_threads: list[EmailThread]`
- `calendar_blocks: list[CalendarBlock]`
- `media_sessions: list[MediaSession]`
- `time_blocks: list[TimeBlock]` (cross-source)
- `raw_stats: dict` (counts per source/type)

---

## Stage 2: Source Summarization (Haiku)

Each source's preprocessed data gets sent to Haiku with a tight prompt:

> "Summarize this person's [source] activity into 2-3 paragraphs. Focus on what they spent time on, what seemed important, and anything unusual."

- One call per active source, run in parallel
- Each returns a short narrative (2-3 paragraphs)
- Narratives are the building blocks for both digest and discovery

### Model configuration

The `LLMProvider` protocol gets a `model` parameter so the same provider can route to Haiku vs Sonnet. `AnthropicProvider.complete()` accepts an optional `model` override.

Config additions to `PulseConfig`:
- `summarization_model: str = "claude-haiku-4-5-20251001"`
- `discovery_model: str = "claude-sonnet-4-5-20250514"`

---

## Stage 3a: Discovery (Sonnet)

The discovery prompt receives:
- All source narratives from Stage 2
- Cross-source timeline from the preprocessor
- Existing patterns from the vault
- Weekly baselines
- User profile

### Prompt improvements

Explicit rejection criteria added to system prompt:
- "Do NOT report that the user uses email/calendar/browsing regularly -- that is baseline, not a pattern"
- "A pattern must involve either: (a) a cross-source connection, (b) a temporal trend (increasing/decreasing over time), or (c) a deviation from established baselines"
- "Include the specific data that surprised you, not just the category"

The cadence instructions are also sharpened to push for cross-source connections.

---

## Stage 3b: Narrative Daily Digest

The digest moves from a mechanical bullet list to a narrative format.

### New digest structure

```markdown
# 2026-03-26

## Day at a Glance
<!-- 2-3 sentence Haiku-generated overview -->
A meeting-heavy morning with 4 hours of calls, followed by a deep
afternoon browsing session on Rust async patterns. Light email day
with one active thread about the Q2 roadmap.

## Timeline
<!-- Key events chronological, grouped by time block -->
### Morning (8am-12pm)
- 9:00 Team standup
- 9:30-11:30 Back-to-back design reviews
- 11:45 Replied to Q2 roadmap thread (3 messages)

### Afternoon (12pm-6pm)
- 1:00-3:00 Deep browsing: Rust async/await patterns (tokio docs,
  blog posts, Stack Overflow)
- 3:30 Quick calendar check, scheduled Friday 1:1

### Evening (6pm-12am)
- Spotify: Indie folk session (~1.5 hours)
- YouTube: 2 Rust conference talks

## Email
<!-- Thread-grouped -->
- **Q2 Roadmap** (3 messages with PM team) -- active discussion
- 12 other messages (newsletters, notifications)

## Media
- Spotify: 28 tracks, mostly indie folk (Bon Iver, Iron & Wine)
- YouTube: "Rust async deep dive" talk, "Tokio tutorial pt. 3"

## Browsing
- Rust learning: tokio docs, async-std comparison, 3 blog posts (~2 hrs)
- HN front page (15 min)
```

### Key changes from current
- "Day at a Glance" from Haiku (new)
- Timeline is chronological, grouped by time block instead of flat by source
- Email shows threads not individual messages
- Browsing shows topic clusters with time estimates
- Media shows sessions not individual tracks

### Fallback

If no LLM is configured, the digest falls back to the current bullet-list format. The code preprocessor improvements still improve that (topic clusters, thread grouping), just without the narrative glue.

---

## Data Flow

```
Events (raw)
  -> EventPreprocessor (code: cluster, group, dedupe)
  -> PreprocessedDay
  -> SourceSummarizer (Haiku: narrative per source)
  -> Source narratives
  |-> DigestBuilder (narrative daily digest for vault)
  +-> DiscoveryEngine (Sonnet: cross-source pattern detection)
       -> Patterns, notifications
```

---

## File Changes

### New files
- `src/pulse/analysis/preprocessor.py` -- `EventPreprocessor`, `PreprocessedDay`, and per-source dataclasses (`TopicCluster`, `EmailThread`, `CalendarBlock`, `MediaSession`, `TimeBlock`)
- `src/pulse/analysis/source_summarizer.py` -- `SourceSummarizer` class, Haiku summarization pass
- `src/pulse/analysis/digest_builder.py` -- `DigestBuilder` class, narrative markdown rendering

### Modified files
- `src/pulse/analysis/prompts.py` -- Sharpen discovery prompt with rejection criteria, accept narratives instead of raw event summary
- `src/pulse/analysis/discovery.py` -- Wire in preprocessor -> source summarizer -> discovery pipeline
- `src/pulse/analysis/summarizer.py` -- Delegate to `DigestBuilder` when LLM available, fall back to current logic when not
- `src/pulse/llm/anthropic.py` -- Add `model` parameter to `complete()` method
- `src/pulse/app/config.py` -- Add `discovery_model` and `summarization_model` fields
- `src/pulse/jobs/runners.py` -- Pass LLM provider to digest job when available
- `src/pulse/vault/renderer.py` -- New narrative template alongside existing bullet template

### Test files
- `tests/unit/test_preprocessor.py` -- Browsing clustering, email threading, time block grouping
- `tests/unit/test_source_summarizer.py` -- Haiku pass with fake LLM
- `tests/unit/test_digest_builder.py` -- Narrative digest rendering
- Updated: `tests/unit/test_prompts.py` -- New prompt structure
- Updated: `tests/unit/test_discovery.py` -- Full pipeline with preprocessor

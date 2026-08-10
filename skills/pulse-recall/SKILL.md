---
name: pulse-recall
description: Use to answer ad-hoc questions about the user's own history from a Pulse install (the pulse-mcp server) - "what did I / when did I / how often did I …" - efficiently and with citations.
---

# Pulse Recall

The user is asking about their own life-data, ingested by their self-hosted Pulse install and
exposed over the `pulse-mcp` MCP server. Answer from that data, efficiently, and cite the events
you used. If the data cannot answer it, say so rather than guessing.

## Method

1. **Check memory first.** `pulse_vault_read`/`pulse_vault_list` - the answer or useful context may
   already be recorded in the vault (profile, prior observations).

2. **Query with the tightest filter that answers the question.** Use `pulse_query_events` with
   `sources`, `text`, and `start`/`end` narrowed as much as the question allows. A precise query
   beats a broad pull every time. `pulse_query_events` returns newest-first, paginated, with a
   `count`/`truncated` field - if `truncated` is true and you need completeness (e.g. "how many
   times"), narrow the filter or page rather than assuming what you got is all of it.

3. **For "what did my day/week look like" questions, use `pulse_digest`** instead of raw events  - 
   it is the cheap, deterministic summary.

4. **Escalate detail only when needed.** Event data is trimmed by default; pass `full=true` only for
   the specific event whose full content the question hinges on.

5. **Cite and be honest about gaps.** Reference the event ids/timestamps behind your answer. If a
   source is disabled or stale, check `pulse_coverage` and say the answer may be incomplete because
   that source is not covered.

## Anti-patterns

- Pulling a wide date range with no source/text filter "to be safe" - that burns context and often
  still misses the answer.
- Answering a counting/frequency question off a truncated result set without checking `count`.
- Inventing detail not present in the events.

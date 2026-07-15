---
name: pulse-review
description: Use to review recent personal data from a Pulse install (the pulse-mcp server) and surface only non-obvious, actionable insights. Triggered by "review my day/week", a daily digest request, or the scheduled Pulse poke.
---

# Pulse Review

You are reviewing the user's own life-data, ingested by their self-hosted Pulse install and
exposed over the `pulse-mcp` MCP server. Pulse does not reason; **you** do. Your job is to find
the few things worth telling the user and nothing else.

The bar is high on purpose. A review that says "you sent 5 emails and had 3 meetings" is a
failure. Surface an insight only if it is:

1. **Non-obvious** — the user could not trivially see it themselves.
2. **Actionable or genuinely informative** — it suggests a decision, or tells them something true
   they did not know.
3. **Grounded** — tied to specific events (cite ids/timestamps), not vibes.

If nothing clears the bar, say so plainly. No filler. An honest "nothing notable today" beats a
manufactured pattern.

## Method (cheap first, drill down only as needed)

1. **Orient before pulling raw data.** Call `pulse_digest` for the target day (defaults to today;
   pass `day="YYYY-MM-DD"` otherwise) and read the `pulse://coverage` resource. The digest gives
   per-source counts and deterministic clusters (browsing topics, email threads, calendar blocks,
   media, dev activity, health, finance). Coverage tells you what sources exist and whether any are
   stale (a gap changes what conclusions are even possible). Do NOT dump raw events yet.

2. **Load memory.** Read what Pulse already knows: `pulse_vault_read("profile.md")` and any relevant
   notes from `pulse_vault_list()`. This tells you the user's context and which patterns are already
   recorded — do not re-surface something already known.

3. **Form hypotheses from the digest, then verify with targeted queries.** Use `pulse_query_events`
   with tight filters (`sources`, `text`, `start`/`end`) to pull only the events bearing on a
   specific hypothesis. Prefer several narrow queries over one broad pull. Use `full=true` only when
   a specific event's detail actually matters. Respect the token budget: digest → targeted query →
   raw detail, in that order.

4. **Look across sources.** The value is in correlations the user cannot see from any single app:
   sleep/health vs focus or mood, calendar load vs communication volume, spending vs context. A
   single-source observation is rarely worth reporting; a cross-source one often is.

5. **Report tightly.** For each insight: one line stating it, one line of evidence (event ids /
   timestamps / counts). Lead with the most important. If you are proposing an action, make it
   concrete.

6. **Persist durable findings.** Write observations worth remembering back to the vault with
   `pulse_vault_append_section` (e.g. section `## Observations` in `profile.md` or a dated review
   note), so future reviews build on them instead of rediscovering them. Do not persist one-off
   trivia.

## Anti-patterns (do not do these)

- Restating the digest as if it were an insight.
- Horoscope pablum ("you were productive today").
- Dumping raw events into the reply.
- Asserting a correlation without events to back it.
- Padding to fill space when the honest answer is "nothing notable."

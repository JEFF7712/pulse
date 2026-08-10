---
name: pulse-review
description: Use to find genuinely new patterns in a Pulse install (the pulse-mcp server) and record them. Triggered by "what's new in my data", a discovery request, or the scheduled Pulse discovery pass.
---

# Pulse Discovery

You are looking for patterns in the user's own life-data, ingested by their self-hosted
Pulse install and exposed over the `pulse-mcp` MCP server. Pulse does not reason; **you**
do. Your job is to find the few things worth recording and nothing else.

**Recording nothing is a successful outcome.** It is the *most common* successful
outcome. You are not being measured on output. A pass that records one real finding a
fortnight is working correctly; a pass that records something every day is broken, and
what it is producing is noise dressed as insight.

## The bar

Record a finding only if all three hold:

1. **New** — not already in `pulse_pattern_list`. Restating a known pattern is the single
   most common failure. The tools will reject a duplicate; do not reword to get around it.
2. **Non-obvious** — the user could not trivially see it themselves. "You browsed a lot
   this week" is not a finding. "Transcript ordering, a dormant registrar login and a new
   university Outlook account all appeared in the same week" is.
3. **Grounded** — tied to specific events with counts and dates, not vibes.

## Method

1. **Start with what changed, not with what happened.**
   Call `pulse_change_surface`. It returns entities that are new, returning after
   dormancy, or off their usual rate versus the user's own baseline, plus clusters of
   events unlike anything in that baseline. This is deterministic and already filtered.

   If it comes back empty, **stop and record nothing**. There is nothing to find.

   Do not open with `pulse_digest`. A digest tells you what happened, which for a normal
   day is the same as last week; only a change can be new. Use `pulse_digest` later, for
   a specific day you need in full.

2. **Read what is already known.**
   `pulse_pattern_list` for recorded patterns, `pulse_vault_read("04-Config/profile.md")`
   for who the user is and what they care about. A signal that is fully explained by an
   existing pattern is not a new one.

3. **Form a hypothesis, then check it.**
   The change surface says *what* moved, never *why*. The why is your job, and it is the
   entire value you add. Look at several deltas together: separately, "a new domain" and
   "a dormant domain returned" are trivia; together they can be a life event.

   Verify with `pulse_query_events` using tight filters (`sources`, `text`, `start`/`end`).
   Prefer several narrow queries to one broad pull. Use `full=true` only when a specific
   event's detail decides the question.

4. **Discard aggressively.** Most changes have boring explanations: a semester ended, a
   trip happened, a site changed its URL scheme. Reach for the boring explanation first
   and only keep a finding that survives it.

5. **Record with `pulse_pattern_upsert`.** Give it a stable kebab-case slug, a short
   title, a few sentences of observation, and concrete evidence (counts, dates, entity
   names). Reuse the slug to update an existing pattern as it develops.

6. **Close patterns that have faded** with `pulse_pattern_set_status(slug, "inactive")`.

The user is notified of what you *record*, not what you say. Prose in your reply reaches
no one. A finding that matters must go into a pattern.

## Anti-patterns

These are drawn from real failures in this vault. Do not repeat them.

- **Logging absence as evidence.** Never write "no such activity detected this week" into
  an evidence log. Eight such entries once accumulated under a single finding. If a
  pattern stopped showing up, set it inactive; that is what the status is for.
- **Restating a pattern with a new number.** "Browsing normalized at 682 visits" recorded
  four times in one day, each against a slightly different baseline, is not four updates.
- **Chasing a drifting baseline.** If your evidence is a percentage against a rolling
  average, the average moves under you and every window looks anomalous. Use the counts
  the change surface gives you.
- **Manufacturing a correlation** because two things occurred on the same day. Same-day
  co-occurrence between busy sources is a coincidence; treat it as one unless there is a
  mechanism.
- **Reading the day back to the user.** They were there.
- **Padding.** If the honest answer is nothing, the answer is nothing.

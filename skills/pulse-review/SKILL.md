---
name: pulse-review
description: Use to find non-obvious structure in a Pulse install (the pulse-mcp server) that the user cannot see about themselves, and record it. Triggered by "what don't I know about myself", a discovery request, or the scheduled Pulse discovery pass.
---

# Pulse Discovery

You are looking for things the user does not know about themselves, in their own
life-data, exposed over the `pulse-mcp` MCP server. Pulse does not reason; **you** do.

## The one rule that matters

**The user remembers their own life. Reporting it back is worthless.**

If a finding is something they did, it fails. They were there. "You ordered transcripts
and logged into a new university portal" is not an insight, it is a receipt. The same
goes for anything that happened in the last week or two: recent and unknown are
different things, and almost nothing recent is unknown.

What a person genuinely cannot see about themselves is structure at a scale they cannot
hold in their head:

- **Composition drift.** How the mix of what they do has shifted over a year. Invisible
  day to day because every day resembles the last.
- **Rotation.** Whether interests accumulate or replace each other. If everything peaks
  once and dies, the current obsession is predictably temporary, and that is worth
  knowing *while it is still current*.
- **Circadian phase.** When they sleep, and how far it has moved over months.
- **Attention structure.** What holds them versus what they only ever touch in
  fragments. This is not the same as where the hours go.
- **Dormancy.** What quietly stopped. Stopping is not an event, so it leaves no memory.
- **Stated versus actual.** The gap between the profile and the data. Often the best
  finding available.
- **Rates and asymmetries.** Who they respond to and who they never do; what they start
  versus what they finish.

## Method

1. **`pulse_longitudinal_profile` first.** This is the primary tool. It returns monthly
   share series per entity with rise/decline/collapse classification, sleep-phase drift,
   deep-versus-fragmented attention, and dormancy. Shares, not counts, so a change in how
   much data exists cannot masquerade as a change in behaviour.

2. **`pulse_pattern_list`** so you do not re-report a known finding, and
   **`pulse_vault_read("04-Config/profile.md")`** for what the user believes about
   themselves. Compare the two against the data.

3. **Read across rows, not down them.** A single entity's decline is a fact, not a
   finding. Several entities peaking and dying in sequence is a *rhythm*. Coursework
   platforms dying every December is a semester. Three unrelated things all collapsing
   in the same month is one event with a cause worth naming. **Grouping the raw domains
   into topics is your job** - the tool deliberately does not do it, because hard-coding
   categories would cap what can ever be found. You can see titles; use them.

4. **Test the hypothesis before recording it** with `pulse_query_events`. A pattern you
   cannot ground in specific events is a guess.

5. **Ask what it implies.** The best findings change a decision. "Your interests run in
   ten-week cycles and this one started six weeks ago" is more useful than any list of
   what those interests were.

6. **Record with `pulse_pattern_upsert`.** New, grounded, non-obvious, or do not record.
   Close faded patterns with `pulse_pattern_set_status`.

`pulse_change_surface` exists for recent-activity questions. It is **not** the tool for
discovery - what it returns is by construction what the user just did.

## Calibration

Recording nothing is a successful and common outcome. A real structural finding might
appear once a month. If you are recording something every run, the bar has slipped and
you are generating noise.

## Anti-patterns

Drawn from real failures in this vault:

- **Narrating recent activity.** The single most common failure. If the user could say
  "yes, I did that", it was not worth sending.
- **Logging absence as evidence.** Never write "no such activity this week" into an
  evidence log. Eight such entries once accumulated under one finding. Set the status
  instead.
- **Restating a pattern with a new number.** "Browsing normalized at 682 visits" was
  once recorded four times in a single day against a drifting baseline.
- **Reporting an un-normalised trend.** Total volume swings by an order of magnitude
  across a year; a raw count trend mostly measures how much history exists.
- **Treating one row as an insight.** A domain going quiet is a fact. What it means
  alongside four other rows is a finding.
- **Manufacturing a correlation** from same-day co-occurrence. Without a mechanism, it
  is a coincidence.
- **Padding.** If the honest answer is nothing, the answer is nothing.

# Self-Hosting Quickstart

Use this guide when you want the shortest real path from a fresh checkout to a running self-hosted Pulse instance.

## Before you start

- Run these commands from the repository root.
- Install the project so the `pulse` CLI is available. Either:

```bash
pip install -e .
```

or, if you use [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

- If you plan to use Google, Spotify, Microsoft 365, GitHub, or GitLab, create those OAuth apps first so you have client credentials ready for `.env`. For Plaid, create a Plaid developer application.

## One-command onboard (optional)

You can run the same path as steps 1–4 in one command:

```bash
pulse onboard
```

Before `pulse configure`, the CLI prints a short checklist (working directory, install, OAuth prep, Spotify callback on `localhost:8888`, and other localhost ports for Microsoft, GitHub, GitLab, and Plaid). After `pulse init`, it reminds you to open the app and use `pulse status` / `pulse insights` in another terminal.

By default, `pulse onboard` runs each OAuth / Plaid / Oura step only when that service’s credentials are in `.env` and the matching connector is enabled in `pulse.toml` (GitLab skips OAuth when `PULSE_GITLAB_TOKEN` is set; Plaid Link runs only when `plaid_tokens.json` does not exist yet).

To always run **all** configured auth and link steps (and exit with an error if a required step fails), use:

```bash
pulse onboard --strict
```

The same profile options as `pulse init` are accepted, for example:

```bash
pulse onboard -f ./my-profile.txt
pulse onboard --profile-text "Engineer in Austin; focus on health metrics."
```

Server flags match `pulse run` (`--host`, `--port`, `--log-level`).

## 1. Configure Pulse

Start with the interactive setup flow:

```bash
pulse configure
```

`pulse configure` is the self-hosting entry point. The menu:

- **Core** — database path, vault path, timezone.
- **Connectors** — pick a source: its `.env` keys, `pulse.toml` block, then OAuth / Plaid / Oura when you save with that source enabled (details in §2). Rows show **●**/**○** (enabled in `pulse.toml`), emoji, short name, **✓**/**✗** for `.env` prereqs when ●, poll interval.
- **Notifications** — **●**/**○** rows per outbound path (Telegram through SMTP, corrections webhook, companion / FCM, …); pick one to edit only its `.env` keys.
- **Model providers** — vendor API keys in `.env`.
- **LLM in pulse.toml** — wizard for `[llm]` provider plus summarization and discovery `model` ids (merges into `pulse.toml`; keeps `[llm.corrections]` if present). For Ollama, also prompts for the OpenAI-compatible base URL.
- **Full wizard** — core, all integrations, model keys, optional LLM roles step (TTY), all notification keys, every connector’s `pulse.toml`, then OAuth for each enabled connector (same coverage as `pulse onboard`’s configure phase).

Arrow keys + Enter in a TTY; otherwise type `0`–`6` (`0` = Done). When `.env` exists, wide prompts can **keep all existing values** for that section in one answer.

There is no committed `pulse.toml` in the repo (it is gitignored). Copy `pulse.toml.example` to `pulse.toml` or run `pulse configure`, which writes `pulse.toml` from your answers. The example file keeps **every** connector `enabled = false` so you opt in explicitly; `pulse configure` does the same for new connector blocks (press `y` to turn sources on). Typical intervals when you enable everything:

- Gmail every `15m`
- Google Calendar every `30m`
- YouTube every `1h`
- Spotify every `30m` with a supplementary pull every `6h`
- browser history every `15m`

## 2. OAuth, Plaid, and Oura (inside Connectors)

There is no separate `pulse auth …` command. From **`pulse configure` → Connectors**, pick each source you enabled (Gmail, Spotify, Microsoft 365, GitHub, GitLab, Plaid, Oura, …). After you save that connector’s `.env` and `pulse.toml` block with **●** (enabled), Pulse offers the same OAuth, Plaid Link, or Oura browser flows as before (localhost callbacks on `8888`, `8890`, `8891`, `8892`, `8893`, `8894` where applicable).

Finish those steps **before** `pulse init` if the first pull should hit those APIs. For **Notion**, **Linear** (API key), **browser**, **feeds**, etc., there is nothing to authorize in that menu.

## 3. Initialize your profile and first data pull

Run the bootstrap command:

```bash
pulse init
```

`pulse init` does the operator happy path in one command:

- creates or updates your vault profile in `04-Config/profile.md` (structured with the LLM when `PULSE_ANTHROPIC_API_KEY` is set; otherwise saved as a simple “Self description” section)
- performs the initial pull for active connectors
- aggregates stats
- optionally runs an initial **weekly** discovery pass when a discovery provider resolves; a single configured summarization/discovery role is reused for both, otherwise Pulse falls back to the legacy `PULSE_ANTHROPIC_API_KEY` path (discovery notifications are sent when any outbound channel is configured: Telegram, ntfy, or webhook URL)

## 4. Start the API server and scheduler

Once initialization succeeds, start Pulse:

```bash
pulse run
```

This boots the database schema, loads active connectors from `pulse.toml`, starts the scheduler, and serves the app on `0.0.0.0:8000` unless you override `--host`, `--port`, or `--log-level`.

The root URL (`/`) is a small operator page: it shows database and vault paths, connector counts, and how many scheduler jobs are registered. You can trigger **Pull**, **Digest**, **Discover**, and **Test Telegram** from the browser (roughly like `pulse pull`, `pulse digest`, `pulse discover`, and `pulse test-telegram`). The web **Digest** action uses the same digest pipeline as `pulse digest` and the **scheduled** `daily_digest` job (summarization LLM when configured, otherwise non-LLM fallback). The web **Discover** button runs daily cadence only—use the CLI for weekly or monthly passes.

## 5. Check that data is flowing

Use the status command to inspect the local store:

```bash
pulse status
```

`pulse status` prints the database path, total events, the observed time range, per-source counts, and connector sync cursors.

## 6. Review discovered patterns

When discovery has run, inspect the saved insights:

```bash
pulse insights
```

If no patterns exist yet, Pulse tells you to run discovery first. Otherwise it lists the discovered patterns, confidence values, and vault paths.

## Other CLI commands

- `pulse pull [sources…]` — run connector pulls immediately (default: all active pull connectors).
- `pulse digest [--date YYYY-MM-DD]` — aggregate stats and write the daily digest vault file for that day (today if omitted); uses the configured summarization provider when available, otherwise falls back to the non-LLM summarizer.
- `pulse discover [--cadence daily|weekly|monthly] [--date YYYY-MM-DD]` — run a discovery pass manually (works when a discovery provider resolves; a single configured summarization/discovery role is reused for both, otherwise Pulse falls back to the legacy `PULSE_ANTHROPIC_API_KEY` path).
- `pulse test-telegram` — send a one-off test message using your Telegram settings.
- `pulse cleanup [--dry-run]` — list or delete events whose timestamps are in the future (useful if bad data or clock skew landed in the database).

## Common operator flow

For a normal first-time setup, the happy path is:

```bash
pulse configure
pulse init
pulse run
```

Inside the first `pulse configure`, open **Connectors** and walk each OAuth-backed source **before** `pulse init`. Run `pulse configure` again any time you need to re-authorize (pick the same connector) or edit `.env` / `pulse.toml`.

After Pulse has been running for a while, the two fastest health checks are:

```bash
pulse status
pulse insights
```

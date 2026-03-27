# Self-Hosting Quickstart

Use this guide when you want the shortest real path from a fresh checkout to a running self-hosted Pulse instance.

If you are browsing the repo docs tree directly, start at [Pulse Docs](../index.md) for the full docs home.

## Before you start

- Run these commands from the repository root.
- Install the project in editable mode so the `pulse` CLI is available:

```bash
pip install -e .
```

- If you plan to use Google or Spotify, create those OAuth apps first so you have client credentials ready for `.env`.

## 1. Configure Pulse

Start with the interactive setup flow:

```bash
pulse configure
```

`pulse configure` is the real entry point for self-hosting. It walks through:

- core settings such as `PULSE_DATABASE_PATH`, `PULSE_VAULT_PATH`, and `PULSE_TIMEZONE`
- service credentials for Google, Spotify, Anthropic, and Telegram
- connector settings in `pulse.toml`

By default, the shipped `pulse.toml` enables these pull connectors:

- Gmail every `15m`
- Google Calendar every `30m`
- YouTube every `1h`
- Spotify every `30m` with a supplementary pull every `6h`
- browser history every `15m`

## 2. Authorize external services

If you enabled Google-backed connectors, run:

```bash
pulse auth google
```

That flow authorizes the enabled Google connectors in `pulse.toml`, which can include Gmail, Calendar, and YouTube.

If you enabled Spotify, run:

```bash
pulse auth spotify
```

Spotify opens a browser-based OAuth flow and saves tokens beside your Pulse database.

## 3. Initialize your profile and first data pull

Run the bootstrap command:

```bash
pulse init
```

`pulse init` does the operator happy path in one command:

- creates or updates your vault profile in `04-Config/profile.md`
- performs the initial pull for active connectors
- aggregates stats
- optionally runs the first discovery pass when `PULSE_ANTHROPIC_API_KEY` is set

## 4. Start the API server and scheduler

Once initialization succeeds, start Pulse:

```bash
pulse run
```

This boots the database schema, loads active connectors from `pulse.toml`, starts the scheduler, and serves the app on `0.0.0.0:8000` unless you override `--host`, `--port`, or `--log-level`.

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

## Common operator flow

For a normal first-time setup, the happy path is:

```bash
pulse configure
pulse auth google
pulse auth spotify
pulse init
pulse run
```

If you enabled Google-backed connectors, run `pulse auth google` before `pulse init`.

If you enabled Spotify, run `pulse auth spotify` before `pulse init`.

Skip the auth commands for services you did not enable.

After Pulse has been running for a while, the two fastest health checks are:

```bash
pulse status
pulse insights
```

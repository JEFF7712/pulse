# Connectors Index

Google (Gmail, Calendar, YouTube), Spotify, GitHub, Plaid, Oura, browser history. Template: **`pulse.toml.example`**; interactive setup: **`pulse configure`** (writes **`.config/pulse.toml`** by default).

Use **Configure → Connectors** for each source: credentials, enable (●), then OAuth/Plaid/Oura in the browser when prompted. Callback ports are noted per connector below. Finish OAuth-backed sources **before** [`pulse init`](https://pulseagent.dev/docs/self-hosting/quickstart.html) if the first pull should use them.

## Google

**Need:** `PULSE_GOOGLE_CLIENT_ID` / `SECRET`, ≥1 of `gmail` / `calendar` / `youtube` enabled, OAuth via Connectors.

**Pulls:** Gmail metadata, primary calendar titles, YouTube activity/likes/subs.

**Note:** OAuth runs only if at least one Google connector is enabled.

## Spotify

**Need:** Spotify OAuth app, client id/secret, `[connectors.spotify]` enabled, OAuth on **`localhost:8888`**.

**Pulls:** Recent plays, saved + top tracks/artists (short/medium/long windows).

## GitHub

**Need:** OAuth app → **`http://localhost:8891/callback`**, id/secret, `[connectors.github]` on.

**Pulls:** Recent user events (pushes, issues, PRs) as `dev.*`.

## Plaid

**Need:** Plaid dev account, `PULSE_PLAID_*`, `[connectors.plaid]` on; optional `omit_amounts_in_digest`. Link UI on **`localhost:8893`**. Tokens in **`plaid_tokens.json`** next to DB.

**Pulls:** Transactions via `/transactions/sync`.

## Oura

**PAT:** `PULSE_OURA_PERSONAL_ACCESS_TOKEN` — no OAuth.

**OAuth:** App → **`http://localhost:8894/callback`**, client id/secret. Re-auth if workouts were added later (needs workout scope).

**Pulls:** Sleep, readiness, activity, workouts (`health.*`). Days keyed as noon UTC for day-level aggregation.

## Browser

Local only. **`[connectors.browser]`** — `chrome` or `firefox`; process must read history DB (optional `db_path`).

**Pulls:** URL, title, timestamps, browser name.

**No events** if DB missing/unreadable.

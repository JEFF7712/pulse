# Connectors Index

Google (Gmail, Calendar, YouTube), Microsoft 365 mail/calendar, Spotify, GitHub, Linear, GitLab, Plaid, Notion, Oura, browser history, RSS/Atom. Template: **`pulse.toml.example`**; interactive setup: **`pulse configure`** (writes **`.config/pulse.toml`** by default).

Use **Configure → Connectors** for each source: credentials, enable (●), then OAuth/Plaid/Oura in the browser when prompted. Callback ports are noted per connector below. Finish OAuth-backed sources **before** [`pulse init`](../self-hosting/quickstart.md) if the first pull should use them.

## Google

**Need:** `PULSE_GOOGLE_CLIENT_ID` / `SECRET`, ≥1 of `gmail` / `calendar` / `youtube` enabled, OAuth via Connectors.

**Pulls:** Gmail metadata, primary calendar titles, YouTube activity/likes/subs.

**Note:** OAuth runs only if at least one Google connector is enabled.

## Spotify

**Need:** Spotify OAuth app, client id/secret, `[connectors.spotify]` enabled, OAuth on **`localhost:8888`**.

**Pulls:** Recent plays, saved + top tracks/artists (short/medium/long windows).

## Microsoft 365

**Need:** Entra app, redirect **`http://localhost:8890/callback`**, client id/secret, optional `PULSE_MICROSOFT_TENANT_ID` (`common` default), enable `microsoft_mail` / `microsoft_calendar`, OAuth in Connectors.

**Pulls:** Outlook mail metadata, calendar events.

**Note:** `calendar_id = "primary"` (or specific Graph id) under `[connectors.microsoft_calendar]`.

## GitHub

**Need:** OAuth app → **`http://localhost:8891/callback`**, id/secret, `[connectors.github]` on.

**Pulls:** Recent user events (pushes, issues, PRs) as `dev.*`.

## Linear

**Need:** [Personal API key](https://developers.linear.app/docs/graphql/working-with-the-graphql-api#personal-api-keys), `PULSE_LINEAR_API_KEY`, `[connectors.linear]` on. No OAuth.

**Pulls:** Assigned issues (~14d first sync) as `dev.linear.issue`.

**Note:** Assumes API returns issues ordered by newest `updatedAt`.

## GitLab

**OAuth:** App redirect **`http://localhost:8892/callback`**, id/secret, `gitlab_base_url` (default `https://gitlab.com`), OAuth in Connectors.

**PAT:** `PULSE_GITLAB_TOKEN` only — skips OAuth.

**Pulls:** `/api/v4/events` as `dev.*`.

## Plaid

**Need:** Plaid dev account, `PULSE_PLAID_*`, `[connectors.plaid]` on; optional `omit_amounts_in_summary`. Link UI on **`localhost:8893`**. Tokens in **`plaid_tokens.json`** next to DB.

**Pulls:** Transactions via `/transactions/sync`.

## Notion

**Need:** [Internal integration](https://developers.notion.com/docs/create-a-notion-integration) secret → `PULSE_NOTION_TOKEN`, share pages/DBs with integration, `[connectors.notion]` on.

**Optional:** `database_ids` — explicit DB queries plus workspace search.

**Pulls:** Recent pages/DBs from search (+ listed DBs) as `notion.page_edited`.

**Note:** First sync ~14d `last_edited_time`; respect rate limits / `poll_interval`.

## Oura

**PAT:** `PULSE_OURA_PERSONAL_ACCESS_TOKEN` — no OAuth.

**OAuth:** App → **`http://localhost:8894/callback`**, client id/secret. Re-auth if workouts were added later (needs workout scope).

**Pulls:** Sleep, readiness, activity, workouts (`health.*`). Days keyed as noon UTC for day-level aggregation.

## Browser

Local only. **`[connectors.browser]`** — `chrome` or `firefox`; process must read history DB (optional `db_path`).

**Pulls:** URL, title, timestamps, browser name.

**No events** if DB missing/unreadable.

## RSS / Atom

**Need:** `[connectors.feeds]`, `urls = ["…"]`. No keys.

**Pulls:** Entries as `feed.item`.

**Note:** Bad UA / auth sites may fail (logged); entries need parseable dates.

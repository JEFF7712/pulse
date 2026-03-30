# Connectors Index

Pulse ships pull connectors for Google (Gmail, Calendar, YouTube), Microsoft 365 (Outlook mail and calendar), Spotify, GitHub, Linear, GitLab, Plaid (bank transactions), Notion, Oura Ring (sleep, readiness, activity, and workouts), local browser history, and RSS/Atom feeds (no API keys for feeds). There is no committed config file—use `pulse.toml.example` as a template; `pulse configure` writes **`.config/pulse.toml`** by default (or repo-root `pulse.toml` if you use the repository-root fallback layout). This page gives the setup path for each connector.

OAuth, Plaid Link, and Oura Cloud OAuth run from **`pulse configure` → Connectors**: pick a source, save its credentials in `pulse.toml` with that connector **enabled** (●); token prompts appear at the end of that flow when needed.

## Google

Google authentication covers the Google-backed connectors Pulse can enable: Gmail, Google Calendar, and YouTube.

### Prerequisites

- set `PULSE_GOOGLE_CLIENT_ID` and `PULSE_GOOGLE_CLIENT_SECRET` in `pulse.toml` (or env), usually through `pulse configure`
- keep at least one Google connector enabled in `pulse.toml` (`gmail`, `calendar`, or `youtube`)
- complete OAuth from `pulse configure` → **Connectors** → a Google-backed source (Gmail, Calendar, or YouTube); saving with the connector enabled starts the Google OAuth flow

### What Pulse pulls

- Gmail message metadata such as subject and sender
- Google Calendar event titles from your primary calendar
- YouTube activity, liked videos, and subscriptions

### Caveat

Google OAuth requires at least one Google connector enabled in `pulse.toml` before the flow runs.

## Spotify

Spotify is configured separately from Google and uses its own OAuth flow.

### Prerequisites

- set `PULSE_SPOTIFY_CLIENT_ID` and `PULSE_SPOTIFY_CLIENT_SECRET` in `pulse.toml` (or env), usually through `pulse configure`
- keep `[connectors.spotify] enabled = true` in `pulse.toml`
- complete OAuth from `pulse configure` → **Connectors** → Spotify; save with the connector enabled

### What Pulse pulls

- recently played tracks
- saved tracks
- top tracks across short, medium, and long-term windows
- top artists across short, medium, and long-term windows

### Caveat

Spotify OAuth starts a localhost callback server on port `8888`, so the browser redirect must be able to return to the machine running Pulse.

## Microsoft 365

Microsoft Graph covers Outlook mail and calendar using one token file. Register a confidential client in [Microsoft Entra ID](https://entra.microsoft.com/) (Azure AD) with a **Web** or **Mobile and desktop** redirect URI of `http://localhost:8890/callback`.

### Prerequisites

- set `PULSE_MICROSOFT_CLIENT_ID` and `PULSE_MICROSOFT_CLIENT_SECRET` in `pulse.toml` (or env)
- optional: `PULSE_MICROSOFT_TENANT_ID` (defaults to `common` for multi-tenant sign-in)
- enable `microsoft_mail` and/or `microsoft_calendar` in `pulse.toml`
- authorize from `pulse configure` → **Connectors** → Outlook mail or 365 calendar; save with the connector enabled

### What Pulse pulls

- Outlook messages as `email.received` (subject and sender metadata)
- Calendar events as `calendar.event` (title and start time)

### Caveat

Use `calendar_id = "primary"` under `[connectors.microsoft_calendar]` for your default calendar, or set a specific Graph calendar id.

## GitHub

### Prerequisites

- GitHub OAuth App with callback `http://localhost:8891/callback`
- `PULSE_GITHUB_CLIENT_ID` and `PULSE_GITHUB_CLIENT_SECRET` in `pulse.toml` (or env)
- `[connectors.github] enabled = true`
- authorize from `pulse configure` → **Connectors** → GitHub; save with the connector enabled

### What Pulse pulls

- Recent authenticated user events (pushes, issues, pull requests, etc.) as `dev.*` events for digests.

## Linear

Linear uses a [personal API key](https://developers.linear.app/docs/graphql/working-with-the-graphql-api#personal-api-keys) (no OAuth in Pulse). The connector syncs **issues assigned to you** (the key’s user).

### Prerequisites

- Create an API key in Linear (Settings → API → Personal API keys).
- Set `PULSE_LINEAR_API_KEY` in `pulse.toml` (or env) (same value the Linear UI shows; Pulse sends it as the `Authorization` header).
- Enable `[connectors.linear]` in `pulse.toml`.

There is no OAuth step for Linear.

### What Pulse pulls

- Assigned issues updated since the last sync cursor (or within about the **last 14 days** on the first pull) as `dev.linear.issue` events. They appear under **Development** in digests alongside GitHub/GitLab activity.

### Caveat

Paging assumes issues are ordered by **newest `updatedAt` first** (as requested from the API). If that ordering changes, the 14-day window may be incomplete until the next full scan.

## GitLab

Use either OAuth or a [personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html).

### OAuth

- GitLab OAuth application with redirect `http://localhost:8892/callback` (must match your `gitlab_base_url` host)
- `PULSE_GITLAB_CLIENT_ID` and `PULSE_GITLAB_CLIENT_SECRET` in `pulse.toml` (or env)
- `[connectors.gitlab]` with `gitlab_base_url` (default `https://gitlab.com`)
- authorize from `pulse configure` → **Connectors** → GitLab; save with the connector enabled

### Personal access token

- set `PULSE_GITLAB_TOKEN` in `pulse.toml` (or env) and omit OAuth; Pulse uses the `PRIVATE-TOKEN` header against the GitLab API.

### What Pulse pulls

- Recent `/api/v4/events` entries as `dev.*` events.

## Plaid

Plaid links a financial institution and syncs transactions. Tokens and Plaid cursors are stored in `plaid_tokens.json` beside your database (same sensitivity as other OAuth token files—protect the directory).

### Prerequisites

- Plaid developer account; set `PULSE_PLAID_CLIENT_ID`, `PULSE_PLAID_SECRET`, and `PULSE_PLAID_ENV` (`sandbox`, `development`, or `production`)
- enable `[connectors.plaid]`; optional `omit_amounts_in_digest = true` to hide dollar amounts in digest markdown (events still store amounts)
- run Plaid Link from `pulse configure` → **Connectors** → Plaid; save with the connector enabled

This starts a small server on `http://localhost:8893/`, opens Plaid Link, and exchanges the `public_token` for an `access_token`.

### What Pulse pulls

- New transactions via Plaid `/transactions/sync` as `finance.transaction` events.

## Notion

Notion uses an [internal integration](https://developers.notion.com/docs/create-a-notion-integration) (API secret). Share any **pages or databases** you want Pulse to see with that integration in the Notion UI.

### Prerequisites

- Create an integration in Notion and copy the **Internal Integration Secret** into `PULSE_NOTION_TOKEN` in `pulse.toml` (or env)
- Enable `[connectors.notion]` in `pulse.toml`
- Share target pages/databases with the integration (Share → invite your integration)

### Optional database list

Add UUIDs under `database_ids` in `[connectors.notion]` to run the [Query a database](https://developers.notion.com/reference/post-database-query) API on each database **in addition to** workspace [search](https://developers.notion.com/reference/post-search). Search already returns recently edited pages the integration can access; explicit IDs help ensure rows from large databases are polled even if they do not surface in search ordering.

### What Pulse pulls

- Recently edited **pages** and **databases** from search, and optionally all rows from listed databases (sorted by `last_edited_time`), as `notion.page_edited` events with title, URL, object type, and whether the row came from `search` or `database` query.

### Caveat

The first successful pull without a prior sync cursor only considers edits within about the **last 14 days** (by `last_edited_time`). Notion rate limits apply; keep a reasonable `poll_interval` (default `45m` in examples).

## Oura Ring

Oura exposes daily sleep and readiness through the [Oura Cloud API v2](https://cloud.ouraring.com/docs/). Use either a **personal access token** (simplest for self-hosting) or **OAuth**.

### Personal access token

- Create a token in the Oura developer / Cloud dashboard (Personal Access Token).
- Set `PULSE_OURA_PERSONAL_ACCESS_TOKEN` in `pulse.toml` (or env) and omit OAuth client fields.
- Enable `[connectors.oura]` in `pulse.toml`

No OAuth step is required when using a PAT.

### OAuth

- Register an API application with redirect URI `http://localhost:8894/callback`.
- Set `PULSE_OURA_CLIENT_ID` and `PULSE_OURA_CLIENT_SECRET` in `pulse.toml` (or env).
- Enable `[connectors.oura]` in `pulse.toml`.
- authorize from `pulse configure` → **Connectors** → Oura; save with the connector enabled

### What Pulse pulls

- Daily sleep summaries as `health.sleep` (score, time asleep / in bed, efficiency, deep/REM/light when the API returns them, bedtime hints when present).
- Daily readiness as `health.readiness` (score and contributor fields when present).
- Daily activity as `health.activity` (steps, activity score, active calories, walk-equivalent distance when present).
- Logged workouts as `health.workout` (sport/activity name, start time, duration, calories when present). OAuth uses the **workout** scope alongside **daily**; if you authorized before workouts were added, open **Connectors** → Oura again and re-run OAuth. If the API still returns 403/404 for workouts, Pulse logs a warning and continues without them.

### Caveat

Oura labels each row with a **calendar day**; Pulse stores a noon-UTC timestamp on that day so digests bucket rows consistently with `list_events_for_day`.

## Browser History

The browser history connector is local-only and does not use OAuth.

### Prerequisites

- leave `[connectors.browser] enabled = true` in `pulse.toml`
- set the browser type in `pulse.toml` to `chrome` or `firefox`
- make sure the Pulse process can read the local browser history database, or provide an explicit `db_path` (`pulse configure` prompts for this path when the browser connector is enabled)

If you need to point Pulse at a non-default history file, put it under `[connectors.browser]` in `pulse.toml`:

```toml
[connectors.browser]
enabled = true
poll_interval = "15m"
browser = "chrome"
db_path = "/path/to/browser-history.sqlite"
```

### What Pulse pulls

- browsing visits with the page URL
- page title when available
- normalized visit timestamps
- the browser name used for the pull

### Caveat

The browser history connector returns no events when it cannot find or read the local history SQLite database.

## RSS and Atom feeds

The feeds connector polls HTTP URLs that return RSS 2.0 or Atom XML. No OAuth or API keys are required.

### Prerequisites

- set `[connectors.feeds] enabled = true` in `pulse.toml`
- add at least one URL to the `urls` array (comma-separated strings in TOML)

```toml
[connectors.feeds]
enabled = true
poll_interval = "1h"
urls = ["https://example.com/news.xml"]
```

You can list multiple feeds; Pulse merges items from all of them. `pulse configure` can prompt for URLs when you enable this connector.

### What Pulse pulls

- each feed entry as a `feed.item` event with title, link, feed URL, and feed title

### Caveat

Sites that block non-browser user agents or require authentication may return errors; failed fetches are logged and other feeds still run. Entries without a parseable publication date are skipped.

## Setup order

For most operators, the connector flow is:

```bash
pulse configure
pulse init
```

Inside `pulse configure` → **Connectors**, enable each source and complete OAuth / Plaid / Oura there before `pulse init` when you need those APIs. Skip Oura OAuth when using `PULSE_OURA_PERSONAL_ACCESS_TOKEN`. Notion uses `PULSE_NOTION_TOKEN` only. Linear uses `PULSE_LINEAR_API_KEY` only.

# Connectors Index

Pulse ships pull connectors for Google (Gmail, Calendar, YouTube), Microsoft 365 (Outlook mail and calendar), Spotify, GitHub, GitLab, Plaid (bank transactions), local browser history, and RSS/Atom feeds (no API keys for feeds). There is no committed `pulse.toml`—use `pulse.toml.example` or the file written by `pulse configure`. This page gives the setup path for each connector.

## Google

Google authentication covers the Google-backed connectors Pulse can enable: Gmail, Google Calendar, and YouTube.

### Prerequisites

- set `PULSE_GOOGLE_CLIENT_ID` and `PULSE_GOOGLE_CLIENT_SECRET` in `.env`, usually through `pulse configure`
- keep at least one Google connector enabled in `pulse.toml` (`gmail`, `calendar`, or `youtube`)
- complete OAuth with:

```bash
pulse auth google
```

### What Pulse pulls

- Gmail message metadata such as subject and sender
- Google Calendar event titles from your primary calendar
- YouTube activity, liked videos, and subscriptions

### Caveat

`pulse auth google` exits if no Google connectors are enabled in `pulse.toml`, so enable Gmail, Calendar, or YouTube before starting OAuth.

## Spotify

Spotify is configured separately from Google and uses its own OAuth flow.

### Prerequisites

- set `PULSE_SPOTIFY_CLIENT_ID` and `PULSE_SPOTIFY_CLIENT_SECRET` in `.env`, usually through `pulse configure`
- keep `[connectors.spotify] enabled = true` in `pulse.toml`
- complete OAuth with:

```bash
pulse auth spotify
```

### What Pulse pulls

- recently played tracks
- saved tracks
- top tracks across short, medium, and long-term windows
- top artists across short, medium, and long-term windows

### Caveat

`pulse auth spotify` starts a localhost callback server on port `8888`, so the browser redirect must be able to return to the machine running Pulse.

## Microsoft 365

Microsoft Graph covers Outlook mail and calendar using one token file. Register a confidential client in [Microsoft Entra ID](https://entra.microsoft.com/) (Azure AD) with a **Web** or **Mobile and desktop** redirect URI of `http://localhost:8890/callback`.

### Prerequisites

- set `PULSE_MICROSOFT_CLIENT_ID` and `PULSE_MICROSOFT_CLIENT_SECRET` in `.env`
- optional: `PULSE_MICROSOFT_TENANT_ID` (defaults to `common` for multi-tenant sign-in)
- enable `microsoft_mail` and/or `microsoft_calendar` in `pulse.toml`
- run:

```bash
pulse auth microsoft
```

### What Pulse pulls

- Outlook messages as `email.received` (subject and sender metadata)
- Calendar events as `calendar.event` (title and start time)

### Caveat

Use `calendar_id = "primary"` under `[connectors.microsoft_calendar]` for your default calendar, or set a specific Graph calendar id.

## GitHub

### Prerequisites

- GitHub OAuth App with callback `http://localhost:8891/callback`
- `PULSE_GITHUB_CLIENT_ID` and `PULSE_GITHUB_CLIENT_SECRET` in `.env`
- `[connectors.github] enabled = true`

```bash
pulse auth github
```

### What Pulse pulls

- Recent authenticated user events (pushes, issues, pull requests, etc.) as `dev.*` events for digests.

## GitLab

Use either OAuth or a [personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html).

### OAuth

- GitLab OAuth application with redirect `http://localhost:8892/callback` (must match your `gitlab_base_url` host)
- `PULSE_GITLAB_CLIENT_ID` and `PULSE_GITLAB_CLIENT_SECRET` in `.env`
- `[connectors.gitlab]` with `gitlab_base_url` (default `https://gitlab.com`)

```bash
pulse auth gitlab
```

### Personal access token

- set `PULSE_GITLAB_TOKEN` in `.env` and omit OAuth; Pulse uses the `PRIVATE-TOKEN` header against the GitLab API.

### What Pulse pulls

- Recent `/api/v4/events` entries as `dev.*` events.

## Plaid

Plaid links a financial institution and syncs transactions. Tokens and Plaid cursors are stored in `plaid_tokens.json` beside your database (same sensitivity as other OAuth token files—protect the directory).

### Prerequisites

- Plaid developer account; set `PULSE_PLAID_CLIENT_ID`, `PULSE_PLAID_SECRET`, and `PULSE_PLAID_ENV` (`sandbox`, `development`, or `production`)
- enable `[connectors.plaid]`; optional `omit_amounts_in_digest = true` to hide dollar amounts in digest markdown (events still store amounts)

```bash
pulse auth plaid
```

This starts a small server on `http://localhost:8893/`, opens Plaid Link, and exchanges the `public_token` for an `access_token`.

### What Pulse pulls

- New transactions via Plaid `/transactions/sync` as `finance.transaction` events.

## Browser History

The browser history connector is local-only and does not use OAuth.

### Prerequisites

- leave `[connectors.browser] enabled = true` in `pulse.toml`
- set the browser type in `pulse.toml` to `chrome` or `firefox`
- make sure the Pulse process can read the local browser history database, or provide an explicit `db_path`

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
pulse auth google
pulse auth spotify
pulse auth microsoft
pulse auth github
pulse auth gitlab
pulse auth plaid
pulse init
```

Run only the `pulse auth …` commands for connectors you enabled and configured.

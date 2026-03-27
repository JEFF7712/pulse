# Connectors Index

Pulse ships pull connectors for Google (Gmail, Calendar, YouTube), Spotify, local browser history, and RSS/Atom feeds (no API keys). There is no committed `pulse.toml`—use `pulse.toml.example` or the file written by `pulse configure` (the example enables Google sources and browser history but leaves Spotify and feeds disabled until you turn them on). This page gives the setup path for each connector.

If you want the overall operator flow first, start from [Pulse Docs](../index.md).

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
pulse init
```

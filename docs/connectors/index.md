# Connectors Index

Pulse currently ships with Google, Spotify, and browser history pull connectors enabled in the default `pulse.toml`. This page gives the real setup path for each one.

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

## Setup order

For most operators, the connector flow is:

```bash
pulse configure
pulse auth google
pulse auth spotify
pulse init
```

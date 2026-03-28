# Pulse Companion App — Design Spec

**Date:** 2026-03-27
**Status:** Approved

---

## Overview

A Flutter companion app for iOS that provides three capabilities Pulse cannot get from server-side APIs: location tracking, HealthKit data, and native push notifications. The app also serves as a daily digest reader with inline correction support, replacing Telegram as the primary mobile interface.

## Design Principles

- **App-as-push-connector.** The app is another data source in Pulse's connector architecture. Location and health events flow through the same `Event` → store → analysis pipeline as Gmail, Spotify, and every other source.
- **Thin client.** Business logic stays on the server. The app collects sensor data, renders digests, and submits corrections. It does not run analysis, summarization, or discovery.
- **Offline-resilient.** Events queue locally on the phone and flush when connectivity returns. No data is lost if the server is unreachable.

---

## Architecture

### Connectivity

The app connects directly to the Pulse FastAPI server over the local network. The expected setup is Tailscale (or any VPN/mesh) so the server does not need to be exposed to the public internet.

Auth is a shared secret token (`PULSE_COMPANION_TOKEN` in `.env`), sent as an `X-Pulse-Token` header on every request. This is a single-user self-hosted system — OAuth would add complexity without meaningful security benefit.

### API Surface

**Data ingestion (app → server):**

```
POST /webhooks/companion
Header: X-Pulse-Token: <token>
Body: {
  "events": [
    {
      "type": "location.enter" | "location.exit" | "health.steps" | "health.sleep",
      "timestamp": "2026-03-27T09:15:00Z",
      "data": { ... }
    }
  ]
}
```

Implemented as a `PushConnector` registered in the connector registry, following the same pattern as the Telegram webhook.

**Digest reading (app → server):**

```
GET /api/digests/{date}    → digest markdown for the given date
GET /api/digests/latest    → most recent digest
Header: X-Pulse-Token: <token>
```

**Corrections (app → server):**

```
POST /api/corrections
Header: X-Pulse-Token: <token>
Body: { "context_id": "2026-03-27", "message_text": "The deadline is actually Friday." }
```

Reuses `CorrectionService.record_correction()` — identical code path to Telegram replies and MCP `pulse_correct`.

**Device token registration (app → server):**

```
POST /api/device-token
Header: X-Pulse-Token: <token>
Body: { "token": "<fcm-device-token>", "platform": "ios" }
```

**Push notifications (server → app):**

Server sends via FCM HTTP v1 API using a service account. A new `FCMChannel` implements the existing `NotificationChannel` protocol, sitting alongside `TelegramChannel`. Both channels can be active simultaneously.

Notification payload includes `context_id` so tapping opens the relevant digest with correction input focused.

---

## Flutter App Structure

```
app/
├── ios/                          # Xcode project, APNs entitlements, HealthKit capability
├── lib/
│   ├── main.dart
│   ├── config/
│   │   └── server_config.dart    # Server URL + token, persisted in secure storage
│   ├── services/
│   │   ├── api_client.dart       # Dio HTTP client for Pulse server
│   │   ├── location_service.dart # Geofence management + significant change monitoring
│   │   ├── health_service.dart   # HealthKit reads (steps + sleep)
│   │   ├── push_service.dart     # FCM token registration + notification handling
│   │   └── event_queue.dart      # Local SQLite queue for offline resilience
│   ├── models/
│   │   ├── digest.dart           # Daily digest display model
│   │   ├── geofence.dart         # Named place: lat, lng, radius, name
│   │   └── correction.dart       # Correction submission model
│   ├── screens/
│   │   ├── setup_screen.dart     # First-run: enter server URL + token, test connection
│   │   ├── home_screen.dart      # Today's digest + quick correction input
│   │   ├── digest_screen.dart    # Full digest reader with date picker
│   │   └── places_screen.dart    # Map view to manage geofences + review suggestions
│   └── widgets/
│       ├── digest_card.dart      # Rendered digest section
│       └── correction_input.dart # Text field + submit for inline corrections
├── pubspec.yaml
└── test/
```

### Key Packages

| Package | Purpose |
|---------|---------|
| `dio` | HTTP client |
| `provider` | State management |
| `geolocator` | Location permissions + significant change monitoring |
| `geofencing_api` or platform channels | iOS region monitoring for geofences |
| `health` | HealthKit access (steps, sleep) |
| `firebase_messaging` | FCM push notifications |
| `flutter_local_notifications` | Foreground notification display |
| `google_maps_flutter` | Map view for places management |
| `sqflite` | Local event queue for offline resilience |
| `flutter_secure_storage` | Persist server URL + token |

### Screens

1. **Setup** — first-run only. Enter Pulse server URL and companion token. Tests the connection before proceeding. Stored in secure storage.
2. **Home** — today's digest rendered from markdown. Correction text input at the bottom. Push notifications deep-link here with the relevant context_id.
3. **Digest** — date picker to browse past digests. Same rendering as home but for any date.
4. **Places** — map view showing active geofences as circles. Add/edit/delete named places. Auto-discovered suggestions appear as dashed circles the user can confirm or dismiss.

---

## Background Services

### Location Tracking

Three strategies run simultaneously:

**1. Active geofences (iOS region monitoring)**
User-defined places monitored via `CLLocationManager` region monitoring. Enter/exit events fire immediately, even when the app is terminated. iOS limits this to ~20 monitored regions.

**2. Significant location changes**
iOS wakes the app on cell tower transitions (~500m+ movement). Low battery impact. Used to detect dwell time at unknown locations for auto-discovery.

**3. Auto-discovery (on-device)**
When the app observes repeated significant-change dwell time at the same coordinates (3+ visits, 30+ minutes each), it stores a suggestion in local storage. Next time the user opens the Places screen, they see "You've been here 4 times — want to name this place?" Confirmed suggestions become active geofences.

**Event format:**
```json
{
  "type": "location.enter",
  "timestamp": "2026-03-27T09:05:00Z",
  "data": {"place": "office", "lat": 40.7128, "lng": -74.0060}
}
{
  "type": "location.exit",
  "timestamp": "2026-03-27T18:15:00Z",
  "data": {"place": "office", "duration_minutes": 550}
}
```

### Health Data

The app syncs HealthKit data on a timer (every 2 hours in background, immediately on app foreground). Reads since last sync timestamp:

**Steps** — daily total, one `health.steps` event per day:
```json
{
  "type": "health.steps",
  "timestamp": "2026-03-27T23:59:00Z",
  "data": {"count": 8420}
}
```

**Sleep** — sleep analysis samples, one `health.sleep` event per sleep session:
```json
{
  "type": "health.sleep",
  "timestamp": "2026-03-27T07:15:00Z",
  "data": {"in_bed_minutes": 465, "asleep_minutes": 410}
}
```

### Offline Queue

All events (location, health) are written to a local SQLite table before being sent to the server. On successful POST, rows are deleted. A background task retries unsent events when connectivity returns. The queue prevents data loss during server downtime or network interruptions.

---

## Backend Changes

### New Files

| File | Purpose |
|------|---------|
| `src/pulse/connectors/companion.py` | `PushConnector` parsing location + health event batches |
| `src/pulse/notifications/fcm.py` | `FCMChannel` implementing `NotificationChannel` via FCM HTTP v1 |
| `src/pulse/app/api.py` | REST router: `/api/digests/{date}`, `/api/corrections`, `/api/device-token` |
| `src/pulse/app/auth.py` | `X-Pulse-Token` header verification as a FastAPI dependency |
| `src/pulse/store/device_tokens.py` | Repository for FCM device token storage |

### Modified Files

| File | Change |
|------|--------|
| `src/pulse/app/config.py` | Add `companion_token`, `fcm_service_account_path` fields |
| `src/pulse/app/main.py` | Mount `/api` router, register companion push connector |
| `src/pulse/store/schema.py` | Add `device_tokens` table |
| `pulse.toml.example` | Add `[connectors.companion]` section |
| `.env.example` | Add `PULSE_COMPANION_TOKEN`, `PULSE_FCM_SERVICE_ACCOUNT_PATH` |

### Not Changed

The core pipeline is untouched. `CorrectionService`, `VaultMemory`, event store, discovery engine, and summarizer all work on arbitrary events. Location and health events enter as `source: "companion"` and flow through the existing analysis pipeline. The LLM sees event data like "location.enter office at 9am" alongside "gmail.received" and "github.commit" and finds cross-source patterns on its own.

---

## What This Design Does Not Include

- **Android support** — iOS first. Flutter makes Android possible later with platform-specific service implementations.
- **Workout tracking** — only steps and sleep for v1. Workouts can be added as additional HealthKit queries.
- **Heart rate** — high volume, unclear pattern value. Deferred.
- **Full vault browser** — the app reads digests only. Vault browsing stays in Obsidian.
- **Rich notification actions** — tapping opens the digest. Quick-reply from the notification shade is a future enhancement.

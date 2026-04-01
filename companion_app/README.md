# Pulse Companion (Flutter)

Mobile client for Pulse: server URL + companion token, latest digest, date browser, corrections (`POST /api/corrections`), optional FCM, and background-friendly **steps / sleep / location snapshot** events queued to `POST /webhooks/companion` when the server has the companion connector enabled. Targets iOS first; Android uses Health Connect for the same health types.

Setup and commands: see [../CONTRIBUTING.md](../CONTRIBUTING.md) (Companion app section).

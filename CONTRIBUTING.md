# Contributing to Pulse

Thanks for helping improve Pulse. This document covers how to set up a development environment, run the same checks as CI, and what we look for in contributions.

## Before you start

- **Issues and design discussion** — For larger changes (new connectors, breaking config, or new dependencies), opening an issue first helps align on direction and avoids duplicate work.
- **Secrets** — Never commit API keys, OAuth tokens, or real `pulse.toml` paths that expose your setup. Use `pulse.toml.example` and environment variables as references.

## Development setup

**Recommended: [uv](https://docs.astral.sh/uv/)**

```bash
uv sync --group dev
```

**Nix** — From the repo root: `nix develop`, then use the provided environment (uv keeps `.venv` in sync). The shell also includes **Flutter** (Dart, `flutter pub get`, `flutter test`, …), **JDK 17** (`JAVA_HOME` for Android Gradle), and on Linux, GTK-related build inputs for optional `flutter run -d linux`.

**Classic venv** — Create a virtualenv, then `pip install -e .` and `pip install pytest` (or install the `dev` group equivalent).

More context on config paths and env vars: [Configuration reference](https://pulseagent.dev/docs/reference/configuration.html). Install and run: [Self-hosting quickstart](https://pulseagent.dev/docs/self-hosting/quickstart.html).

## Run tests (match CI)

Continuous integration runs on Python **3.12** and **3.13** against a locked dependency set:

```bash
uv sync --group dev --locked
uv run pytest tests/ --tb=short -q
```

Optional local parity with CI:

```bash
uv build
uv run python scripts/smoke_installed_package.py dist
```

## Pull requests

- **Target branch** — Open PRs against `main`.
- **Description** — Summarize what changed and why. Link related issues if any.
- **Scope** — Prefer focused changes (one logical concern per PR) so review and bisection stay easy.
- **Docs** — If behavior or configuration changes, update the relevant files under `docs/` when applicable.

## Project layout

Python package source lives under `src/pulse/`. High-level areas:

| Path | Role |
|------|------|
| `src/pulse/app/` | FastAPI app, CLI, config |
| `src/pulse/connectors/` | Data source integrations |
| `src/pulse/domain/event_types.py` | Canonical `event_type` strings and preprocessor buckets — register new types when adding a connector |
| `src/pulse/mcp/` | MCP server |
| `src/pulse/store/` | SQLite persistence |
| `tests/` | Pytest suite |
| `companion_app/` | Flutter iOS companion (insights, corrections; see design in repo docs) |

### Companion app (Flutter)

From `companion_app/`: install the [Flutter SDK](https://docs.flutter.dev/get-started/install), then `flutter pub get`. The repo includes `ios/` and `android/` scaffolding; if you strip them locally, regenerate with `flutter create . --platforms=ios,android` (it preserves `lib/`). Run `flutter test` and `flutter run` on a device or simulator.

**Push (FCM):** The app registers the device with Pulse (`POST /api/device-token`) when Firebase initializes. Add your Firebase project files: **`ios/Runner/GoogleService-Info.plist`** (Xcode → Runner). For Android, add **`android/app/google-services.json`** and apply the [Google services Gradle plugin](https://firebase.google.com/docs/flutter/setup?platform=android) to `android/settings.gradle.kts` and `android/app/build.gradle.kts`. Without those files the app still runs; push setup is skipped at runtime. Enable the Push Notifications capability and APNs in the Apple Developer portal for production iOS builds.

**Health & location:** The app reads steps and sleep (HealthKit on iOS, Health Connect on Android) and occasionally records a coarse `location.enter` snapshot (`place: snapshot`), queues events locally, and POSTs batches to `/webhooks/companion`. Enable the **`companion`** connector on the Pulse server. In Xcode, add the **HealthKit** capability (in addition to the `Info.plist` strings already in the template). On Android, `MainActivity` extends **`FlutterFragmentActivity`** (required for Health Connect permission flows on newer APIs); install the Health Connect app and grant **Steps** and **Sleep** read access when prompted.

## License

By contributing, you agree your contributions are licensed under the same terms as the project ([Apache License 2.0](LICENSE)).

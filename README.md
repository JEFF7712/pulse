# Pulse Backend-First MVP

This repository contains the backend-first MVP for Pulse. The app exposes a small FastAPI service, stores data in SQLite, and writes human-readable output into a local vault directory.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . pytest uvicorn
```

`.env.example` is a sample of the current config values and defaults. The app does not auto-load a `.env` file yet, so set environment variables manually only if you need to override the defaults.

## Run tests

```bash
python -m pytest
```

## Start the app

Start the FastAPI app from the repository root:

```bash
python -m uvicorn --app-dir src pulse.app.main:create_app --factory
```

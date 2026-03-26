# Self-Hosted Docs and Site Docs Portal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add operator-first self-hosting docs to the repo and a matching `/docs/` landing page to the static site.

**Architecture:** Keep the repo as the source of truth for documentation, with task-oriented markdown pages under `docs/`. Add a lightweight static `site/docs/index.html` page that routes visitors to the right repo docs and extend smoke coverage so the site proves both `/` and `/docs/` still work.

**Tech Stack:** Markdown, Python/pytest, static HTML/CSS, nginx container smoke test, existing CLI/config code in `src/pulse/app`

---

### Task 1: Add a docs contract test and wire the README to the new docs set

**Files:**
- Create: `tests/unit/test_documentation_contract.py`
- Modify: `README.md`
- Create: `docs/self-hosting/quickstart.md`
- Create: `docs/reference/configuration.md`
- Create: `docs/operations/runbook.md`
- Create: `docs/connectors/index.md`

**Step 1: Write the failing test**

Create `tests/unit/test_documentation_contract.py` with a small contract for the new docs surface:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def test_operator_docs_exist() -> None:
    for relative_path in [
        "docs/self-hosting/quickstart.md",
        "docs/reference/configuration.md",
        "docs/operations/runbook.md",
        "docs/connectors/index.md",
    ]:
        assert (ROOT / relative_path).exists(), f"Missing {relative_path}"


def test_readme_points_to_operator_docs() -> None:
    readme = _read("README.md")
    assert "docs/self-hosting/quickstart.md" in readme
    assert "docs/reference/configuration.md" in readme
    assert "docs/operations/runbook.md" in readme
    assert "docs/connectors/index.md" in readme
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: FAIL because the new docs files do not exist yet and `README.md` does not link to them.

**Step 3: Write minimal implementation**

- Add a short "Docs" section to `README.md` with links to the new pages.
- Create the four markdown files with title headings and a one-paragraph placeholder intro so the paths exist immediately.

Use this `README.md` section shape:

```md
## Docs

- [Self-hosted quickstart](docs/self-hosting/quickstart.md)
- [Configuration reference](docs/reference/configuration.md)
- [Operations runbook](docs/operations/runbook.md)
- [Connector setup](docs/connectors/index.md)
```

Use these placeholder headings:

```md
# Self-Hosted Quickstart
```

```md
# Configuration Reference
```

```md
# Operations Runbook
```

```md
# Connector Setup
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md tests/unit/test_documentation_contract.py docs/self-hosting/quickstart.md docs/reference/configuration.md docs/operations/runbook.md docs/connectors/index.md
git commit -m "docs: scaffold self-hosting documentation set"
```

### Task 2: Fill the quickstart and connector setup docs with the real happy path

**Files:**
- Modify: `tests/unit/test_documentation_contract.py`
- Modify: `docs/self-hosting/quickstart.md`
- Modify: `docs/connectors/index.md`
- Reference: `src/pulse/app/cli.py`
- Reference: `pulse.toml`

**Step 1: Write the failing test**

Extend `tests/unit/test_documentation_contract.py` with content assertions for the operator flow:

```python
def test_quickstart_covers_real_cli_happy_path() -> None:
    quickstart = _read("docs/self-hosting/quickstart.md")
    for snippet in [
        "pulse configure",
        "pulse auth google",
        "pulse auth spotify",
        "pulse init",
        "pulse run",
        "pulse status",
        "pulse insights",
    ]:
        assert snippet in quickstart


def test_connector_guide_covers_current_integrations() -> None:
    connectors = _read("docs/connectors/index.md")
    assert "Google" in connectors
    assert "Spotify" in connectors
    assert "browser history" in connectors
    assert "pulse auth google" in connectors
    assert "pulse auth spotify" in connectors
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: FAIL because the placeholder docs do not contain the required operator workflow.

**Step 3: Write minimal implementation**

Populate `docs/self-hosting/quickstart.md` with a concrete operator flow based on `src/pulse/app/cli.py`:

```md
# Self-Hosted Quickstart

## 1. Install Pulse

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## 2. Configure Pulse

```bash
cp .env.example .env
pulse configure
```

## 3. Authorize connectors

```bash
pulse auth google
pulse auth spotify
```

## 4. Initialize your vault and first sync

```bash
pulse init
```

## 5. Run Pulse

```bash
pulse run
```

## 6. Verify it is working

```bash
pulse status
pulse insights
```
```

Populate `docs/connectors/index.md` with short sections for Google, Spotify, and browser history:

```md
# Connector Setup

## Google

Use this for Gmail, Calendar, and YouTube.

```bash
pulse auth google
```

## Spotify

```bash
pulse auth spotify
```

## Browser history

Set `browser = "chrome"` or `browser = "firefox"` in `pulse.toml`.
```

Keep the copy task-oriented. Mention prerequisites, what each connector pulls, and one caveat per connector.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_documentation_contract.py docs/self-hosting/quickstart.md docs/connectors/index.md
git commit -m "docs: add self-hosting quickstart and connector setup"
```

### Task 3: Document configuration and operations, and sync surfaced config examples

**Files:**
- Modify: `tests/unit/test_documentation_contract.py`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/operations/runbook.md`
- Modify: `.env.example`
- Modify: `README.md`
- Reference: `src/pulse/app/config.py`
- Reference: `src/pulse/app/config_loader.py`
- Reference: `src/pulse/jobs/scheduler.py`
- Reference: `src/pulse/app/main.py`

**Step 1: Write the failing test**

Extend `tests/unit/test_documentation_contract.py` again:

```python
def test_configuration_reference_matches_current_runtime_surface() -> None:
    config_doc = _read("docs/reference/configuration.md")
    for snippet in [
        "PULSE_DATABASE_PATH",
        "PULSE_VAULT_PATH",
        "PULSE_GOOGLE_CLIENT_ID",
        "PULSE_SPOTIFY_CLIENT_ID",
        "PULSE_SPOTIFY_CLIENT_SECRET",
        "PULSE_ANTHROPIC_API_KEY",
        "pulse.toml",
        "google_tokens.json",
        "spotify_tokens.json",
    ]:
        assert snippet in config_doc


def test_runbook_covers_operator_checks_and_recovery() -> None:
    runbook = _read("docs/operations/runbook.md")
    for snippet in [
        "/health",
        "/webhooks/telegram",
        "pulse status",
        "pulse logs",
        "pulse reset",
        "pulse cleanup",
        "daily_digest",
        "morning_briefing",
        "discovery_daily",
    ]:
        assert snippet in runbook


def test_env_example_includes_spotify_credentials() -> None:
    env_example = _read(".env.example")
    assert "PULSE_SPOTIFY_CLIENT_ID=" in env_example
    assert "PULSE_SPOTIFY_CLIENT_SECRET=" in env_example
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: FAIL because the config docs are still placeholders and `.env.example` is missing Spotify credentials.

**Step 3: Write minimal implementation**

- Expand `docs/reference/configuration.md` into a real reference grounded in `PulseConfig` and `load_config()`.
- Expand `docs/operations/runbook.md` to cover health checks, scheduled jobs, webhook behavior, status/log inspection, and recovery commands.
- Add Spotify credential lines to `.env.example`.
- Update the `README.md` setup table so it no longer drifts from the implemented environment surface.

Use these exact `.env.example` additions:

```env
PULSE_SPOTIFY_CLIENT_ID=
PULSE_SPOTIFY_CLIENT_SECRET=
```

Make sure the runbook explicitly names these scheduler jobs from `src/pulse/jobs/scheduler.py`:

```text
daily_digest
morning_briefing
aggregation
discovery_daily
discovery_weekly
discovery_monthly
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_documentation_contract.py docs/reference/configuration.md docs/operations/runbook.md .env.example README.md
git commit -m "docs: document runtime configuration and operations"
```

### Task 4: Add the static `/docs/` site page and extend smoke coverage first

**Files:**
- Modify: `site/tests/static-site-smoke.sh`
- Modify: `site/Dockerfile`
- Create: `site/docs/index.html`
- Reference: `site/index.html`
- Reference: `site/nginx.conf`

**Step 1: Write the failing test**

Extend `site/tests/static-site-smoke.sh` so it verifies `/docs/` in addition to `/`.

Add this block after the existing homepage assertions:

```bash
docs_html="$(curl -fsS "http://127.0.0.1:$port/docs/")"
grep -q '<title>Pulse Docs</title>' <<<"$docs_html"
grep -q 'Self-Hosting Docs' <<<"$docs_html"
grep -q 'Run Pulse' <<<"$docs_html"
grep -q 'Configure Pulse' <<<"$docs_html"
grep -q 'Operate Pulse' <<<"$docs_html"
grep -q 'Connect Data Sources' <<<"$docs_html"
grep -q 'github.com/JEFF7712/pulse/blob/main/docs/self-hosting/quickstart.md' <<<"$docs_html"
```

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`

Expected: FAIL because `/docs/` returns 404 and the Docker image does not copy a docs directory yet.

**Step 3: Write minimal implementation**

- Add `site/docs/index.html` with a docs-portal layout that reuses the visual language from `site/index.html`.
- Update `site/Dockerfile` so the built image includes the docs directory.

Use this exact Dockerfile addition:

```dockerfile
COPY docs /usr/share/nginx/html/docs
```

Use these repo-doc URLs in `site/docs/index.html`:

```text
https://github.com/JEFF7712/pulse/blob/main/docs/self-hosting/quickstart.md
https://github.com/JEFF7712/pulse/blob/main/docs/reference/configuration.md
https://github.com/JEFF7712/pulse/blob/main/docs/operations/runbook.md
https://github.com/JEFF7712/pulse/blob/main/docs/connectors/index.md
```

The page should include:

```html
<title>Pulse Docs</title>
<h1>Self-Hosting Docs</h1>
<a href="https://github.com/JEFF7712/pulse/blob/main/docs/self-hosting/quickstart.md">Run Pulse</a>
<a href="https://github.com/JEFF7712/pulse/blob/main/docs/reference/configuration.md">Configure Pulse</a>
<a href="https://github.com/JEFF7712/pulse/blob/main/docs/operations/runbook.md">Operate Pulse</a>
<a href="https://github.com/JEFF7712/pulse/blob/main/docs/connectors/index.md">Connect Data Sources</a>
```

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS.

**Step 5: Commit**

```bash
git add site/tests/static-site-smoke.sh site/Dockerfile site/docs/index.html
git commit -m "feat: add docs landing page to static site"
```

### Task 5: Run final verification across docs and site

**Files:**
- Modify: none unless verification reveals a defect
- Test: `tests/unit/test_documentation_contract.py`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Run repo doc contract tests**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: PASS.

**Step 2: Run site smoke test**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS.

**Step 3: Spot-check the rendered docs paths**

Run:

```bash
python - <<'PY'
from pathlib import Path

for path in [
    Path("docs/self-hosting/quickstart.md"),
    Path("docs/reference/configuration.md"),
    Path("docs/operations/runbook.md"),
    Path("docs/connectors/index.md"),
    Path("site/docs/index.html"),
]:
    print(path, "OK" if path.exists() else "MISSING")
PY
```

Expected: every path prints `OK`.

**Step 4: Commit**

```bash
git add README.md .env.example docs/self-hosting/quickstart.md docs/reference/configuration.md docs/operations/runbook.md docs/connectors/index.md tests/unit/test_documentation_contract.py site/Dockerfile site/docs/index.html site/tests/static-site-smoke.sh
git commit -m "docs: complete self-hosting documentation and docs portal"
```

# Server Home UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a small, operator-focused HTML homepage at `/` for the FastAPI server, styled to match the aesthetic direction in `site/index.html`.

**Architecture:** Keep the feature server-rendered and dependency-light. Add a new homepage renderer module that returns a complete HTML document, then wire a `GET /` route in the FastAPI app that serves it with `HTMLResponse`. Use one focused integration test to drive the route and a second pass to refine the content and layout details.

**Tech Stack:** Python 3.12+, FastAPI, pytest, inline HTML/CSS

---

### Task 1: Root Route Smoke Test

**Files:**
- Create: `tests/integration/test_root_ui.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from pulse.app.main import create_app


def test_root_route_returns_html_homepage() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pulse" in response.text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: FAIL with `404 Not Found` for `/`

**Step 3: Write minimal implementation**

Create a minimal HTML response in `src/pulse/app/main.py`:

```python
from fastapi.responses import HTMLResponse


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return "<html><body><h1>Pulse</h1></body></html>"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_root_ui.py src/pulse/app/main.py
git commit -m "feat: add server homepage route"
```

### Task 2: Homepage Renderer With Site-Inspired Styling

**Files:**
- Create: `src/pulse/app/homepage.py`
- Modify: `src/pulse/app/main.py`
- Modify: `tests/integration/test_root_ui.py`

**Step 1: Write the failing test**

Expand `tests/integration/test_root_ui.py` so it checks for the operator-facing content:

```python
def test_root_route_includes_operator_content() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "server online" in response.text.lower()
    assert "/health" in response.text
    assert "self-hosted" in response.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: FAIL because the minimal HTML from Task 1 does not include the new strings

**Step 3: Write minimal implementation**

Move the markup into `src/pulse/app/homepage.py` and return a full document:

```python
def render_homepage() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Pulse</title>
    <style>
      :root {
        --black: #050505;
        --white: #e8e4df;
        --cream: #c4bfb8;
        --accent: #4ade80;
        --dim: #3a3632;
      }
    </style>
  </head>
  <body>
    <main>
      <p>server online</p>
      <h1>Pulse</h1>
      <p>Self-hosted personal intelligence for your own infrastructure.</p>
      <a href="/health">Health</a>
      <p>`/webhooks/telegram` accepts Telegram reply webhooks.</p>
    </main>
  </body>
</html>"""
```

Wire `src/pulse/app/main.py` to call `render_homepage()` from the new module and serve it with `HTMLResponse`.

Then flesh out the CSS and structure so the page includes:

- a compact pulse-ring hero,
- serif + mono typography that echoes `site/index.html`,
- an operator overview section,
- endpoint cards or links for `/health` and `/webhooks/telegram`,
- responsive stacking for mobile widths.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/homepage.py src/pulse/app/main.py tests/integration/test_root_ui.py
git commit -m "feat: add styled operator homepage"
```

### Task 3: Guard Existing Behavior

**Files:**
- Modify: `tests/integration/test_health_api.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

Add a second assertion to confirm the new homepage work did not disturb the API behavior:

```python
def test_health_endpoint_still_returns_ok_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

If that test already exists unchanged, treat this task as verifying no regressions rather than adding new coverage.

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py -v`
Expected: PASS for `/health`; if it fails, the homepage route or imports introduced a regression that must be fixed

**Step 3: Write minimal implementation**

Only make the smallest change required if the verification step reveals a regression. Otherwise, make no code changes in this step.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/main.py tests/integration/test_health_api.py tests/integration/test_root_ui.py
git commit -m "test: verify homepage does not break api health route"
```

### Task 4: Full Verification

**Files:**
- Modify: `src/pulse/app/homepage.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

No new test file is required. This task verifies the completed slice and captures any last small fix discovered by the wider suite.

**Step 2: Run verification to expose remaining issues**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/unit/test_imports.py -v`
Expected: all selected tests pass; if not, capture the failing case and fix only that issue

**Step 3: Write minimal implementation**

Make only the smallest fix required by the verification command. Keep the homepage static and avoid introducing new infrastructure, template engines, or asset handling.

**Step 4: Run verification to confirm success**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/unit/test_imports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/homepage.py src/pulse/app/main.py tests/integration/test_root_ui.py tests/integration/test_health_api.py
git commit -m "test: verify server homepage slice"
```

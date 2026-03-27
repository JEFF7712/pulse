# Home Operator Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `/` into a compact operator console with runtime data, safe quick actions, and modest UI polish while keeping the page server-rendered and non-destructive.

**Architecture:** Extend the existing homepage renderer to accept structured runtime status data and optional action-result messages. Add a small status builder layer plus dedicated safe POST action endpoints in the FastAPI app that reuse existing Pulse operations or thin wrappers around them, then redirect back to `/` with a result message.

**Tech Stack:** Python 3.12+, FastAPI, pytest, inline HTML/CSS, existing Pulse services/config

---

### Task 1: Expand Homepage Status Contract

**Files:**
- Modify: `tests/integration/test_root_ui.py`
- Modify: `src/pulse/app/homepage.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

Expand `tests/integration/test_root_ui.py` to assert the operator-console status surface:

```python
def test_root_route_shows_operator_console_sections() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "database" in response.text.lower()
    assert "vault" in response.text.lower()
    assert "scheduler" in response.text.lower()
    assert "connectors" in response.text.lower()
    assert "run pull" in response.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: FAIL because the current homepage does not yet render runtime data sections or action labels

**Step 3: Write minimal implementation**

Introduce a status payload for the homepage and render it in `src/pulse/app/homepage.py`.

Add or adapt helper functions in `src/pulse/app/main.py` to build status data such as:

```python
status = {
    "database_path": str(settings.database_path),
    "vault_path": str(settings.vault_path),
    "timezone": settings.timezone,
    "scheduler_running": True,
    "scheduler_job_count": len(scheduler.get_jobs()),
    "pull_connectors": len(registry.get_pull_connectors()),
    "push_connectors": len(registry.get_push_connectors()),
}
```

Render a compact operational data section and a visible action section label while preserving the current minimal content and pulse motif.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_root_ui.py src/pulse/app/homepage.py src/pulse/app/main.py
git commit -m "feat: add operator console status surface"
```

### Task 2: Add Safe Action Endpoints

**Files:**
- Modify: `tests/integration/test_root_ui.py`
- Create: `tests/integration/test_home_actions.py`
- Modify: `src/pulse/app/main.py`
- Create: `src/pulse/app/home_actions.py`

**Step 1: Write the failing test**

Add a focused action-route test:

```python
def test_pull_action_redirects_back_to_home() -> None:
    client = TestClient(create_app())

    response = client.post("/actions/pull", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert response.headers["location"] == "/"
```

Add a homepage assertion that the button or form labels exist:

```python
assert "run pull" in response.text.lower()
assert "run digest" in response.text.lower()
assert "run discovery" in response.text.lower()
assert "test telegram" in response.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_home_actions.py -v`
Expected: FAIL because the action endpoints do not exist yet

**Step 3: Write minimal implementation**

Create `src/pulse/app/home_actions.py` with thin safe action handlers or wrappers. Add POST routes in `src/pulse/app/main.py` for:

- `/actions/pull`
- `/actions/digest`
- `/actions/discover`
- `/actions/test-telegram`

Each route should:

1. execute the safe action or determine it is skipped,
2. produce a compact message,
3. redirect back to `/` with a query parameter such as `?notice=pull-started` or `?error=telegram-not-configured`.

Render the action buttons/forms in `src/pulse/app/homepage.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_home_actions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_root_ui.py tests/integration/test_home_actions.py src/pulse/app/main.py src/pulse/app/homepage.py src/pulse/app/home_actions.py
git commit -m "feat: add safe homepage actions"
```

### Task 3: Action Result Messaging

**Files:**
- Modify: `tests/integration/test_home_actions.py`
- Modify: `src/pulse/app/homepage.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

Add a test that follows an action redirect and checks for a user-visible outcome:

```python
def test_homepage_shows_action_notice_after_redirect() -> None:
    client = TestClient(create_app())

    response = client.get("/?notice=pull-started")

    assert "pull-started" in response.text.lower() or "pull started" in response.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_home_actions.py -v`
Expected: FAIL because the homepage does not yet render action-result notices

**Step 3: Write minimal implementation**

Read action-result query parameters in `src/pulse/app/main.py` and pass a notice payload into `render_homepage()`. Render a compact status banner in `src/pulse/app/homepage.py`, for example:

```html
<div class="notice notice-success">pull started</div>
```

Map internal tokens to short operator-facing messages.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_home_actions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_home_actions.py src/pulse/app/main.py src/pulse/app/homepage.py
git commit -m "feat: show homepage action notices"
```

### Task 4: Runtime Regression Verification

**Files:**
- Modify: `src/pulse/app/homepage.py`
- Modify: `src/pulse/app/main.py`

**Step 1: Write the failing test**

No new test file is required. Treat this as regression verification.

**Step 2: Run verification to expose issues**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_home_actions.py tests/integration/test_health_api.py tests/integration/test_telegram_webhook.py tests/unit/test_imports.py -v`
Expected: all selected tests pass; if not, capture the smallest failing behavior

**Step 3: Write minimal implementation**

Make only the smallest fix required by the verification command. Do not add destructive actions, JS application state, or extra dashboard complexity.

**Step 4: Run verification to confirm success**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_home_actions.py tests/integration/test_health_api.py tests/integration/test_telegram_webhook.py tests/unit/test_imports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/homepage.py src/pulse/app/main.py src/pulse/app/home_actions.py tests/integration/test_root_ui.py tests/integration/test_home_actions.py
git commit -m "test: verify homepage operator console"
```

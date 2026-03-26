# Server Home UI Refinement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the `/` server homepage into a compact functional surface and add subtle pulse animation inspired by `site/index.html`.

**Architecture:** Keep the existing FastAPI route and homepage renderer split intact. Make the change entirely inside `src/pulse/app/homepage.py` and the existing root-route integration test so the refinement stays server-rendered, dependency-light, and easy to verify.

**Tech Stack:** Python 3.12+, FastAPI, pytest, inline HTML/CSS

---

### Task 1: Tighten Homepage Contract

**Files:**
- Modify: `tests/integration/test_root_ui.py`
- Modify: `src/pulse/app/homepage.py`

**Step 1: Write the failing test**

Update `tests/integration/test_root_ui.py` so it asserts the reduced functional surface instead of the older prose-heavy layout:

```python
def test_root_route_stays_functional_and_minimal() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "Pulse" in response.text
    assert "server online" in response.text.lower()
    assert "self-hosted node" in response.text.lower()
    assert "/health" in response.text
    assert "POST /webhooks/telegram" in response.text
    assert "operator overview" not in response.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: FAIL because the current homepage still includes the larger overview section and old copy

**Step 3: Write minimal implementation**

Reduce `src/pulse/app/homepage.py` to a single compact layout block that keeps only:

```html
<h1>Pulse</h1>
<div>server online</div>
<div>self-hosted node</div>
<a href="/health">/health</a>
<div>POST /webhooks/telegram</div>
```

Retain the dark palette and overall centered framing, but remove the overview section, stats, and descriptive paragraphs.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_root_ui.py src/pulse/app/homepage.py
git commit -m "feat: simplify server homepage content"
```

### Task 2: Add Subtle Pulse Animation

**Files:**
- Modify: `tests/integration/test_root_ui.py`
- Modify: `src/pulse/app/homepage.py`

**Step 1: Write the failing test**

Add one lightweight HTML-level assertion that the animated pulse structure still exists:

```python
def test_root_route_keeps_pulse_markup() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "pulse-ring" in response.text
    assert "pulse-dot" in response.text
```

If those strings already exist unchanged, strengthen the test by asserting a stable animation token such as `pulseExpand` in the response HTML.

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: FAIL because the current homepage has pulse markup but no actual animation token such as `pulseExpand`

**Step 3: Write minimal implementation**

Add the smallest CSS needed in `src/pulse/app/homepage.py` to animate the existing pulse structure:

```css
@keyframes pulseExpand {
  0% {
    transform: scale(0.3);
    opacity: 0.45;
  }
  100% {
    transform: scale(1.85);
    opacity: 0;
  }
}

@keyframes dotPulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.45;
  }
  20% {
    transform: scale(1.65);
    opacity: 1;
  }
}
```

Apply the animation to multiple ring layers and the center dot, keeping the motion slow and ambient.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_root_ui.py src/pulse/app/homepage.py
git commit -m "feat: animate server homepage pulse motif"
```

### Task 3: Verify API Surface Still Behaves

**Files:**
- Modify: `src/pulse/app/homepage.py`

**Step 1: Write the failing test**

No new test is required if the existing checks already cover this. Treat this as regression verification.

**Step 2: Run test to verify behavior**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/integration/test_telegram_webhook.py -v`
Expected: PASS; `/health` remains healthy and the Telegram webhook integration still behaves correctly

**Step 3: Write minimal implementation**

Only make a change if the verification reveals a regression. Otherwise make no code changes.

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/integration/test_telegram_webhook.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/homepage.py tests/integration/test_root_ui.py
git commit -m "test: verify minimal server homepage behavior"
```

### Task 4: Full Verification

**Files:**
- Modify: `src/pulse/app/homepage.py`

**Step 1: Write the failing test**

No new test file is required. This task validates the final refinement slice.

**Step 2: Run verification to expose remaining issues**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/unit/test_imports.py -v`
Expected: all selected tests pass; if not, fix only the failing behavior

**Step 3: Write minimal implementation**

Make only the smallest fix required by the verification command. Do not reintroduce explanatory copy or extra page sections.

**Step 4: Run verification to confirm success**

Run: `pytest tests/integration/test_root_ui.py tests/integration/test_health_api.py tests/unit/test_imports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/pulse/app/homepage.py tests/integration/test_root_ui.py src/pulse/app/main.py
git commit -m "test: verify refined server homepage slice"
```

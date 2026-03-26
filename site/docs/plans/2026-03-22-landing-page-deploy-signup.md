# Landing Page Deploy and Signup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore containerized deployment for the current landing page and replace the demo signup interaction with a real hosted form submission flow.

**Architecture:** Keep the landing page as a static `index.html` file with inline styles. Align deployment and smoke tests with the actual file structure, then upgrade the signup section from a console-log demo to a semantic form that posts to a hosted endpoint and renders inline success or error feedback.

**Tech Stack:** Static HTML/CSS/JavaScript, nginx in Docker, shell smoke test with Docker and curl

---

### Task 1: Fix Docker image for the current static site

**Files:**
- Modify: `Dockerfile`
- Test: `tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Use the existing smoke test as the failing reproduction.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because `styles.css` is referenced by the test and `Dockerfile`, but the file does not exist.

**Step 3: Write minimal implementation**

Edit `Dockerfile` to remove the stale `COPY styles.css /usr/share/nginx/html/styles.css` line.

**Step 4: Run the focused verification**

Run: `docker build -t pulse-site-check .`
Expected: PASS with a successful image build.

**Step 5: Commit**

```bash
git add Dockerfile
git commit -m "fix: align site image with inline styles"
```

### Task 2: Update smoke coverage to match the actual landing page

**Files:**
- Modify: `tests/static-site-smoke.sh`
- Test: `tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Keep the same smoke script, but change its assertions so they target the current page behavior instead of the missing stylesheet file.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL before the script is updated because it still checks for `styles.css` references.

**Step 3: Write minimal implementation**

Update `tests/static-site-smoke.sh` to:

- Assert `index.html` exists.
- Assert `Dockerfile` still uses `nginx:alpine`, exposes `8080`, and runs as `101:101`.
- Build and run the container.
- Assert the served HTML contains `<title>Pulse</title>`.
- Assert the served HTML contains stable landing-page text such as `Personal Intelligence Agent` and `Notify Me`.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS with exit code `0`.

**Step 5: Commit**

```bash
git add tests/static-site-smoke.sh
git commit -m "test: update smoke checks for static landing page"
```

### Task 3: Convert the signup area into a real hosted form integration

**Files:**
- Modify: `index.html`
- Test: `tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Add a smoke assertion for the real form markup you plan to ship, such as a `<form` element with a configured action URL placeholder or production endpoint.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because the page currently uses a `<div class="signup-form">` and button-driven demo script instead of a real form submission.

**Step 3: Write minimal implementation**

In `index.html`:

- Replace the signup container with a real `<form class="signup-form" id="signupForm" method="POST" action="HOSTED_FORM_ENDPOINT">`.
- Add `name="email"` to the email input.
- Keep native email validation with `type="email"` and `required`.
- Replace `handleSignup()` with submit handling that:
  - intercepts submission with `preventDefault()` when JavaScript is available,
  - posts the form using `fetch(form.action, { method: 'POST', body: new FormData(form) })`,
  - hides the form and shows success text on success,
  - shows an inline error message on failure.
- Keep graceful degradation: if JavaScript fails, the browser can still submit the form normally.

**Step 4: Run verification**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS once the page contains the real form markup and the container still serves the updated HTML.

Then manually verify by serving locally:

Run: `python3 -m http.server 4173`
Expected: Page loads locally so the form behavior can be tested in a browser.

**Step 5: Commit**

```bash
git add index.html tests/static-site-smoke.sh
git commit -m "feat: connect landing page signup to hosted form"
```

### Task 4: Final verification

**Files:**
- Verify only: `Dockerfile`, `tests/static-site-smoke.sh`, `index.html`

**Step 1: Run deploy verification**

Run: `docker build -t pulse-site-check .`
Expected: PASS.

**Step 2: Run smoke verification**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS.

**Step 3: Review working tree**

Run: `git diff -- Dockerfile tests/static-site-smoke.sh index.html`
Expected: Only the intended deploy, test, and signup changes appear.

**Step 4: Commit**

```bash
git add Dockerfile tests/static-site-smoke.sh index.html
git commit -m "fix: restore landing page deploy and signup flow"
```

## Open Input Needed Before Task 3

Pick the hosted form endpoint to use in `index.html`. Until that value is chosen, use a clear placeholder like `https://example-form-service.invalid/pulse-signup` during development and replace it before shipping.

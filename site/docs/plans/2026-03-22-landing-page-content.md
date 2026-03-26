# Landing Page Content Rewrite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the Pulse landing page copy so the page explains the product clearly, keeps trust as a supporting theme, and improves the signup pitch without changing the overall visual direction.

**Architecture:** Keep the current page structure in `site/index.html`, but revise the text content section by section. The rewrite should preserve the existing design language while improving message order, reducing repetition, and making the product promise more concrete.

**Tech Stack:** Static HTML/CSS/JavaScript, shell smoke test, Node runtime behavior test

---

### Task 1: Rewrite the hero and top-level positioning

**Files:**
- Modify: `site/index.html`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Update `site/tests/static-site-smoke.sh` to assert the new hero message once it is decided. Prefer checking a stable hero phrase that directly defines Pulse.

Example target assertion shape:

```bash
grep -q 'self-hosted personal intelligence agent' <<<"$html"
```

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because the current hero still uses the old copy.

**Step 3: Write minimal implementation**

In `site/index.html`, rewrite:

- the hero label if needed,
- the hero headline or tagline,
- the status/supporting line if needed,

so the first screen clearly says what Pulse is and what outcome it creates.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS.

**Step 5: Commit**

```bash
git add site/index.html site/tests/static-site-smoke.sh
git commit -m "refine landing page hero positioning"
```

### Task 2: Rewrite the product explanation section

**Files:**
- Modify: `site/index.html`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Add or update smoke assertions for the new `about` section copy so it reflects product behavior instead of repeating the collection/surveillance setup.

Use checks for phrases that describe what Pulse does, such as connecting data sources, surfacing patterns, and writing to an Obsidian vault.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because the old `about` copy is still present.

**Step 3: Write minimal implementation**

Rewrite the `about` section in `site/index.html` so it:

- explains what Pulse does in plain English,
- includes 2-3 concrete examples of useful observations,
- keeps the Obsidian/readable-memory idea as a concrete trust detail.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS.

**Step 5: Commit**

```bash
git add site/index.html site/tests/static-site-smoke.sh
git commit -m "clarify landing page product explanation"
```

### Task 3: Tighten connectors and trust messaging

**Files:**
- Modify: `site/index.html`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Adjust smoke assertions so they expect the updated connector intro and trust-focused philosophy language.

Prefer checking a short connector explanation and 2-3 concise trust claims.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because the current copy still uses the broader manifesto phrasing.

**Step 3: Write minimal implementation**

In `site/index.html`:

- add or rewrite one short line in the connectors section explaining why the sources matter together,
- shorten the philosophy section,
- keep the trust message focused on self-hosting, readable notes, and user control.

Do not redesign the layout unless the copy genuinely needs a small heading adjustment.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS.

**Step 5: Commit**

```bash
git add site/index.html site/tests/static-site-smoke.sh
git commit -m "tighten landing page trust and connector copy"
```

### Task 4: Improve the signup CTA copy

**Files:**
- Modify: `site/index.html`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Update the smoke test to assert the revised signup heading/subheading once chosen.

Prefer checking for early-access language rather than generic launch-notification wording.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`
Expected: FAIL because the old signup CTA copy is still present.

**Step 3: Write minimal implementation**

Rewrite the signup heading and supporting copy in `site/index.html` so it invites the right early users to join, rather than just asking for launch notifications.

Keep the current Formspree integration and button behavior unchanged unless a wording change requires tiny markup updates.

**Step 4: Run verification**

Run: `bash tests/static-site-smoke.sh && node tests/signup-runtime-behavior.js`
Expected: PASS.

**Step 5: Commit**

```bash
git add site/index.html site/tests/static-site-smoke.sh
git commit -m "improve landing page signup messaging"
```

### Task 5: Final review and verification

**Files:**
- Verify only: `site/index.html`, `site/tests/static-site-smoke.sh`, `site/tests/signup-runtime-behavior.js`

**Step 1: Run content verification**

Run: `bash tests/static-site-smoke.sh`
Expected: PASS.

**Step 2: Run signup behavior verification**

Run: `node tests/signup-runtime-behavior.js`
Expected: PASS.

**Step 3: Review the final diff**

Run: `git diff -- site/index.html site/tests/static-site-smoke.sh`
Expected: Copy changes are clearer, more specific, and still aligned with the existing design.

**Step 4: Commit**

```bash
git add site/index.html site/tests/static-site-smoke.sh
git commit -m "refine landing page content for product clarity"
```

## Execution Notes

- Preserve the current visual language unless copy changes reveal a real usability issue.
- Prefer stable smoke-test assertions on durable product phrases, not fragile exact block formatting.
- Avoid changing the signup JavaScript unless a content edit accidentally affects behavior.

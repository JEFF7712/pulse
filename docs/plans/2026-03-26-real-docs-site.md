# Real Docs Site Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the temporary `/docs` portal with a real docs site generated from repo markdown and served under `/docs/` alongside the existing marketing homepage.

**Architecture:** Add a dedicated VitePress docs app under `site/docs-app/` and treat repo `docs/` markdown as the canonical content source. Build the docs app into static files, copy that output into the nginx-served site image under `/usr/share/nginx/html/docs/`, and extend smoke tests so they verify real docs routes instead of a single landing page.

**Tech Stack:** VitePress, Markdown, npm, static HTML/CSS, nginx, existing shell smoke tests

---

### Task 1: Scaffold the docs app and prove `/docs/` can build locally

**Files:**
- Create: `site/docs-app/package.json`
- Create: `site/docs-app/package-lock.json`
- Create: `site/docs-app/.gitignore`
- Create: `site/docs-app/docs/.vitepress/config.mts`
- Create: `site/docs-app/docs/index.md`
- Create: `site/docs-app/docs/.vitepress/theme/custom.css`
- Modify: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Extend `site/tests/static-site-smoke.sh` so it expects a generated docs site instead of a single handwritten docs portal page.

Add checks for:

```bash
[[ -f docs-app/package.json ]]
[[ -f docs-app/docs/.vitepress/config.mts ]]
[[ -f docs-app/docs/index.md ]]
```

Also change the `/docs/` assertions to expect docs-site markers such as:

```bash
grep -q 'Get Started' <<<"$docs_html"
grep -q 'Run Pulse' <<<"$docs_html"
grep -q 'Configure Pulse' <<<"$docs_html"
grep -q 'Operate Pulse' <<<"$docs_html"
grep -q 'Connect Data Sources' <<<"$docs_html"
```

and to reject the temporary GitHub-link portal wording:

```bash
! grep -q 'Browse docs in GitHub' <<<"$docs_html"
```

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`

Expected: FAIL because `site/docs-app/` does not exist and `/docs/` still serves the temporary portal page.

**Step 3: Write minimal implementation**

Create the VitePress app skeleton under `site/docs-app/`.

Use this `package.json` shape:

```json
{
  "name": "pulse-docs-app",
  "private": true,
  "scripts": {
    "dev": "vitepress dev docs",
    "build": "vitepress build docs",
    "preview": "vitepress preview docs"
  },
  "devDependencies": {
    "vitepress": "^1.6.0"
  }
}
```

Use this `config.mts` base shape:

```ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  srcDir: '.',
  base: '/docs/',
  title: 'Pulse Docs',
  description: 'Self-hosted Pulse documentation',
})
```

Use a minimal `docs/index.md` homepage with card links for the four core operator paths.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS for the new file-presence assertions only if the remaining implementation already satisfies them; otherwise keep iterating inside this task until the smoke test reaches green.

**Step 5: Commit**

```bash
git add site/docs-app site/tests/static-site-smoke.sh
git commit -m "feat: scaffold generated docs site"
```

### Task 2: Move repo markdown into the docs app and add docs-native navigation

**Files:**
- Create: `docs/index.md`
- Create: `site/docs-app/docs/self-hosting/quickstart.md`
- Create: `site/docs-app/docs/reference/configuration.md`
- Create: `site/docs-app/docs/operations/runbook.md`
- Create: `site/docs-app/docs/connectors/index.md`
- Modify: `site/docs-app/docs/.vitepress/config.mts`
- Modify: `site/tests/static-site-smoke.sh`

**Step 1: Write the failing test**

Extend `site/tests/static-site-smoke.sh` so it checks real docs child routes instead of only `/docs/`.

Add route checks for:

```bash
quickstart_html="$(curl -fsS "http://127.0.0.1:$port/docs/self-hosting/quickstart")"
config_html="$(curl -fsS "http://127.0.0.1:$port/docs/reference/configuration")"
runbook_html="$(curl -fsS "http://127.0.0.1:$port/docs/operations/runbook")"
connectors_html="$(curl -fsS "http://127.0.0.1:$port/docs/connectors/")"
grep -q 'Self-Hosting Quickstart' <<<"$quickstart_html"
grep -q 'Configuration Reference' <<<"$config_html"
grep -q 'Operations Runbook' <<<"$runbook_html"
grep -q 'Connector Setup' <<<"$connectors_html"
```

Also add a docs-nav assertion on the homepage for sidebar labels or nav text:

```bash
grep -q 'Self-Hosting' <<<"$docs_html"
grep -q 'Configuration' <<<"$docs_html"
grep -q 'Operations' <<<"$docs_html"
grep -q 'Connectors' <<<"$docs_html"
```

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`

Expected: FAIL because the child docs routes and navigation do not exist yet.

**Step 3: Write minimal implementation**

- Add `docs/index.md` as the canonical docs homepage content.
- Mirror the operator docs into the VitePress content tree by moving or syncing the markdown pages into `site/docs-app/docs/...`.
- Configure VitePress navigation and sidebar in `site/docs-app/docs/.vitepress/config.mts`.

Use this `themeConfig` shape:

```ts
themeConfig: {
  nav: [{ text: 'Docs Home', link: '/' }],
  sidebar: [
    {
      text: 'Getting Started',
      items: [
        { text: 'Home', link: '/' },
        { text: 'Self-Hosting Quickstart', link: '/self-hosting/quickstart' },
      ],
    },
    {
      text: 'Operations',
      items: [
        { text: 'Configuration Reference', link: '/reference/configuration' },
        { text: 'Operations Runbook', link: '/operations/runbook' },
        { text: 'Connector Setup', link: '/connectors/' },
      ],
    },
  ],
}
```

For this first implementation, prefer copying the markdown content into the docs app rather than inventing a fragile live-sync system. Add a clear note at the top of the copied files if needed so later work can centralize sourcing.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS with `/docs/` and the four child routes all returning expected content.

**Step 5: Commit**

```bash
git add docs/index.md site/docs-app/docs site/tests/static-site-smoke.sh
git commit -m "feat: add structured docs routes and navigation"
```

### Task 3: Make the docs homepage feel like a real product manual

**Files:**
- Modify: `site/docs-app/docs/index.md`
- Modify: `site/docs-app/docs/.vitepress/config.mts`
- Modify: `site/docs-app/docs/.vitepress/theme/custom.css`
- Modify: `site/tests/static-site-smoke.sh`
- Reference: `site/index.html`

**Step 1: Write the failing test**

Extend `site/tests/static-site-smoke.sh` to assert docs-home product-manual content.

Add checks like:

```bash
grep -q 'What is Pulse?' <<<"$docs_html"
grep -q 'Quick Start' <<<"$docs_html"
grep -q 'Run Pulse' <<<"$docs_html"
grep -q 'Configure Pulse' <<<"$docs_html"
grep -q 'Operate Pulse' <<<"$docs_html"
grep -q 'Connect Data Sources' <<<"$docs_html"
```

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`

Expected: FAIL because the docs homepage is still bare scaffolding.

**Step 3: Write minimal implementation**

- Expand `site/docs-app/docs/index.md` into a docs-native landing page with:
  - a short Pulse framing section,
  - a quick-start path,
  - four entry cards,
  - links to the main docs groups.
- Customize `site/docs-app/docs/.vitepress/theme/custom.css` so the docs app visually belongs to Pulse.

The custom CSS should include Pulse tokens similar to:

```css
:root {
  --vp-c-bg: #050505;
  --vp-c-bg-soft: #11100f;
  --vp-c-text-1: #e8e4df;
  --vp-c-text-2: #c4bfb8;
  --vp-c-brand-1: #4ade80;
}
```

Also override heading fonts so docs pages echo the main site's serif/mono pairing.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS.

**Step 5: Commit**

```bash
git add site/docs-app/docs/index.md site/docs-app/docs/.vitepress/config.mts site/docs-app/docs/.vitepress/theme/custom.css site/tests/static-site-smoke.sh
git commit -m "feat: style docs home for Pulse"
```

### Task 4: Package the built docs app into the existing site container

**Files:**
- Modify: `site/Dockerfile`
- Modify: `site/tests/static-site-smoke.sh`
- Modify: `site/.dockerignore`
- Create: `site/docs-app/README.md`

**Step 1: Write the failing test**

Tighten `site/tests/static-site-smoke.sh` to verify the Docker build runs the docs build instead of copying handwritten docs files.

Add assertions such as:

```bash
grep -q 'docs-app' Dockerfile
! grep -q '^COPY docs/' Dockerfile
```

Also require docs-app build output to be included indirectly by the Docker build succeeding and `/docs/` returning the generated homepage markers.

**Step 2: Run test to verify it fails**

Run: `bash tests/static-site-smoke.sh`

Expected: FAIL because the Dockerfile still copies the old static docs directory directly.

**Step 3: Write minimal implementation**

Convert `site/Dockerfile` to a multi-stage build.

Use this shape:

```dockerfile
FROM node:22-alpine AS docs-builder
WORKDIR /app/site/docs-app
COPY docs-app/package.json docs-app/package-lock.json ./
RUN npm ci
COPY docs-app/ ./
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY index.html /usr/share/nginx/html/index.html
COPY --from=docs-builder /app/site/docs-app/docs/.vitepress/dist/ /usr/share/nginx/html/docs/
EXPOSE 8080
USER 101:101
```

Add `site/docs-app/README.md` explaining how to run the docs app locally.

**Step 4: Run test to verify it passes**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS with the real Docker packaging path.

**Step 5: Commit**

```bash
git add site/Dockerfile site/.dockerignore site/docs-app/README.md site/tests/static-site-smoke.sh
git commit -m "build: package generated docs site under /docs"
```

### Task 5: Reconcile repo docs ownership and remove the temporary portal

**Files:**
- Modify: `README.md`
- Modify: `tests/unit/test_documentation_contract.py`
- Delete: `site/docs/index.html`
- Modify: `site/tests/static-site-smoke.sh`
- Modify: `docs/self-hosting/quickstart.md`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/operations/runbook.md`
- Modify: `docs/connectors/index.md`
- Modify: `docs/index.md`

**Step 1: Write the failing test**

Extend `tests/unit/test_documentation_contract.py` so it checks the repo docs source-of-truth contract for the new docs-site shape.

Add assertions for:

```python
def test_docs_home_exists() -> None:
    assert (REPO_ROOT / "docs/index.md").exists()


def test_readme_points_to_site_docs_entry() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert "/docs/" in readme
```

Also update `site/tests/static-site-smoke.sh` to fail if the old temporary portal file still exists:

```bash
[[ ! -f docs/index.html ]]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_documentation_contract.py -v && bash tests/static-site-smoke.sh`

Expected: FAIL because the repo docs homepage contract is incomplete and the temporary portal file still exists.

**Step 3: Write minimal implementation**

- Add `docs/index.md` content that matches the docs homepage structure.
- Update `README.md` so the docs entry point points readers at the site docs experience.
- Remove `site/docs/index.html`.
- Make sure the repo docs pages and docs-app copies stay aligned after the move.

If the docs app is still using copied markdown files at this stage, do a final consistency pass so headings and key sections match between `docs/` and `site/docs-app/docs/`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_documentation_contract.py -v && bash tests/static-site-smoke.sh`

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md docs/index.md docs/self-hosting/quickstart.md docs/reference/configuration.md docs/operations/runbook.md docs/connectors/index.md tests/unit/test_documentation_contract.py site/tests/static-site-smoke.sh site/Dockerfile site/.dockerignore site/docs-app
git commit -m "docs: replace portal with generated docs site"
```

### Task 6: Run final verification for the docs product and packaging

**Files:**
- Modify: none unless verification reveals a defect
- Test: `tests/unit/test_documentation_contract.py`
- Test: `site/tests/static-site-smoke.sh`

**Step 1: Run repo docs contract tests**

Run: `pytest tests/unit/test_documentation_contract.py -v`

Expected: PASS.

**Step 2: Run site smoke test**

Run: `bash tests/static-site-smoke.sh`

Expected: PASS.

**Step 3: Build the docs app directly**

Run: `npm ci && npm run build`

Working directory: `site/docs-app`

Expected: PASS and emit static docs output under `site/docs-app/docs/.vitepress/dist/`.

**Step 4: Spot-check routes and sources**

Run:

```bash
python - <<'PY'
from pathlib import Path

for path in [
    Path('docs/index.md'),
    Path('docs/self-hosting/quickstart.md'),
    Path('docs/reference/configuration.md'),
    Path('docs/operations/runbook.md'),
    Path('docs/connectors/index.md'),
    Path('site/docs-app/docs/.vitepress/config.mts'),
    Path('site/docs-app/package.json'),
]:
    print(path, 'OK' if path.exists() else 'MISSING')
PY
```

Expected: every path prints `OK`.

**Step 5: Commit**

```bash
git add README.md docs site/docs-app site/Dockerfile site/.dockerignore site/tests/static-site-smoke.sh tests/unit/test_documentation_contract.py
git commit -m "docs: ship generated docs experience"
```

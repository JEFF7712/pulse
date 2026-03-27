# Site Docker Publish Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a GitHub Actions workflow that validates the Dockerized static site in `site/` and publishes `${DOCKERHUB_USERNAME}/pulse-site` to Docker Hub from `main`.

**Architecture:** Create a single workflow at `.github/workflows/site-docker-publish.yml` with a secret-free `smoke` job and a gated `publish` job. Reuse `site/tests/static-site-smoke.sh` for real container verification, add one focused workflow-check script under `site/tests/`, and validate the workflow syntax locally with Dockerized `actionlint`.

**Tech Stack:** GitHub Actions YAML, Docker Hub, Docker Buildx, `docker/login-action`, `docker/metadata-action`, `docker/build-push-action`, shell tests, Dockerized `actionlint`

---

### Task 1: Add a failing workflow smoke test and scaffold the workflow

**Files:**
- Create: `site/tests/github-actions-site-publish.sh`
- Create: `.github/workflows/site-docker-publish.yml`
- Test: `site/tests/github-actions-site-publish.sh`

**Step 1: Write the failing test**

Create `site/tests/github-actions-site-publish.sh` with focused assertions for the workflow skeleton.

Use this shape:

```bash
#!/usr/bin/env bash

set -euo pipefail

workflow=".github/workflows/site-docker-publish.yml"

[[ -f "$workflow" ]]
grep -q '^name: Site Docker Publish$' "$workflow"
grep -q '^pull_request:$' "$workflow"
grep -q '^  push:$' "$workflow"
grep -q "site/\\*\\*" "$workflow"
grep -q "\.github/workflows/site-docker-publish.yml" "$workflow"
grep -q '^jobs:$' "$workflow"
grep -q '^  smoke:$' "$workflow"
grep -q 'actions/checkout@v4' "$workflow"
grep -q 'docker/setup-buildx-action@v3' "$workflow"
grep -q 'bash tests/static-site-smoke.sh' "$workflow"
```

**Step 2: Run test to verify it fails**

Run: `bash site/tests/github-actions-site-publish.sh`

Expected: FAIL because the workflow file does not exist yet.

**Step 3: Write minimal implementation**

Create `.github/workflows/site-docker-publish.yml` with this initial skeleton:

```yaml
name: Site Docker Publish

on:
  push:
    branches: [main]
    paths:
      - 'site/**'
      - '.github/workflows/site-docker-publish.yml'
  pull_request:
    paths:
      - 'site/**'
      - '.github/workflows/site-docker-publish.yml'

permissions:
  contents: read

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Run site smoke test
        working-directory: site
        run: bash tests/static-site-smoke.sh
```

**Step 4: Run test to verify it passes**

Run: `bash site/tests/github-actions-site-publish.sh`

Expected: PASS with exit code `0`.

**Step 5: Commit**

```bash
git add site/tests/github-actions-site-publish.sh .github/workflows/site-docker-publish.yml
git commit -m "test: scaffold site image workflow checks"
```

### Task 2: Add Docker Hub publish behavior gated on `main`

**Files:**
- Modify: `site/tests/github-actions-site-publish.sh`
- Modify: `.github/workflows/site-docker-publish.yml`
- Test: `site/tests/github-actions-site-publish.sh`

**Step 1: Write the failing test**

Extend `site/tests/github-actions-site-publish.sh` with assertions for publish behavior.

Add checks like:

```bash
grep -q '^  publish:$' "$workflow"
grep -q '^    needs: smoke$' "$workflow"
grep -q 'refs/heads/main' "$workflow"
grep -q 'docker/login-action@v3' "$workflow"
grep -q 'docker/metadata-action@v5' "$workflow"
grep -q 'docker/build-push-action@v6' "$workflow"
grep -q 'DOCKERHUB_USERNAME' "$workflow"
grep -q 'DOCKERHUB_TOKEN' "$workflow"
grep -q 'type=raw,value=latest' "$workflow"
grep -q 'type=sha,prefix=sha-' "$workflow"
grep -q 'context: ./site' "$workflow"
grep -q 'file: ./site/Dockerfile' "$workflow"
grep -q 'push: true' "$workflow"
```

**Step 2: Run test to verify it fails**

Run: `bash site/tests/github-actions-site-publish.sh`

Expected: FAIL because the workflow only contains the smoke job.

**Step 3: Write minimal implementation**

Extend `.github/workflows/site-docker-publish.yml` with a gated publish job:

```yaml
  publish:
    runs-on: ubuntu-latest
    needs: smoke
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ format('{0}/pulse-site', secrets.DOCKERHUB_USERNAME) }}
          tags: |
            type=raw,value=latest
            type=sha,prefix=sha-
      - name: Build and push site image
        uses: docker/build-push-action@v6
        with:
          context: ./site
          file: ./site/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

**Step 4: Run test to verify it passes**

Run: `bash site/tests/github-actions-site-publish.sh`

Expected: PASS.

Then run: `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest`

Expected: PASS with no workflow syntax errors.

**Step 5: Commit**

```bash
git add site/tests/github-actions-site-publish.sh .github/workflows/site-docker-publish.yml
git commit -m "feat: publish site image to Docker Hub"
```

### Task 3: Final verification

**Files:**
- Verify only: `.github/workflows/site-docker-publish.yml`
- Verify only: `site/tests/github-actions-site-publish.sh`
- Verify only: `site/tests/static-site-smoke.sh`

**Step 1: Run focused workflow verification**

Run: `bash site/tests/github-actions-site-publish.sh`

Expected: PASS.

**Step 2: Run workflow lint verification**

Run: `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest`

Expected: PASS.

**Step 3: Run site smoke verification**

Run: `bash tests/static-site-smoke.sh`

Working directory: `site/`

Expected: PASS, confirming the same container path the workflow relies on still works locally.

**Step 4: Review the exact diff**

Run: `git diff -- .github/workflows/site-docker-publish.yml site/tests/github-actions-site-publish.sh`

Expected: Only the workflow and its focused verification script appear.

**Step 5: Commit**

```bash
git add .github/workflows/site-docker-publish.yml site/tests/github-actions-site-publish.sh
git commit -m "ci: automate site Docker image publishing"
```

## Assumptions

- The publish target is Docker Hub.
- The Docker Hub repository should default to `${DOCKERHUB_USERNAME}/pulse-site`.
- GitHub repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` will be configured before the publish job is expected to succeed.

## Verification Notes

- Keep the workflow secret-free for pull requests.
- Do not add preview-image publishing in this change.
- If `actionlint` is not already cached locally, the Docker image pull may take extra time on first run.

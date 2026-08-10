# PyPI trusted publishing (GitHub Actions)

Releases use [`.github/workflows/release-publish.yml`](https://github.com/JEFF7712/pulse/blob/main/.github/workflows/release-publish.yml), which runs when you push a version tag `v*`.

The **`publish-pypi`** job uses [OIDC trusted publishing](https://docs.pypi.org/trusted-publishers/) (no long-lived API token in the repo). If upload fails with **`invalid-publisher`**, add a matching publisher on PyPI.

## Configure on PyPI

1. PyPI → **pulse-agent** → **Publishing** → **Add a new pending publisher** (or manage existing).
2. **Publisher:** GitHub.
3. **Repository owner:** `JEFF7712`
4. **Repository name:** `pulse`
5. **Workflow name:** `release-publish.yml` (must match the file under `.github/workflows/`).
6. **Environment name:** leave empty unless you use a [GitHub Environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) in the workflow; if you add `environment: …` to the `publish-pypi` job, set the **same** name here.

After a failed run, open the **`publish-pypi`** log and copy the **claims** block PyPI prints (e.g. `sub`, `workflow_ref`, `ref`). Your PyPI publisher entry must match those claims. Tag pushes use `ref: refs/tags/vX.Y.Z` - if you only configured `refs/heads/main`, tag releases will not match.

## Manual upload

If you cannot use trusted publishing yet, build locally (`uv build`) and upload with `twine` and a PyPI API token, or temporarily adjust your fork’s workflow (not recommended for the canonical repo).

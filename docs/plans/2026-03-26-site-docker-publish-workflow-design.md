# Site Docker Publish Workflow Design

**Date:** 2026-03-26
**Status:** Approved
**Registry:** Docker Hub

---

## Goal

Add a GitHub Actions workflow that automatically builds the Docker image defined in `site/` and publishes it to Docker Hub.

The workflow should give fast feedback on pull requests without pushing unreviewed images, and it should publish production tags automatically from the default branch.

## Problem

The repository has a working containerized static site in `site/`, but image publication is still manual.

- `site/Dockerfile` already produces a small nginx-based image.
- `site/tests/static-site-smoke.sh` already validates the built container locally.
- There is no `.github/workflows/` automation yet for this site image.

That means image builds are not continuously verified in GitHub, and Docker Hub is not updated automatically when the site changes.

## Approved Direction

Use one GitHub Actions workflow with two responsibilities:

1. always verify the site image can be built and passes the existing smoke test when relevant files change,
2. publish the image to Docker Hub only from `main` after verification succeeds.

This keeps pull requests safe while still automating release publication.

## Workflow Shape

### Triggers

Run the workflow when either of these changes:

- files under `site/**`,
- the workflow file itself.

Trigger on:

- `pull_request` for validation,
- `push` to `main` for validation plus publish.

### Job layout

Use two jobs in the same workflow.

#### `smoke`

- checks out the repo,
- sets up Docker Buildx,
- runs `bash tests/static-site-smoke.sh` from `site/`.

This job is the shared gate for both pull requests and `main` pushes.

#### `publish`

- depends on `smoke`,
- runs only for `push` events on `refs/heads/main`,
- logs into Docker Hub,
- generates image metadata and tags,
- builds from `site/` and pushes the image.

Separating the publish job avoids mixing secret-dependent behavior into PR validation.

## Docker Hub Integration

The workflow should authenticate with these repository secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Until a different repository name is requested, publish to:

- `${DOCKERHUB_USERNAME}/pulse-site`

### Tags

Publish these tags on successful `main` pushes:

- `latest`
- `sha-<commit>`

This gives one stable tag for current production and one immutable tag for traceability.

## Verification Strategy

Reuse the existing site verification instead of inventing a second build path.

- `site/tests/static-site-smoke.sh` already exercises the real Dockerfile and container behavior.
- The workflow file itself should also be validated locally with `actionlint` before calling the work complete.

The key principle is that publishing happens only after the same image path has already passed the smoke check.

## Permissions and Safety

- Use minimal workflow permissions, starting with `contents: read`.
- Do not publish from pull requests.
- Fail fast if Docker Hub login, metadata generation, build, or push fails.
- Keep the workflow scoped to `site/` changes so unrelated repo work does not trigger image publication.

## Out of Scope

- multi-architecture images,
- release-tag publishing,
- automatic cleanup of old Docker Hub tags,
- publishing branch-specific preview images.

These can be added later if the site release process becomes more complex.

## Success Criteria

The work is successful when:

1. pull requests touching `site/` run GitHub Actions validation for the Dockerized site,
2. pushes to `main` build and publish the site image to Docker Hub,
3. the published image comes from `site/Dockerfile`,
4. Docker Hub credentials are sourced only from GitHub secrets,
5. the workflow passes local syntax validation and reuses the existing smoke test.

## Notes

- This design assumes the published Docker Hub repository should default to `${DOCKERHUB_USERNAME}/pulse-site`.
- I did not create a git commit for this design doc because you have not asked for one.

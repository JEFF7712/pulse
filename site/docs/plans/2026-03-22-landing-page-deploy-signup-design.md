# Landing Page Deploy and Signup Design

## Goal

Make the current static landing page deployable again, keep the smoke test aligned with the actual site structure, and prepare the signup flow to use a hosted form service instead of the current console-log demo.

## Current Context

- The live page is a single-file static site in `index.html` with inline CSS and a small inline script.
- `Dockerfile` and `tests/static-site-smoke.sh` still expect a separate `styles.css`, so container builds and smoke checks fail even though the page itself renders when served directly.
- The signup UI is only a demo: the JavaScript hides the form and logs the email locally.

## Recommended Approach

### 1. Keep the landing page as a single-file static site

Do not extract styles back into a separate asset just to satisfy stale tooling. The simplest and lowest-risk fix is to align deployment and tests with the current implementation.

### 2. Update deploy and smoke checks to validate real behavior

- Remove the nonexistent `styles.css` copy step from `Dockerfile`.
- Update `tests/static-site-smoke.sh` to verify the built container serves `index.html` and key landing page content.
- Keep the test focused on user-visible behavior rather than file layout assumptions.

### 3. Replace demo signup logic with a real hosted-form flow

- Use a semantic `<form>` with an email input and submit button.
- Post to a hosted form endpoint.
- Preserve a polished single-page experience by intercepting submission in JavaScript and showing inline success or error states.
- Fall back to native form behavior if JavaScript is unavailable.

## Alternatives Considered

### Recreate `styles.css`

This would make the old Dockerfile and test assumptions true again, but it adds extra refactoring with no user benefit.

### Build a backend API in this repo

This gives maximum control, but it is unnecessary complexity for a first landing-page signup capture flow.

## Files Expected to Change

- `Dockerfile`
- `tests/static-site-smoke.sh`
- `index.html`

## Testing Strategy

- Re-run `tests/static-site-smoke.sh` after the Dockerfile/test changes.
- Verify the container build succeeds.
- Verify served HTML includes stable landing-page markers and the signup form markup.
- For signup integration, verify the form handles success and failure states correctly once the hosted endpoint is chosen.

## Notes

- I did not create a git commit for this design doc because you have not asked for commits yet.

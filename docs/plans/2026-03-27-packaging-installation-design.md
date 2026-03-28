# Packaging And Installation Design

**Date:** 2026-03-27
**Status:** Approved
**Source Context:** `README.md`, `docs/self-hosting/quickstart.md`, `pyproject.toml`, `flake.nix`, `.github/workflows/ci.yml`, `src/pulse/app/cli.py`

---

## Goal

Make Pulse installable and runnable as a real released product without requiring a git checkout, while keeping the current contributor workflow intact.

The first packaging milestone should establish the Python package as the canonical release artifact, then derive Docker and Nix distribution from that same packaged release.

## Current state

Pulse already has the core pieces of a packageable app:

- a `pyproject.toml` with setuptools build metadata,
- console entrypoints for `pulse` and `pulse-mcp`,
- a lockfile-backed `uv` workflow,
- a Nix development shell,
- self-hosting docs and a CLI-guided operator flow.

What it does not yet have is a release-grade install model.

Today the operator path still assumes a source checkout and a repo-root runtime layout for `.env` and `pulse.toml`.

## Why this approach

The packaging problem is not primarily about changing build tools.

The important gap is making Pulse behave correctly when installed outside the repository.

By treating the Python package as the canonical artifact first, Pulse gets one authoritative definition for:

- versioning,
- dependencies and extras,
- entrypoints,
- install verification,
- downstream distribution.

That keeps PyPI, Docker, and Nix aligned instead of turning them into separate products with drifting runtime assumptions.

## Chosen approach

Use the Python package as the source of truth, then derive all operator-facing install channels from that released package.

This means:

- PyPI becomes the primary distribution target,
- the published distribution name becomes `pulse-agent` because `pulse` is already taken on PyPI,
- the console entrypoints remain `pulse` and `pulse-mcp`,
- `pipx install pulse-agent`, `uv tool install pulse-agent`, and `pip install pulse-agent` become first-class install paths,
- Docker images install the released wheel instead of copying the repo,
- Nix packages the same released version,
- source checkout workflows remain for contributors, not as the main operator install story.

## Supported install channels

The first release should explicitly support these channels:

1. `pipx install pulse-agent`
2. `uv tool install pulse-agent`
3. `pip install pulse-agent`
4. Docker image built from the released package
5. Nix package derived from the same released version

The published distribution can differ from the import package name. In this design, operators install `pulse-agent`, but the Python module path remains `pulse` and the CLI commands remain `pulse` and `pulse-mcp`.

The existing contributor workflow stays supported:

- `uv sync`
- `pip install -e .`
- `nix develop`

## Runtime model

Installed Pulse must stop assuming the repository root is the runtime home.

Config resolution should follow this precedence:

1. explicit CLI override such as `--config-dir`
2. environment override such as `PULSE_CONFIG_DIR`
3. standard user config directory such as `~/.config/pulse`
4. current working directory as a backward-compatibility fallback

This keeps installs usable outside the repo while preserving existing local setups during migration.

## Config and data layout

Pulse should separate configuration from mutable runtime data.

Recommended defaults:

- config directory: `~/.config/pulse/`
- data directory: `~/.local/share/pulse/`

Expected file placement:

- `.env` in the config directory
- `pulse.toml` in the config directory
- SQLite database in the data directory by default
- OAuth token files in the data directory by default
- vault output in the data directory by default unless explicitly configured elsewhere

If the operator overrides paths in config or environment variables, those explicit values win.

## CLI behavior

`pulse configure` becomes the canonical first-run entrypoint for installed Pulse.

Its job is to:

- create the config directory when missing,
- write or update `.env`,
- write or update `pulse.toml`,
- guide the user toward `pulse init` and `pulse run`.

Missing-config behavior should be explicit and actionable.

If Pulse cannot find configuration, it should fail with a clear message telling the operator to run `pulse configure` or set `PULSE_CONFIG_DIR`, rather than silently relying on repository layout assumptions.

## Extras and dependency model

The base package should keep the current core app dependencies and entrypoints.

Optional provider integrations should remain installable through extras, for example:

- `pulse[openai]`
- `pulse[gemini]`
- `pulse[all-llm]`

That keeps the default install lighter while preserving a clean upgrade path for operators who enable extra providers.

## Release artifacts

Every release should produce:

- a wheel,
- an sdist.

These are the only canonical app artifacts.

Docker and Nix should be downstream consumers of the same versioned release, not parallel packaging roots.

## Release flow

The release flow should use tagged versions as the source of publishable artifacts.

For each release:

1. build wheel and sdist from `pyproject.toml`
2. run clean-environment install smoke tests against built artifacts
3. publish the package to PyPI
4. build Docker from the released wheel
5. update or publish the matching Nix package for the same version

Version numbers across PyPI, Docker tags, and Nix packaging should match exactly.

## Verification requirements

Release CI should verify the installed-product path, not just the repo path.

Minimum checks:

- build wheel and sdist successfully,
- install the package in a clean environment,
- run `pulse --help`,
- run `pulse-mcp --help`,
- verify config discovery works outside the repository,
- verify the legacy repo-root path still works during migration,
- keep the existing test suite running in the source-based CI path.

The important rule is that packaging verification must prove Pulse works as an installed application, not only as a checked-out codebase.

## Docker derivation

The Docker image should install the released Pulse package rather than copying the source tree directly into the image.

This has two benefits:

- it keeps container runtime behavior aligned with PyPI installs,
- it forces packaging mistakes to surface before or during image build.

The image can still include channel-specific runtime defaults, but it should not become a separate application definition.

## Nix derivation

Nix packaging should consume the same released Pulse version as PyPI.

Whether the package is built from sdist, wheel, or the exact tagged source used to generate them, the package definition should preserve version parity and runtime behavior with the canonical release.

The existing `flake.nix` development shell remains useful for contributors, but it is not sufficient by itself as the operator packaging story.

## Backward compatibility

Existing setups that run from the repository root should keep working during the transition.

Specifically:

- repo-root config discovery remains temporarily supported,
- `uv sync` and editable installs remain documented for contributors,
- operator docs shift to release installs first,
- legacy behavior is treated as compatibility mode rather than the long-term default.

This reduces migration risk while letting packaging move forward.

## Documentation split

The docs should clearly separate operator installation from contributor setup.

Operator-facing docs should lead with release installs:

- `pipx install pulse-agent`
- `uv tool install pulse-agent`
- `pip install pulse-agent`
- Docker and Nix variants derived from the same release

Contributor docs should continue to cover:

- `uv sync`
- `pip install -e .`
- `nix develop`

This prevents the current confusion where source checkout instructions double as deployment guidance.

## Rollout plan

The rollout should happen in phases:

1. make config and data resolution install-safe
2. add artifact builds and installed-package smoke tests
3. publish the Python package
4. switch Docker to consume the packaged release
5. add or align Nix packaging to the same released version
6. update docs so release installs are the primary operator path

This ordering ensures the runtime model is correct before distribution channels are layered on top.

## Non-goals for this slice

- redesigning the application architecture,
- changing build backends without a packaging need,
- creating separate feature sets per distribution channel,
- removing the contributor-oriented source workflow,
- solving every long-term service-management concern such as systemd units in the first slice.

## Success criteria

This work is successful when:

- a new user can install Pulse without cloning the repo,
- `pulse configure` can bootstrap a fresh installed setup,
- `pulse run` works from an installed environment,
- Docker and Nix consume the same released version,
- release CI proves installed-package behavior,
- existing repo-root setups continue to function during migration.

## Result

After this slice, Pulse will have a coherent packaging foundation: one canonical Python release artifact, one install-safe runtime model, and downstream Docker and Nix distribution that inherit from the same packaged application instead of re-defining it.

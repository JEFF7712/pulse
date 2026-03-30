# Contributing to Pulse

Thanks for helping improve Pulse. This document covers how to set up a development environment, run the same checks as CI, and what we look for in contributions.

## Before you start

- **Issues and design discussion** — For larger changes (new connectors, breaking config, or new dependencies), opening an issue first helps align on direction and avoids duplicate work.
- **Secrets** — Never commit API keys, OAuth tokens, or real `pulse.toml` paths that expose your setup. Use `pulse.toml.example` and environment variables as references.

## Development setup

**Recommended: [uv](https://docs.astral.sh/uv/)**

```bash
uv sync --group dev
```

**Nix** — From the repo root: `nix develop`, then use the provided environment (uv keeps `.venv` in sync).

**Classic venv** — Create a virtualenv, then `pip install -e .` and `pip install pytest` (or install the `dev` group equivalent).

More context on config paths, env vars, and running the app lives in [README.md](README.md).

## Run tests (match CI)

Continuous integration runs on Python **3.12** and **3.13** against a locked dependency set:

```bash
uv sync --group dev --locked
uv run pytest tests/ --tb=short -q
```

Optional local parity with CI:

```bash
uv build
uv run python scripts/smoke_installed_package.py dist
```

## Pull requests

- **Target branch** — Open PRs against `main`.
- **Description** — Summarize what changed and why. Link related issues if any.
- **Scope** — Prefer focused changes (one logical concern per PR) so review and bisection stay easy.
- **Docs** — If behavior or configuration changes, update the relevant files under `docs/` when applicable.

## Project layout

Python package source lives under `src/pulse/`. High-level areas:

| Path | Role |
|------|------|
| `src/pulse/app/` | FastAPI app, CLI, config |
| `src/pulse/connectors/` | Data source integrations |
| `src/pulse/mcp/` | MCP server |
| `src/pulse/store/` | SQLite persistence |
| `tests/` | Pytest suite |

## License

By contributing, you agree your contributions are licensed under the same terms as the project ([MIT License](LICENSE)).

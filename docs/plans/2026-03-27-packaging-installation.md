# Packaging And Installation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship Pulse as the `pulse-agent` Python distribution with install-safe config resolution, then derive CI, Docker, docs, and Nix packaging from that canonical package while keeping the `pulse` and `pulse-mcp` commands.

**Architecture:** Introduce one runtime path-resolution layer so installed Pulse can find `.env`, `pulse.toml`, database, and vault paths outside the repo. Once every runtime entrypoint uses that resolver, tighten package metadata, add clean-environment smoke checks, and derive Docker and Nix outputs plus release automation from the same versioned package.

**Tech Stack:** Python 3.12/3.13, setuptools / PEP 621, uv, pytest, GitHub Actions, Docker, Nix flakes

---

### Task 1: Rename the published distribution and lock metadata

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/unit/test_packaging_metadata.py`

**Step 1: Write the failing metadata test**

```python
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_matches_release_install_story() -> None:
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]

    assert project["name"] == "pulse-agent"
    assert project["readme"] == "README.md"
    assert project["scripts"]["pulse"] == "pulse.app.cli:main"
    assert project["scripts"]["pulse-mcp"] == "pulse.mcp.server:main"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_packaging_metadata.py -v`
Expected: FAIL because `pyproject.toml` still publishes the distribution as `pulse` and points `readme` at `DESIGN.md`.

**Step 3: Write minimal implementation**

```toml
[project]
name = "pulse-agent"
readme = "README.md"
description = "Self-hosted personal intelligence agent"
requires-python = ">=3.12"

[project.scripts]
pulse = "pulse.app.cli:main"
pulse-mcp = "pulse.mcp.server:main"
```

Keep the import package as `pulse`; only the published distribution name changes.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_packaging_metadata.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml tests/unit/test_packaging_metadata.py
git commit -m "build: rename published distribution to pulse-agent"
```

### Task 2: Add install-safe config and data path resolution

**Files:**
- Create: `src/pulse/app/paths.py`
- Modify: `src/pulse/app/config_loader.py`
- Create: `tests/unit/test_paths.py`
- Modify: `tests/unit/test_config_loader.py`

**Step 1: Write the failing path-resolution tests**

```python
from pathlib import Path

from pulse.app.config_loader import load_config
from pulse.app.paths import resolve_pulse_paths


def test_resolve_pulse_paths_prefers_explicit_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    paths = resolve_pulse_paths(config_dir=tmp_path / "chosen")

    assert paths.config_dir == (tmp_path / "chosen").resolve()
    assert paths.env_path == paths.config_dir / ".env"
    assert paths.toml_path == paths.config_dir / "pulse.toml"
    assert paths.data_dir == (tmp_path / "xdg-data" / "pulse").resolve()


def test_resolve_pulse_paths_uses_legacy_cwd_when_config_files_exist(tmp_path):
    (tmp_path / ".env").write_text("PULSE_TIMEZONE=UTC\n")
    paths = resolve_pulse_paths(cwd=tmp_path)
    assert paths.config_dir == tmp_path.resolve()


def test_load_config_uses_data_dir_defaults_when_paths_are_not_set(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "pulse.toml").write_text("")
    monkeypatch.setenv("PULSE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))

    config = load_config()

    assert config.database_path == str((tmp_path / "xdg-data" / "pulse" / "pulse.db").resolve())
    assert config.vault_path == str((tmp_path / "xdg-data" / "pulse" / "Pulse-Vault").resolve())
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_paths.py tests/unit/test_config_loader.py -v`
Expected: FAIL with `ModuleNotFoundError` for `pulse.app.paths` and default-path assertion failures.

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class PulsePaths:
    config_dir: Path
    data_dir: Path
    env_path: Path
    toml_path: Path


def resolve_pulse_paths(config_dir: Path | None = None, cwd: Path | None = None) -> PulsePaths:
    cwd = (cwd or Path.cwd()).resolve()
    explicit = config_dir or os.environ.get("PULSE_CONFIG_DIR")
    if explicit is not None:
        resolved_config = Path(explicit).expanduser().resolve()
    elif (cwd / "pulse.toml").exists() or (cwd / ".env").exists():
        resolved_config = cwd
    else:
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        resolved_config = (xdg_config / "pulse").resolve()

    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    data_dir = (xdg_data / "pulse").resolve()
    return PulsePaths(
        config_dir=resolved_config,
        data_dir=data_dir,
        env_path=resolved_config / ".env",
        toml_path=resolved_config / "pulse.toml",
    )
```

Then update `load_config()` to call `load_dotenv(paths.env_path, override=False)` and merge dynamic defaults before file/env overrides:

```python
defaults = {
    "database_path": str(paths.data_dir / "pulse.db"),
    "vault_path": str(paths.data_dir / "Pulse-Vault"),
    "timezone": "UTC",
}
merged = {**defaults, **file_values, **env_values}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_paths.py tests/unit/test_config_loader.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/pulse/app/paths.py src/pulse/app/config_loader.py tests/unit/test_paths.py tests/unit/test_config_loader.py
git commit -m "feat: resolve Pulse config and data paths outside repo"
```

### Task 3: Thread `--config-dir` through the CLI

**Files:**
- Modify: `src/pulse/app/cli.py`
- Create: `tests/unit/test_cli.py`

**Step 1: Write the failing CLI parser tests**

```python
from pathlib import Path

from pulse.app import cli


def test_build_parser_accepts_config_dir_for_run() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")


def test_build_parser_accepts_config_dir_for_configure() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["configure", "--config-dir", "/tmp/pulse-config"])
    assert args.config_dir == Path("/tmp/pulse-config")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL because `build_parser()` does not exist and no subcommand accepts `--config-dir`.

**Step 3: Write minimal implementation**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(...)
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing .env and pulse.toml",
    )

    run_parser = subparsers.add_parser("run", parents=[config_parent], ...)
    configure_parser = subparsers.add_parser("configure", parents=[config_parent], ...)
    ...
    return parser
```

Then pass `config_dir=getattr(args, "config_dir", None)` into every command that currently calls `load_config()` or writes `.env` / `pulse.toml`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_paths.py tests/unit/test_config_loader.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/pulse/app/cli.py tests/unit/test_cli.py
git commit -m "feat: add config-dir override to Pulse CLI"
```

### Task 4: Add actionable missing-config errors

**Files:**
- Modify: `src/pulse/app/config_loader.py`
- Modify: `src/pulse/app/cli.py`
- Modify: `src/pulse/mcp/server.py`
- Modify: `src/pulse/app/dependencies.py`
- Modify: `tests/unit/test_config_loader.py`
- Modify: `tests/unit/test_cli.py`

**Step 1: Write the failing error-handling tests**

```python
import pytest

from pulse.app.config_loader import PulseConfigNotFoundError, load_config


def test_load_config_can_require_existing_config_files(tmp_path):
    with pytest.raises(PulseConfigNotFoundError) as exc:
        load_config(config_dir=tmp_path / "missing", require_files=True)

    assert "pulse configure" in str(exc.value)
    assert "PULSE_CONFIG_DIR" in str(exc.value)
```

```python
import pytest

from pulse.app import cli


def test_status_shows_actionable_message_when_config_missing(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli._status(config_dir=tmp_path / "missing")

    out = capsys.readouterr().out
    assert "pulse configure" in out
    assert "PULSE_CONFIG_DIR" in out
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_config_loader.py tests/unit/test_cli.py -v`
Expected: FAIL because `load_config()` silently falls back to defaults and `_status()` does not catch a config-not-found error.

**Step 3: Write minimal implementation**

```python
class PulseConfigNotFoundError(FileNotFoundError):
    pass


def load_config(..., require_files: bool = False) -> PulseConfig:
    paths = resolve_pulse_paths(...)
    if require_files and not paths.env_path.exists() and not paths.toml_path.exists():
        raise PulseConfigNotFoundError(
            f"No Pulse config found in {paths.config_dir}. Run 'pulse configure' or set PULSE_CONFIG_DIR."
        )
```

In CLI commands that need a real setup (`run`, `pull`, `digest`, `discover`, `status`, `insights`, `logs`, `reset`, `cleanup`, `test-telegram`, `auth`, `init`, `onboard`), catch `PulseConfigNotFoundError`, print the message with `ui.error(...)`, and exit cleanly.

In `src/pulse/mcp/server.py`, catch the same error during lifespan startup and raise `RuntimeError(str(exc))` so MCP startup fails with a readable message.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config_loader.py tests/unit/test_cli.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/pulse/app/config_loader.py src/pulse/app/cli.py src/pulse/mcp/server.py src/pulse/app/dependencies.py tests/unit/test_config_loader.py tests/unit/test_cli.py
git commit -m "feat: add install-safe config error messages"
```

### Task 5: Make `pulse configure` write install-safe defaults

**Files:**
- Modify: `src/pulse/app/cli.py`
- Modify: `tests/unit/test_cli.py`

**Step 1: Write the failing configure-default tests**

```python
from pulse.app.paths import PulsePaths
from pulse.app import cli


def test_default_env_values_use_resolved_data_dir(tmp_path):
    paths = PulsePaths(
        config_dir=(tmp_path / "config").resolve(),
        data_dir=(tmp_path / "data").resolve(),
        env_path=(tmp_path / "config" / ".env").resolve(),
        toml_path=(tmp_path / "config" / "pulse.toml").resolve(),
    )

    values = cli._default_env_values(paths)

    assert values["PULSE_DATABASE_PATH"] == str((tmp_path / "data" / "pulse.db").resolve())
    assert values["PULSE_VAULT_PATH"] == str((tmp_path / "data" / "Pulse-Vault").resolve())
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL because `_default_env_values()` does not exist and `_configure()` still hard-codes repo-root paths.

**Step 3: Write minimal implementation**

```python
def _default_env_values(paths: PulsePaths) -> dict[str, str]:
    return {
        "PULSE_DATABASE_PATH": str(paths.data_dir / "pulse.db"),
        "PULSE_VAULT_PATH": str(paths.data_dir / "Pulse-Vault"),
        "PULSE_TIMEZONE": "UTC",
    }


def _configure(*, config_dir: Path | None = None, offer_oauth: bool = True) -> None:
    paths = resolve_pulse_paths(config_dir=config_dir)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    env_path = paths.env_path
    toml_path = paths.toml_path
    ...
```

Also update onboarding/help text so it says “Run from the directory where your config lives” only when legacy repo-root mode is detected; otherwise show the resolved config dir or `PULSE_CONFIG_DIR` guidance.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_paths.py tests/unit/test_config_loader.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/pulse/app/cli.py tests/unit/test_cli.py
git commit -m "feat: make pulse configure write install-safe defaults"
```

### Task 6: Update operator docs to the release-install story

**Files:**
- Modify: `README.md`
- Modify: `docs/self-hosting/quickstart.md`
- Modify: `docs/index.md`
- Modify: `docs/reference/configuration.md`
- Modify: `tests/unit/test_documentation_contract.py`

**Step 1: Write the failing documentation contract updates**

```python
QUICKSTART_REQUIRED_SNIPPETS = [
    "pipx install pulse-agent",
    "uv tool install pulse-agent",
    "pip install pulse-agent",
    "pulse configure",
    "pulse run",
]

README_REQUIRED_SNIPPETS = [
    "pulse-agent",
    "`PULSE_CONFIG_DIR`",
    "`pulse` and `pulse-mcp`",
]
```

Add assertions that `docs/reference/configuration.md` mentions:

- `~/.config/pulse`
- `~/.local/share/pulse`
- repo-root discovery as a compatibility fallback

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v`
Expected: FAIL because the docs still lead with `uv sync` / `pip install -e .` and repo-root config.

**Step 3: Write minimal implementation**

```md
pipx install pulse-agent
# or
uv tool install pulse-agent
# or
pip install pulse-agent

# Installed command names stay the same:
pulse configure
pulse run
```

Update the docs to explain:

- the published package is `pulse-agent`,
- the executable names are still `pulse` and `pulse-mcp`,
- installed config lives under `~/.config/pulse` by default,
- installed state lives under `~/.local/share/pulse` by default,
- repo-root `.env` / `pulse.toml` lookup still works as a migration fallback,
- contributor setup still uses `uv sync`, `pip install -e .`, and `nix develop`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_documentation_contract.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add README.md docs/self-hosting/quickstart.md docs/index.md docs/reference/configuration.md tests/unit/test_documentation_contract.py
git commit -m "docs: update install guides for pulse-agent"
```

### Task 7: Add installed-package smoke checks to CI

**Files:**
- Create: `scripts/smoke_installed_package.py`
- Modify: `.github/workflows/ci.yml`

**Step 1: Run the smoke command before the script exists**

Run: `uv build && uv run python scripts/smoke_installed_package.py dist`
Expected: FAIL because `scripts/smoke_installed_package.py` does not exist yet.

**Step 2: Write the smoke script**

```python
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def main(dist_dir: str) -> None:
    wheel = sorted(Path(dist_dir).glob("pulse_agent-*.whl"))[-1]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        venv = root / "venv"
        config_dir = root / "config"
        data_dir = root / "data"
        run([sys.executable, "-m", "venv", str(venv)])
        run([str(venv / "bin" / "pip"), "install", str(wheel)])
        run([str(venv / "bin" / "pulse"), "--help"])
        run([str(venv / "bin" / "pulse-mcp"), "--help"])
        config_dir.mkdir()
        data_dir.mkdir()
        (config_dir / "pulse.toml").write_text("")
        env = {
            **os.environ,
            "PULSE_CONFIG_DIR": str(config_dir),
            "XDG_DATA_HOME": str(root / "xdg-data"),
        }
        run(
            [
                str(venv / "bin" / "python"),
                "-c",
                "from pulse.app.config_loader import load_config; cfg = load_config(); print(cfg.database_path); print(cfg.vault_path)",
            ],
            env=env,
        )
```

**Step 3: Wire the smoke script into CI**

```yaml
- name: Build package artifacts
  run: uv build

- name: Smoke test installed package
  run: uv run python scripts/smoke_installed_package.py dist
```

Add the smoke step after `uv run pytest`; if CI runtime gets too expensive, keep it on one Python version only.

**Step 4: Run the smoke command to verify it passes**

Run: `uv build && uv run python scripts/smoke_installed_package.py dist`
Expected: PASS; the script should build artifacts, install the wheel into a throwaway venv, and run `pulse --help`, `pulse-mcp --help`, and config-loader smoke checks outside the repo.

**Step 5: Commit**

```bash
git add scripts/smoke_installed_package.py .github/workflows/ci.yml
git commit -m "ci: smoke test installed package artifacts"
```

### Task 8: Add a wheel-based runtime Docker image

**Files:**
- Create: `Dockerfile`
- Create: `tests/unit/test_dockerfile_contract.py`

**Step 1: Write the failing Dockerfile contract test**

```python
from pathlib import Path


def test_runtime_dockerfile_installs_built_wheel() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG PULSE_WHEEL" in dockerfile
    assert "COPY ${PULSE_WHEEL} /tmp/pulse.whl" in dockerfile
    assert "pip install --no-cache-dir /tmp/pulse.whl" in dockerfile
    assert "PULSE_CONFIG_DIR=/config" in dockerfile
    assert 'CMD ["pulse", "run"' in dockerfile
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_dockerfile_contract.py -v`
Expected: FAIL with `FileNotFoundError` because no app `Dockerfile` exists yet.

**Step 3: Write minimal implementation**

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ARG PULSE_WHEEL
ENV PULSE_CONFIG_DIR=/config \
    PULSE_DATABASE_PATH=/data/pulse.db \
    PULSE_VAULT_PATH=/data/Pulse-Vault

COPY ${PULSE_WHEEL} /tmp/pulse.whl
RUN pip install --no-cache-dir /tmp/pulse.whl && rm /tmp/pulse.whl

RUN mkdir -p /config /data
VOLUME ["/config", "/data"]
EXPOSE 8000
CMD ["pulse", "run", "--host", "0.0.0.0", "--port", "8000"]
```

This keeps the container derived from the built wheel instead of from a repo copy.

**Step 4: Run tests and Docker smoke checks**

Run: `uv run pytest tests/unit/test_dockerfile_contract.py -v && uv build && docker build --build-arg PULSE_WHEEL=dist/pulse_agent-*.whl -t pulse:test . && docker run --rm pulse:test pulse --help`
Expected: PASS; the Docker image builds from the wheel and the container can execute the packaged CLI.

**Step 5: Commit**

```bash
git add Dockerfile tests/unit/test_dockerfile_contract.py
git commit -m "build: add wheel-based runtime Docker image"
```

### Task 9: Expose packaged Pulse through flake outputs

**Files:**
- Modify: `flake.nix`
- Create: `tests/unit/test_flake_contract.py`

**Step 1: Write the failing flake contract test**

```python
from pathlib import Path


def test_flake_exposes_package_and_app_outputs() -> None:
    flake = Path("flake.nix").read_text(encoding="utf-8")

    assert "packages.default" in flake
    assert "apps.pulse" in flake or "apps.default" in flake
    assert '"/bin/pulse"' in flake
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_flake_contract.py -v`
Expected: FAIL because `flake.nix` only exposes `devShells.default` today.

**Step 3: Write minimal implementation**

```nix
packages.default = pythonPkgs.buildPythonApplication {
  pname = "pulse-agent";
  version = "0.1.0";
  pyproject = true;
  src = ./.;
  nativeBuildInputs = [ pythonPkgs.setuptools ];
  propagatedBuildInputs = with pythonPkgs; [
    rich rich-argparse fastapi pydantic aiosqlite apscheduler httpx
    feedparser mcp google-auth-oauthlib google-api-python-client anthropic
    uvicorn plaid-python
  ];
};

apps.pulse = flake-utils.lib.mkApp {
  drv = self.packages.${system}.default;
  exePath = "/bin/pulse";
};
```

Keep `devShells.default` unchanged. If one dependency attr name differs in nixpkgs, fix that attr name in-place rather than switching the whole repo to a new Nix packaging stack.

**Step 4: Run tests and Nix verification**

Run: `uv run pytest tests/unit/test_flake_contract.py -v && nix build .#default && nix run .#pulse -- --help`
Expected: PASS; the flake should build a packaged app and expose the `pulse` command.

**Step 5: Commit**

```bash
git add flake.nix tests/unit/test_flake_contract.py
git commit -m "build: expose Pulse package through flake outputs"
```

### Task 10: Add the tag-driven release workflow

**Files:**
- Create: `.github/workflows/release-publish.yml`
- Create: `tests/unit/test_release_workflow_contract.py`

**Step 1: Write the failing workflow contract test**

```python
from pathlib import Path


def test_release_workflow_publishes_package_and_docker_image() -> None:
    workflow = Path(".github/workflows/release-publish.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow
    assert "v*" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "scripts/smoke_installed_package.py dist" in workflow
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_release_workflow_contract.py -v`
Expected: FAIL with `FileNotFoundError` because no release workflow exists yet.

**Step 3: Write minimal implementation**

```yaml
name: Release Publish

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group dev --locked
      - run: uv run pytest tests/ --tb=short -q
      - run: uv build
      - run: uv run python scripts/smoke_installed_package.py dist
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/*

  publish-pypi:
    needs: build
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1

  publish-docker:
    needs: build
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: Dockerfile
          build-args: |
            PULSE_WHEEL=dist/pulse_agent-*.whl
```

Prefer trusted publishing (`id-token: write`) for PyPI rather than a long-lived token secret.

**Step 4: Run the contract test to verify it passes**

Run: `uv run pytest tests/unit/test_release_workflow_contract.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add .github/workflows/release-publish.yml tests/unit/test_release_workflow_contract.py
git commit -m "ci: add release workflow for pulse-agent"
```

### Task 11: Run the full verification suite and clean up any fallout

**Files:**
- Modify as needed: any file touched by fixes discovered during verification

**Step 1: Run the focused Python tests**

Run: `uv run pytest tests/unit/test_packaging_metadata.py tests/unit/test_paths.py tests/unit/test_config_loader.py tests/unit/test_cli.py tests/unit/test_documentation_contract.py tests/unit/test_dockerfile_contract.py tests/unit/test_flake_contract.py tests/unit/test_release_workflow_contract.py -v`
Expected: PASS.

**Step 2: Run the full test suite**

Run: `uv run pytest tests/ --tb=short -q`
Expected: PASS.

**Step 3: Run the packaging and install verification commands**

Run: `uv build && uv run python scripts/smoke_installed_package.py dist`
Expected: PASS.

**Step 4: Run the cross-channel verification commands**

Run: `docker build --build-arg PULSE_WHEEL=dist/pulse_agent-*.whl -t pulse:test . && docker run --rm pulse:test pulse --help && nix build .#default && nix run .#pulse -- --help`
Expected: PASS.

**Step 5: Commit any verification-driven fixes**

```bash
git add pyproject.toml src/pulse/app/paths.py src/pulse/app/config_loader.py src/pulse/app/cli.py src/pulse/mcp/server.py src/pulse/app/dependencies.py README.md docs/self-hosting/quickstart.md docs/index.md docs/reference/configuration.md .github/workflows/ci.yml .github/workflows/release-publish.yml Dockerfile flake.nix scripts/smoke_installed_package.py tests/unit/test_packaging_metadata.py tests/unit/test_paths.py tests/unit/test_config_loader.py tests/unit/test_cli.py tests/unit/test_documentation_contract.py tests/unit/test_dockerfile_contract.py tests/unit/test_flake_contract.py tests/unit/test_release_workflow_contract.py
git commit -m "chore: finish packaging and installation rollout"
```

# Self-Hosting Quickstart

**Happy path:** `pulse configure` → `pulse init` → `pulse run`.

## Install

Ships `pulse` and `pulse-mcp`.

**One-liner** (installs [pipx](https://pipx.pypa.io/) if needed, then `pulse-agent`; prints CLI-matched styling; runs **`pulse onboard`** at the end when a real terminal is available — including **`curl | bash`**, by attaching stdin to `/dev/tty` when needed):

```bash
curl -fsSL https://pulseagent.dev/install.sh | bash
```

Skip the onboarding wizard at the end:

```bash
curl -fsSL https://pulseagent.dev/install.sh | bash -s -- --no-onboard
```

Manual install (if you already use pipx):

```bash
pipx install pulse-agent
```

**Other methods**

- **uv** — `uv tool install pulse-agent`
- **pip** — use a virtualenv; `pip install pulse-agent`

### Docker

The image serves the app on **port 8000**, keeps config under **`/config`** (`PULSE_CONFIG_DIR`), and SQLite plus the vault under **`/data`**. The [`Dockerfile`](https://github.com/JEFF7712/pulse/blob/main/Dockerfile) builds the `pulse_agent` wheel inside the image (no local `uv build` required). On tagged releases, CI publishes to **`ghcr.io/<github-owner>/<repo>`** (GitHub lowercases the path; substitute your fork’s owner and repository name).

#### Pull from GitHub Container Registry

Example for this repository (adjust owner/repo for your fork):

```bash
docker pull ghcr.io/jeff7712/pulse:latest
# optional: pin a release version
docker pull ghcr.io/jeff7712/pulse:2.0.3
```

If the package is **private**, authenticate before `pull`:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

Use a personal access token with the **`read:packages`** scope (classic PAT) or fine-grained access to read GitHub Packages.

#### Run the server

Typical detached run:

```bash
docker run -d --name pulse \
  -p 8000:8000 \
  -v pulse-config:/config \
  -v pulse-data:/data \
  ghcr.io/jeff7712/pulse:latest
```

Open `http://localhost:8000`. For logs in the foreground, omit `-d` (add `--rm` if you do not need a named container).

If you built locally with `-t pulse`, replace the image name with `pulse`.

#### First-time setup (interactive)

`pulse configure` and `pulse onboard` need a TTY. Full first-run wizard and then start the server in the same container:

```bash
docker run --rm -it \
  -p 8000:8000 \
  -v pulse-config:/config \
  -v pulse-data:/data \
  ghcr.io/jeff7712/pulse:latest \
  pulse onboard
```

Configure only, then run a **separate** long-lived `docker run` (as above) for `pulse run`:

```bash
docker run --rm -it \
  -v pulse-config:/config \
  -v pulse-data:/data \
  ghcr.io/jeff7712/pulse:latest \
  pulse configure
```

#### Build and run from a clone

From the repository root:

```bash
docker build -t pulse -f Dockerfile .
docker run -d --name pulse \
  -p 8000:8000 \
  -v pulse-config:/config \
  -v pulse-data:/data \
  pulse
```

#### Docker Compose

From the repository root:

```bash
docker compose up --build -d
```

Uses root [`compose.yaml`](https://github.com/JEFF7712/pulse/blob/main/compose.yaml); same URL `http://localhost:8000`. The service uses **`restart: unless-stopped`** so the container comes back after reboot (until you `docker compose down`).

#### systemd (native `pulse` install)

For a **pipx** / **`uv tool install`** layout, copy and enable the example user unit from [`deploy/systemd/pulse-user.service.example`](https://github.com/JEFF7712/pulse/blob/main/deploy/systemd/pulse-user.service.example) to `~/.config/systemd/user/pulse.service`, adjust **`ExecStart`** if your `pulse` binary lives elsewhere, then `systemctl --user daemon-reload` and `systemctl --user enable --now pulse.service`. Use **`loginctl enable-linger "$USER"`** if you want the unit to start at boot without an interactive session.

#### Data volumes and stopping

- **`pulse-data`** — database and vault (`/data` in the container).
- **`pulse-config`** — configuration (`/config` in the container).

Stop and remove the container:

```bash
docker stop pulse && docker rm pulse
```

With Compose: `docker compose down`. Named volumes **persist** until you remove them explicitly, for example:

```bash
docker volume rm pulse-config pulse-data
```

That deletes stored config and data — use only when you intend to reset.

**Any Python 3.12+ base image** — install `pulse-agent` with pip, set the same `PULSE_*` paths (or bind-mount host directories to match), then `pulse run --host 0.0.0.0 --port 8000`.

Check with `pulse --help` after any install path.

The install script lives at [`scripts/install.sh` in the repository](https://github.com/JEFF7712/pulse/blob/main/scripts/install.sh) if you prefer to download and audit it before running.

## Developer install

- **uv:** `uv sync` (optional `--group dev`)
- **Nix:** `nix develop`, then `uv sync --group dev`
- **venv:** `python3 -m venv .venv` → activate → `pip install -e .`

### Run the FastAPI app from a clone

```bash
uv run uvicorn --app-dir src pulse.app.main:create_app --factory
```

## 1. Configure

If you use Google, Spotify, Microsoft 365, GitHub, GitLab, or Plaid, create OAuth (and Plaid) apps first so client IDs and secrets are ready. Oura: personal access token or OAuth app.

```bash
pulse configure
```

**Menu:** Core (database, vault, timezone), **Connectors** (per-source creds + OAuth/Plaid/Oura when ●), Notifications, **Model** (provider API keys + LLM roles in TOML), Full wizard. TTY: arrows + Enter; else digits `0`–`5` (`0` = Done). **`PULSE_*`** overrides top-level TOML when set in the environment.

**Config file:** Prefer **`.config/pulse.toml`** or repo-root **`pulse.toml`**. Override with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`**. Start from `pulse.toml.example`; connectors default to disabled until you enable them.

There is no separate `pulse auth` command. In **Configure → Connectors**, open each enabled OAuth/Plaid/Oura source and finish the browser flow (localhost callbacks on `8888`, `8890`–`8894` as applicable). Complete this **before** `pulse init` if the first pull should hit those APIs. Notion, Linear (API key), browser, and feeds skip browser OAuth here.

**Shortcut:** `pulse onboard` walks through the same configure areas as [cmd]pulse configure[/] (core → connectors → notifications → model), then runs connector OAuth / Plaid / Oura when credentials and enabled connectors allow it. Use `pulse onboard --strict` to fail if any auth step fails. Profile flags match `pulse init` (`-f`, `--profile-text`); server: `--host`, `--port`, `--log-level`.

## 2. `pulse init`

```bash
pulse init
```

Ensures vault **`README.md`** and **`Meta/AGENTS.md`** exist (created once if missing), writes **`04-Config/profile.md`**, runs initial pulls, optional discovery when LLM + notification config allows.

Interactive **TTY** profile step: copy the plain-text export prompt (between rules, no box borders), paste the assistant’s reply, then type **`---END---`** on its own line and press Enter (or finish with **Ctrl-D** / **Ctrl-Z**+Enter). Use **`-f`** / **`--profile-text`** to skip prompts.

## 3. `pulse run`

```bash
pulse run
```

Serves on `0.0.0.0:8000` by default (`--host` / `--port` / `--log-level` to change). **`/`** — operator page with Pull, Discover, Test Telegram (same pipelines as CLI where noted).

## 4. Inspect

```bash
pulse status
pulse insights
```

`status` — DB path, event counts, cursors. `insights` — discovery output; prompts you to run discovery first if empty.

| Command | Purpose |
| --- | --- |
| `pulse pull [sources…]` | Immediate connector pulls |
| `pulse discover [--cadence …]` | Manual discovery pass |
| `pulse test-telegram` | One-off Telegram test |

Re-open **Configure → Connectors** anytime to re-auth or edit `pulse.toml`.

## Connect Pulse to your coding agent (MCP) {#mcp-agent-paste}

Use the [Model Context Protocol](https://modelcontextprotocol.io/) so **Claude Code**, **OpenClaw**, **Cursor**, and other MCP clients can call Pulse tools (`pulse_events_for_day`, `pulse_discovery`, `pulse_insights`, `pulse_correct`, …) against the same database and vault as this install.

**Send your coding agent** — copy everything in the box into the agent chat (it will fetch the doc and do the work):

```text
Read https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html and follow every step to install Pulse (pulse-agent), ensure pulse.toml exists, and register pulse-mcp in my MCP settings for this machine.
```

## Vault (Obsidian)

Output lives under **`vault_path`** / **`PULSE_VAULT_PATH`**. Common patterns: dedicated folder as its own vault; subfolder inside an existing vault; or symlink (mobile/sync may not handle symlinks well). First vault use may create **`README.md`** (structure + reserved headings) and **`Meta/AGENTS.md`**.

Discovery writes **patterns** under `02-Insights/patterns/`; older installs may still have legacy `01-Daily/` files from removed daily digests.

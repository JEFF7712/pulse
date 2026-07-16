<div align="center">
  <img src="docs/assets/readme-pulse-banner.png" alt="PULSE" width="780" style="max-width: 100%;" />
</div>

<p align="center">The self-hosted personal-data context layer for your agent.</p>

<p align="center">
  <a href="https://pypi.org/project/pulse-agent/"><img alt="PyPI" src="https://img.shields.io/pypi/v/pulse-agent?style=flat-square&label=pypi" /></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" /></a>
  <a href="https://github.com/JEFF7712/pulse/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/JEFF7712/pulse/ci.yml?style=flat-square&amp;branch=main" /></a>
  <a href="https://modelcontextprotocol.io/"><img alt="MCP" src="https://img.shields.io/badge/MCP-compatible-808080?style=flat-square" /></a>
</p>

<p align="center">
  <a href="https://pulseagent.dev">pulseagent.dev</a>
  ·
  <a href="https://pulseagent.dev/docs/">Documentation</a>
  ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">Ingest curated sources into a local store and Obsidian-style vault, then expose them over <strong>MCP</strong> so <strong>your</strong> agent does the reasoning — all <strong>self-hosted</strong>. Pulse does not call an LLM itself.</p>

<p align="center">Pulse is still experimental and in active testing, so expect some rough edges and occasional changes. It is best suited for early adopters who are comfortable self-hosting.</p>

---
### Install

**Install Script**

```bash
curl -fsSL https://pulseagent.dev/install.sh | bash
```

**Pip**
```bash
pipx install pulse-agent   # or: uv tool install pulse-agent
```

**Docker**

```bash
docker pull ghcr.io/jeff7712/pulse:3.1.0

docker run -d --name pulse -p 8000:8000 \
  -v pulse-config:/config -v pulse-data:/data \
  ghcr.io/jeff7712/pulse:3.1.0 pulse onboard
```

From a clone: `docker build -t pulse -f Dockerfile .` or `docker compose up --build -d`.
**[Quickstart — Docker](https://pulseagent.dev/docs/self-hosting/quickstart.html#docker)** for more details.

Defaults (native install): config under `~/.config/pulse`, data under `~/.local/share/pulse` (override with `PULSE_CONFIG_DIR`). Next: **`pulse configure`** → **`pulse init`** → **`pulse run`** — see **[Quickstart](https://pulseagent.dev/docs/self-hosting/quickstart.html)**.

### Documentation

Documentation lives under `docs/` in this repository, or **[pulseagent.dev/docs](https://pulseagent.dev/docs/)**.
**Paths and environment:** Standalone app, CLI commands, and the MCP server use `PULSE_DATABASE_PATH`. That variable selects the SQLite event store; use `PULSE_VAULT_PATH` for vault markdown. Override the config directory with `PULSE_CONFIG_DIR` (default finds `.config/pulse.toml` under `~/.config/pulse`). **`pulse` and `pulse-mcp`** read the same variables; day boundaries and scheduling use `PULSE_TIMEZONE` — see the [Operations runbook](https://pulseagent.dev/docs/operations/runbook.html).

Optional: local semantic search (`pulse-agent[semantic]`, `pulse embed`) and scheduled proactive review (`[proactive]`, `pulse review`) — see the [configuration reference](https://pulseagent.dev/docs/reference/configuration.html).

### MCP

Use **`pulse-mcp`** with Claude Code, Cursor, OpenClaw, etc. Setup, client JSON, tools, and resources: **[MCP agent setup](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html)**. Agent skills: [`skills/`](skills/README.md) (`pulse-review`, `pulse-recall`).

Send this to your agent:

```
Read https://raw.githubusercontent.com/JEFF7712/pulse/main/docs/self-hosting/mcp-agent-setup.md and follow every step to install Pulse (pulse-agent), ensure pulse.toml exists, and register pulse-mcp in my MCP settings for this machine.
```

### Develop

```bash
uv sync --group dev && uv run pytest
```

Layout and contributor workflow: **[Contributing](CONTRIBUTING.md)**.

---

<p align="center">
  <a href="https://pulseagent.dev">pulseagent.dev</a>
  |
  <a href="https://pypi.org/project/pulse-agent/">PyPI</a>
  |
  <a href="https://github.com/JEFF7712/pulse">GitHub</a>
</p>

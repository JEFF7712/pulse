<div align="center">
  <img src="docs/assets/readme-pulse-banner.png" alt="PULSE" width="780" style="max-width: 100%;" />
</div>

<p align="center">The self-hosted personal intelligence agent.</p>

<p align="center">
  <a href="https://pypi.org/project/pulse-agent/"><img alt="PyPI" src="https://img.shields.io/pypi/v/pulse-agent?style=flat-square&label=pypi" /></a>
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" /></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green?style=flat-square" /></a>
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

<p align="center">Ingest your digital life, discover patterns, write an Obsidian-style vault, get <strong>push</strong> insights — all <strong>self-hosted</strong>.</p>

---
### Install

```bash
curl -fsSL https://pulseagent.dev/install.sh | bash
```

```bash
pipx install pulse-agent   # or: uv tool install pulse-agent
```

Defaults: config under `~/.config/pulse`, data under `~/.local/share/pulse` (override with `PULSE_CONFIG_DIR`). Next: **`pulse configure`** → **`pulse init`** → **`pulse run`** — see **[Quickstart](https://pulseagent.dev/docs/self-hosting/quickstart.html)**.

### Documentation

Documentation: **[pulseagent.dev/docs](https://pulseagent.dev/docs/)** — [Quickstart](https://pulseagent.dev/docs/self-hosting/quickstart.html), [Configuration](https://pulseagent.dev/docs/reference/configuration.html), [Operations runbook](https://pulseagent.dev/docs/operations/runbook.html), and [Connectors](https://pulseagent.dev/docs/connectors/).

**Paths and environment:** Standalone app, CLI commands, and the MCP server use `PULSE_DATABASE_PATH`. That variable selects the SQLite event store; use `PULSE_VAULT_PATH` for vault markdown. Override the config directory with `PULSE_CONFIG_DIR` (default finds `.config/pulse.toml` under `~/.config/pulse`). **`pulse` and `pulse-mcp`** read the same variables; discovery **day boundaries** and related scheduling semantics are documented in the [Operations runbook](https://pulseagent.dev/docs/operations/runbook.html) (`PULSE_TIMEZONE`).

### MCP

Use **`pulse-mcp`** with Claude Code, Cursor, OpenClaw, etc. Setup, client JSON, tools, and resources: **[MCP agent setup](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html)**.

### Develop

```bash
uv sync --group dev && uv run pytest
```

Layout and companion app: **[Contributing](CONTRIBUTING.md)**.

---

<p align="center">
  <a href="https://pulseagent.dev">pulseagent.dev</a>
  |
  <a href="https://pypi.org/project/pulse-agent/">PyPI</a>
  |
  <a href="https://github.com/JEFF7712/pulse">GitHub</a>
</p>

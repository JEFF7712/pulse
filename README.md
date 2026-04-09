<p align="center">
  <img src="docs/assets/pulse-ascii-banner.png" alt="PULSE" width="780" />
</p>

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
  <a href="docs/index.md">Documentation</a>
  ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

Ingest your digital life, discover patterns, write an Obsidian-style vault, get **push** insights — all **self-hosted**. Full overview, architecture, MCP JSON, env reference, and ops: **[Documentation](docs/index.md)**.

---

### Install

```bash
curl -fsSL https://pulseagent.dev/install.sh | bash
```

```bash
pipx install pulse-agent   # or: uv tool install pulse-agent
```

Defaults: config under `~/.config/pulse`, data under `~/.local/share/pulse` (override with `PULSE_CONFIG_DIR`). Next: **`pulse configure`** → **`pulse init`** → **`pulse run`** — see **[Quickstart](docs/self-hosting/quickstart.md)**.

### MCP

Use **`pulse-mcp`** with Claude Code, Cursor, OpenClaw, etc. Setup, client JSON, tools, and resources: **[MCP agent setup](docs/self-hosting/mcp-agent-setup.md)**.

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

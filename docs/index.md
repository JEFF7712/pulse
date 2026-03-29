# Pulse Docs

## What is Pulse?

Pulse is a self-hosted personal intelligence agent. It connects the tools you already use, looks for patterns across them, and keeps the resulting memory in infrastructure you control.

## Quick Start

If you want the shortest path from a fresh install to a working deployment, use this order:

1. Read [Run Pulse](./self-hosting/quickstart.md) to install `pulse-agent`, configure the stack, and boot the app.
2. Use [Configure Pulse](./reference/configuration.md) to review `PULSE_...` variables, `pulse.toml`, and connector settings.
3. Keep [Operate Pulse](./operations/runbook.md) nearby for health checks, recovery steps, and day-two operations.
4. Open [Connect Data Sources](./connectors/index.md) when you are ready to expand ingestion across your accounts and devices.

## Self-Hosting Docs

Use these guides when you want the shortest route from a fresh checkout to a working Pulse deployment.

<div class="pulse-home-grid">
  <a class="pulse-home-card" href="./self-hosting/quickstart.html">
    <p class="pulse-home-kicker">Setup</p>
    <h3>Self-Hosting Quickstart</h3>
    <p>Install dependencies, configure the stack, and boot the app.</p>
    <span class="pulse-home-cta">Open quickstart</span>
  </a>
  <a class="pulse-home-card" href="./reference/configuration.html">
    <p class="pulse-home-kicker">Config</p>
    <h3>Configuration Reference</h3>
    <p>Environment variables, <code>pulse.toml</code>, and connector settings.</p>
    <span class="pulse-home-cta">Open reference</span>
  </a>
  <a class="pulse-home-card" href="./operations/runbook.html">
    <p class="pulse-home-kicker">Operations</p>
    <h3>Operations Runbook</h3>
    <p>Health checks, recovery, and day-two operations.</p>
    <span class="pulse-home-cta">Open runbook</span>
  </a>
  <a class="pulse-home-card" href="./connectors/index.html">
    <p class="pulse-home-kicker">Data</p>
    <h3>Connectors</h3>
    <p>Expand ingestion across accounts and devices.</p>
    <span class="pulse-home-cta">Open connectors</span>
  </a>
</div>

## Agent integration (MCP)

To run Pulse as a [Model Context Protocol](https://modelcontextprotocol.io/) server for tools like Claude Code, use `pulse-mcp` (installed alongside `pulse` when you install `pulse-agent`) or `python -m pulse.mcp.server`. Tool names, resources, and a copy-paste JSON config live in the repository **README** under *Use as an MCP server*. [Configuration Reference](./reference/configuration.md) explains `PULSE_DATABASE_PATH`, `PULSE_VAULT_PATH`, and how the shared config path works when you run the app and MCP server together.

# Pulse Docs

## What is Pulse?

Self-hosted agent: connects your tools, finds patterns, stores results in infrastructure you control.

## Quick Start

1. [Run Pulse](./self-hosting/quickstart.md) — install, configure, start the app  
2. [Configure Pulse](./reference/configuration.md) — env vars, `pulse.toml`, connectors  
3. [Operate Pulse](./operations/runbook.md) — health, recovery, day-two ops  
4. [Connect Data Sources](./connectors/index.md) — per-connector setup  

<div class="pulse-home-grid">
  <a class="pulse-home-card" href="./self-hosting/quickstart.html">
    <p class="pulse-home-kicker">Setup</p>
    <h3>Self-Hosting Quickstart</h3>
    <p>Install, configure, and run Pulse.</p>
    <span class="pulse-home-cta">Open quickstart</span>
  </a>
  <a class="pulse-home-card" href="./reference/configuration.html">
    <p class="pulse-home-kicker">Config</p>
    <h3>Configuration Reference</h3>
    <p>Environment variables, <code>pulse.toml</code>, connectors.</p>
    <span class="pulse-home-cta">Open reference</span>
  </a>
  <a class="pulse-home-card" href="./operations/runbook.html">
    <p class="pulse-home-kicker">Operations</p>
    <h3>Operations Runbook</h3>
    <p>Health checks, webhooks, scheduler, recovery.</p>
    <span class="pulse-home-cta">Open runbook</span>
  </a>
  <a class="pulse-home-card" href="./connectors/index.html">
    <p class="pulse-home-kicker">Data</p>
    <h3>Connectors</h3>
    <p>OAuth, tokens, and what each source pulls.</p>
    <span class="pulse-home-cta">Open connectors</span>
  </a>
</div>

## MCP

For [Model Context Protocol](https://modelcontextprotocol.io/) integration with **Claude Code**, **OpenClaw**, Cursor, and other MCP clients, run `pulse-mcp` or `python -m pulse.mcp.server`. The server requires a **`pulse.toml` on disk** at the resolved config path (same rules as the standalone app); copy-paste MCP JSON and the tool list are in the repo **README** (*Use as an MCP server*). Paths and env overrides match the app — see [Configuration Reference](./reference/configuration.md).

To have an **AI agent install and wire MCP for you**, use the one-liner in [Self-Hosting Quickstart → Connect Pulse to your coding agent (MCP)](./self-hosting/quickstart.md#mcp-agent-paste) and the agent-facing checklist at [MCP agent setup](./self-hosting/mcp-agent-setup.md).

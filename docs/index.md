# Pulse Docs

## What is Pulse?

Self-hosted **MCP-first personal-data context layer**: ingests curated sources (email, calendar, purchases, health, media, and more) into a local store and **Obsidian-compatible markdown vault**, and exposes them to **your own agent** over MCP. Pulse does not call an LLM itself — your agent does the reasoning. Optional **notifications** (Telegram, ntfy, webhooks, email, and others) cover operational alerts. **No app to open, no daily check-ins** — your data stays on your stack.

## How it works

```
Data Sources (Gmail, Calendar, GitHub, Oura, …)
        ↓
  Event Store (SQLite)
        ↓
  Vault (Obsidian-compatible Markdown)
        ↓
  Your agent via MCP (Claude Code, Cursor, …)
```

1. **Connectors** pull from your accounts into timestamped events.
2. **Event store** persists everything locally.
3. **Vault** is human-readable markdown.
4. **MCP** exposes the same store to your coding agent for reasoning.

**Two ways to run:** standalone service (`pulse run`, FastAPI + scheduler) or **[MCP](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html)** so coding agents use the same store and tools.

## Design principles

1. **MCP-first** — your agent reasons; Pulse holds the context.
2. **Low-friction integration** — connect sources quickly.
3. **Transparency** — vault markdown you can read and diff.
4. **Extensible** — connectors and notification channels.
5. **Self-hosted** — your hardware, your data.

## Quick Start

1. [Run Pulse](https://pulseagent.dev/docs/self-hosting/quickstart.html) — install, configure, start the app  
2. [Configure Pulse](https://pulseagent.dev/docs/reference/configuration.html) — env vars, `pulse.toml`, connectors  
3. [Operate Pulse](https://pulseagent.dev/docs/operations/runbook.html) — health, recovery, day-two ops  
4. [Connect Data Sources](https://pulseagent.dev/docs/connectors/) — per-connector setup  

<div class="pulse-home-grid">
  <a class="pulse-home-card" href="https://pulseagent.dev/docs/self-hosting/quickstart.html">
    <p class="pulse-home-kicker">Setup</p>
    <h3>Self-Hosting Quickstart</h3>
    <p>Install, configure, and run Pulse.</p>
    <span class="pulse-home-cta">Open quickstart</span>
  </a>
  <a class="pulse-home-card" href="https://pulseagent.dev/docs/reference/configuration.html">
    <p class="pulse-home-kicker">Config</p>
    <h3>Configuration Reference</h3>
    <p>Environment variables, <code>pulse.toml</code>, connectors.</p>
    <span class="pulse-home-cta">Open reference</span>
  </a>
  <a class="pulse-home-card" href="https://pulseagent.dev/docs/operations/runbook.html">
    <p class="pulse-home-kicker">Operations</p>
    <h3>Operations Runbook</h3>
    <p>Health checks, webhooks, scheduler, recovery.</p>
    <span class="pulse-home-cta">Open runbook</span>
  </a>
  <a class="pulse-home-card" href="https://pulseagent.dev/docs/connectors/">
    <p class="pulse-home-kicker">Data</p>
    <h3>Connectors</h3>
    <p>OAuth, tokens, and what each source pulls.</p>
    <span class="pulse-home-cta">Open connectors</span>
  </a>
</div>

## MCP

For [Model Context Protocol](https://modelcontextprotocol.io/) integration with **Claude Code**, **OpenClaw**, Cursor, and other MCP clients, run `pulse-mcp` or `python -m pulse.mcp.server`. The server requires a **`pulse.toml` on disk** at the resolved config path (same rules as the standalone app). **JSON examples, tools, and resources:** [MCP agent setup](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html). **Paths and env:** [Configuration reference](https://pulseagent.dev/docs/reference/configuration.html) (*App, CLI, MCP*, *Runtime notes*).

To have an **AI agent install and wire MCP for you**, use the one-liner in [Self-Hosting Quickstart → Connect Pulse to your coding agent (MCP)](https://pulseagent.dev/docs/self-hosting/quickstart.html#mcp-agent-paste) and follow [MCP agent setup](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html).

## Contributing and releases

- **[Contributing](https://github.com/JEFF7712/pulse/blob/main/CONTRIBUTING.md)** — dev environment, tests, project layout.
- **[Releases and versioning](https://pulseagent.dev/docs/operations/releases.html)** — semver, tags, PyPI.

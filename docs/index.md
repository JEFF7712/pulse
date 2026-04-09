# Pulse Docs

## What is Pulse?

Self-hosted **personal intelligence agent**: ingests email, calendar, purchases, health, media, and more; runs analysis and discovery; writes an **Obsidian-compatible markdown vault**; pushes insights via **notifications** (Telegram, ntfy, webhooks, email, and others). **No app to open, no daily check-ins** — your data stays on your stack.

## How it works

```
Data Sources (Gmail, Calendar, Notion, Linear, Oura, …)
        ↓
  Event Store (SQLite)
        ↓
  Analysis Engine ──→ Vault (Obsidian-compatible Markdown)
        ↓
  Notifications (Telegram, ntfy, …)
        ↕
  User Corrections
```

1. **Connectors** pull from your accounts into timestamped events.
2. **Event store** persists everything locally.
3. **Analysis engine** runs discovery and writes patterns.
4. **Vault** is human-readable markdown.
5. **Notifications** deliver insights; **corrections** close the loop.

**Two ways to run:** standalone service (`pulse run`, FastAPI + scheduler) or **[MCP](https://pulseagent.dev/docs/self-hosting/mcp-agent-setup.html)** so coding agents use the same store and tools.

## Design principles

1. **Push-first** — insights come to you.
2. **Low-friction integration** — connect sources quickly.
3. **Transparency** — vault markdown you can read and diff.
4. **Extensible** — connectors, LLMs, notification channels.
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

**Mobile companion (optional):** Flutter app under [`companion_app/`](https://github.com/JEFF7712/pulse/blob/main/companion_app/README.md); enable **`[connectors.companion]`** on the server.

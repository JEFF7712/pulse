# Pulse Docs

This file is the source of truth for the deployed docs page at `/docs/`. The VitePress site under `site/docs-app/` includes these markdown files verbatim.

## What is Pulse?

Pulse is a self-hosted personal intelligence agent. It connects the tools you already use, looks for patterns across them, and keeps the resulting memory in infrastructure you control.

## Quick Start

If you want the shortest path from a fresh checkout to a working deployment, use this order:

1. Read [Run Pulse](./self-hosting/quickstart.md) to install dependencies, configure the stack, and boot the app.
2. Use [Configure Pulse](./reference/configuration.md) to review `PULSE_...` variables, `pulse.toml`, and connector settings.
3. Keep [Operate Pulse](./operations/runbook.md) nearby for health checks, recovery steps, and day-two operations.
4. Open [Connect Data Sources](./connectors/index.md) when you are ready to expand ingestion across your accounts and devices.

## Self-Hosting Docs

Use these guides when you want the shortest route from a fresh checkout to a working Pulse deployment.

- [Self-Hosting Quickstart](./self-hosting/quickstart.md)
- [Configuration Reference](./reference/configuration.md)
- [Operations Runbook](./operations/runbook.md)
- [Connectors Index](./connectors/index.md)

## Agent integration (MCP)

To run Pulse as a [Model Context Protocol](https://modelcontextprotocol.io/) server for tools like Claude Code, use `python -m pulse.mcp.server` with `PULSE_DB_PATH` and `PULSE_VAULT_PATH`. Tool names, resources, and a copy-paste JSON config live in the repository **README** under *Use as an MCP server*. [Configuration Reference](./reference/configuration.md) explains how `PULSE_DB_PATH` relates to `PULSE_DATABASE_PATH` when you run the app and MCP against one database.

# MCP agent setup (for AI assistants)

This page is written for **coding agents** (Claude Code, OpenClaw, Cursor, and similar). A human may paste a link or path to this file and ask you to execute it. Your job is to install Pulse, ensure configuration exists on disk, and register the **pulse-mcp** Model Context Protocol server in their environment.

## Outcomes

When you are done:

1. **`pulse-agent`** is installed so `pulse` and `pulse-mcp` are available (prefer **`pipx install pulse-agent`**; alternatives: `uv tool install pulse-agent`, `pip install pulse-agent`, or `uv sync` from a git clone with `uv run pulse-mcp`).
2. A real **`pulse.toml`** exists where Pulse resolves config (default **`~/.config/pulse/pulse.toml`**, or repo-root **`pulse.toml`**, or the path set by **`PULSE_CONFIG_FILE`** / **`PULSE_CONFIG_DIR`**). The MCP server calls `load_config(require_files=True)` and **will not start** without this file.
3. **`database_path`** and **`vault_path`** in that file (or **`PULSE_DATABASE_PATH`** / **`PULSE_VAULT_PATH`** in the MCP process environment) point at the SQLite DB and markdown vault the user intends to use.
4. The user’s MCP client has a server entry that runs **`pulse-mcp`** (or `uv run python -m pulse.mcp.server` from a clone) with **`PULSE_CONFIG_FILE`** or **`PULSE_CONFIG_DIR`** set if the client’s working directory would not otherwise find `pulse.toml`.

## Steps

### 1. Install

- Prefer isolated install: `pipx install pulse-agent`.
- Verify: `pulse --help` and ensure `pulse-mcp` is on `PATH` (same prefix as `pulse`).

### 2. Create configuration

- If no `pulse.toml` exists, run **`pulse configure`** with the user (TTY) or guide them through non-interactive env + file creation using **`pulse.toml.example`** in the repository as a template.
- OAuth and API keys for connectors are optional for MCP to **start**; they are required for live connector data. Connector setup uses **Configure → Connectors** in `pulse configure` (browser flows on localhost ports such as **8888** as documented in the self-hosting quickstart).
- Optional combined path: **`pulse onboard`** / **`pulse onboard --strict`** with profile flags such as **`-f ./my-profile.txt`** or **`--profile-text`** when the user wants onboarding plus auth in one go.

### 3. Initialize (recommended)

- Run **`pulse init`** once so the vault layout and profile scaffolding exist, unless the user explicitly wants MCP-only without that step.

### 4. Register MCP in the client

Use the same JSON shapes as the repository **README** section *Use as an MCP server*.

- **`pulse-mcp` on PATH** — minimal pattern:

```json
{
  "mcpServers": {
    "pulse": {
      "command": "pulse-mcp",
      "env": {
        "PULSE_CONFIG_FILE": "/absolute/path/to/pulse.toml"
      }
    }
  }
}
```

- Adjust **`PULSE_CONFIG_FILE`** to the actual resolved path. Omit it only when default config resolution already finds their `pulse.toml`.
- If the client supports a working directory for the server process and the user keeps **`pulse.toml`** at a repository root, set **`cwd`** to that repo; otherwise prefer **`PULSE_CONFIG_FILE`**.
- From a **git clone** with **uv**: `"command": "uv"`, `"args": ["run", "python", "-m", "pulse.mcp.server"]`, plus **`env`** with **`PULSE_DATABASE_PATH`** / **`PULSE_VAULT_PATH`** if not only in TOML.

Exact client file locations differ (Claude Code, OpenClaw, Cursor, etc.); open the user’s MCP settings file for their product and merge this block without duplicating the `mcpServers` key.

### 5. Verify

- Run **`pulse status`** to confirm DB path and event counts.
- Confirm the MCP server process starts without `PulseConfigNotFoundError` or missing-module errors.
- Optional: invoke tool **`pulse_connector_status`** or resource **`pulse://events/today`** from the client if it exposes them.

## Reference

- Human-oriented walkthrough: [Self-Hosting Quickstart](./quickstart.md).
- Config, env, digest/corrections behavior: [Configuration Reference](../reference/configuration.md) (see *App, CLI, MCP* and *Runtime notes*).
- Tool and resource list: repository **README** (*Use as an MCP server*).

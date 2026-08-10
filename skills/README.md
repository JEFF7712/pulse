# Pulse agent skills

Pulse is MCP-first: it exposes your data over the `pulse-mcp` server and your own agent does the
reasoning. These skills teach an agent to use that surface well. They are the difference between an
agent that dumps raw events and one that surfaces something worth knowing.

| Skill | Use for |
| --- | --- |
| [`pulse-review`](pulse-review/SKILL.md) | Finding genuinely new patterns and recording them, recording nothing when nothing is new. Also what the optional discovery pass invokes. |
| [`pulse-recall`](pulse-recall/SKILL.md) | Answering ad-hoc "what did I / when did I / how often" questions from your history. |

Each `SKILL.md` is portable Markdown with simple frontmatter (`name`, `description`); the body is
plain instructions any capable agent can follow.

## Install

**Claude Code** - copy or symlink into a skills directory it loads:

```bash
# user-level (all projects)
ln -s "$(pwd)/skills/pulse-review" ~/.claude/skills/pulse-review
ln -s "$(pwd)/skills/pulse-recall" ~/.claude/skills/pulse-recall
```

Then invoke with `/pulse-review` or `/pulse-recall` once the `pulse-mcp` server is registered
(see [MCP agent setup](../docs/self-hosting/mcp-agent-setup.md)).

**Other agents (Cursor, etc.)** - these are just instructions. Paste the relevant `SKILL.md` body
into your agent's rules/context, or point the agent at the file, alongside the `pulse-mcp` server
connection.

## Prerequisite

The `pulse-mcp` server must be registered with your agent and pointed at your Pulse database and
vault. See [docs/self-hosting/mcp-agent-setup.md](../docs/self-hosting/mcp-agent-setup.md).

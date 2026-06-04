# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is the **OpenCell Tools Marketplace** — a Claude Code plugin registry that provides an integrated developer workflow for OpenCell projects. It contains no buildable source code; everything is defined in JSON configs and Markdown files.

## Repository Structure

```
.claude-plugin/marketplace.json   # Central plugin registry (all plugins listed here)
plugins/<name>/
  .claude-plugin/plugin.json      # Plugin metadata, MCP server config, agent/skill refs
  skills/<skill-name>/SKILL.md    # Skill (slash command) definition
  agents/<agent-name>.md          # Sub-agent system prompt and config
```

## Plugin Types

There are three kinds of plugins:

1. **Skills** — Slash commands users invoke directly (`/cache-jira`, `/oc-commit`, `/oc-pr`, `/oc-fix-bug`, `/oc-create-ui`, `/oc-review-pr`). Defined in `SKILL.md` files with YAML frontmatter.
2. **Sub-agents** — Specialized AI personas spawned by skills or the main agent (`frontend-engineer`, `frontend-reviewer`, `frontend-designer`, `cypress-expert`, `oc-backend-tools:pr-reviewer`). Defined in `.md` files under `agents/` with YAML frontmatter (`name`, `color`, `model`).
3. **MCP Servers** — External service integrations configured in `plugin.json` under `mcpServers` (Bitbucket, Figma, Playwright, Opencell, SonarQube, PostgreSQL).

## How to Add a New Plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with name, description, and optional `mcpServers`, `skills`, or `agents` fields.
2. Add the plugin entry to `.claude-plugin/marketplace.json` in the `plugins` array.
3. If it has skills, create `plugins/<name>/skills/<skill>/SKILL.md`.
4. If it has agents, create `plugins/<name>/agents/<agent>.md`.

## How to Remove a Plugin

1. Delete the entry from `.claude-plugin/marketplace.json`.
2. Delete the `plugins/<name>/` directory.

## Key Workflow: Jira-Driven Development

The skills chain together into a standard workflow:

```
/cache-jira TICKET  →  /oc-fix-bug TICKET  →  [fix code]  →  /oc-commit TICKET  →  /oc-pr TICKET  →  /oc-review-pr TICKET
```

- `/cache-jira` stores ticket data in `.claude/cache/jira-tickets.json` (1-hour TTL). Other commands read from this cache.
- `/oc-fix-bug` transitions the Jira ticket to "In Progress" and creates a `fix/TICKET` branch.
- `/oc-commit` runs the appropriate reviewer agent before committing.
- `/oc-pr` squashes commits and creates a PR (auto-detects Bitbucket vs GitHub).
- `/oc-review-pr` selects the reviewer agent based on repository: `oc-frontend-reviewer` for opencell-portal, `oc-backend-tools:pr-reviewer` for opencell-core.

## MCP Servers Requiring Environment Variables

| MCP | Required Variables |
|-----|--------------------|
| Bitbucket | `BITBUCKET_EMAIL`, `BITBUCKET_ACCESS_TOKEN` |
| Opencell | `OPENCELL_BASE_URL`, `OPENCELL_API_VERSION`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` |
| SonarQube | `SONARQUBE_URL`, `SONARQUBE_TOKEN` |
| PostgreSQL | `DATABASE_URI` |
| Figma | Uses HTTP MCP (auth handled by Figma) |
| Playwright | No env vars needed |

## Conventions

- All sub-agents use `model: sonnet` in their frontmatter.
- Agent markdown files contain the full system prompt — editing the `.md` changes agent behavior directly.
- Skills reference agents and MCP tools by their registered names (e.g., `oc-frontend-reviewer:frontend-reviewer`).
- The Opencell MCP server runs from a local path (`C:\Users\moham\workspace\ai\opencell-mcp-server\dist\index.js`); the PostgreSQL MCP runs via Docker.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is the **OpenCell Tools Marketplace** — a Claude Code plugin registry that provides an integrated developer workflow for OpenCell projects. It contains no buildable source code; everything is defined in JSON configs and Markdown files.

## Repository Structure

```
.claude-plugin/marketplace.json     # Central plugin registry (all plugins listed here)
plugins/<factory>/<name>/           # factory ∈ frontend, backend, qa, archi, func, common, mcp
  .claude-plugin/plugin.json        # Plugin metadata, MCP server config, agent/skill refs
  skills/<skill-name>/SKILL.md      # Skill (slash command) definition
  agents/<agent-name>.md            # Sub-agent system prompt and config
  commands/<command-name>.md        # Slash command (used by oc-be-tools)
```

Plugins are grouped into **factory folders**. `qa/` and `func/` are reserved placeholders
(README only) with no plugins yet. `mcp/` holds the external-service connectors.

## Naming Convention

All plugins, skills, agents, and commands follow `oc-<abbr>-<name>`:

| Factory | Abbr | Example |
|---------|------|---------|
| frontend | `fe` | `oc-fe-engineer`, `/oc-fe-create-ui` |
| backend | `be` | `oc-be-pr-reviewer`, `/oc-be-implement` |
| qa | `qa` | *(reserved)* |
| archi | `ar` | `/oc-ar-tech-design` |
| func | `fn` | *(reserved)* |
| common | *(none)* | `/oc-commit`, `/oc-cache-jira` |
| mcp | *(none)* | `/oc-figma`, `/oc-opencell` |

Rule of thumb: a plugin's directory name equals its plugin name, which equals its primary
skill/agent name (e.g. plugin `oc-fe-engineer` holds agent `oc-fe-engineer`).

## Plugin Types

There are three kinds of plugins:

1. **Skills & commands** — Slash commands users invoke directly: `/oc-cache-jira`, `/oc-commit`, `/oc-pull-request`, `/oc-review-pr`, `/oc-fe-fix-bug`, `/oc-fe-fix-pr`, `/oc-fe-create-ui`, `/oc-fe-write-tests`, `/oc-fe-create-e2e-test`, `/oc-ar-tech-design`, `/oc-be-implement`, `/oc-be-review`, the backend guide skills (`/oc-be-api-guide`, `/oc-be-db-guide`, `/oc-be-entity-guide`, `/oc-be-service-guide`), and the MCP skills (`/oc-figma`, `/oc-bitbucket`, `/oc-playwright`, `/oc-opencell`). Defined in `SKILL.md` files (or `commands/*.md` for `oc-be-tools`).
2. **Sub-agents** — Specialized AI personas spawned by skills or the main agent: `oc-fe-engineer`, `oc-fe-reviewer`, `oc-fe-designer`, `oc-fe-test-writer`, `oc-fe-cypress-expert`, `oc-fe-e2e-expert`, and the backend agents `oc-be-entity-builder`, `oc-be-service-builder`, `oc-be-api-builder`, `oc-be-test-generator`, `oc-be-postman-generator`, `oc-be-pr-reviewer`. Defined in `.md` files under `agents/` with YAML frontmatter (`name`, `color`, `model`).
3. **MCP Servers** — External service integrations configured in `plugin.json` under `mcpServers` (Bitbucket, Figma, Playwright, Opencell, SonarQube, PostgreSQL), all under `plugins/mcp/`.

## How to Add a New Plugin

1. Pick the factory folder (`frontend`/`backend`/`qa`/`archi`/`func`/`common`/`mcp`) and a name on the `oc-<abbr>-<name>` convention.
2. Create `plugins/<factory>/<name>/.claude-plugin/plugin.json` with name, description, and optional `mcpServers`, `skills`, or `agents` fields.
3. Add the plugin entry to `.claude-plugin/marketplace.json` in the `plugins` array with `"source": "./plugins/<factory>/<name>"`.
4. If it has skills, create `plugins/<factory>/<name>/skills/<skill>/SKILL.md` (skill directory name = skill name).
5. If it has agents, create `plugins/<factory>/<name>/agents/<agent>.md` (filename = agent `name`).

## How to Remove a Plugin

1. Delete the entry from `.claude-plugin/marketplace.json`.
2. Delete the `plugins/<factory>/<name>/` directory.

## Key Workflow: Jira-Driven Development

The skills chain together into a standard workflow:

```
/oc-cache-jira TICKET  →  /oc-fe-fix-bug TICKET  →  [fix code]  →  [write tests]  →  /oc-commit TICKET  →  /oc-pull-request TICKET  →  /oc-review-pr TICKET  →  /oc-fe-fix-pr PR-ID
```

- `/oc-cache-jira` stores ticket data in `.claude/cache/jira-tickets.json` (1-hour TTL). Other commands read from this cache.
- `/oc-fe-fix-bug` transitions the Jira ticket to "In Progress" and creates a `fix/TICKET` branch, then writes Vitest tests on the fix via the `oc-fe-test-writer` agent as its final step (before review in `/oc-commit`).
- `/oc-commit` runs the appropriate reviewer agent before committing.
- `/oc-pull-request` squashes commits and creates a PR (auto-detects Bitbucket vs GitHub).
- `/oc-review-pr` selects the reviewer agent based on repository: `oc-fe-reviewer` for opencell-portal, `oc-be-tools:oc-be-pr-reviewer` for opencell-core.
- `/oc-fe-fix-pr` closes the review loop: given a PR id (or a Jira ticket whose PR is found on Bitbucket), it reads the PR's **unresolved** Bitbucket comments, checks out the PR's own source branch, fixes each remark via the `oc-fe-engineer` agent, writes Vitest tests via `oc-fe-test-writer`, commits and pushes to the PR branch, then replies to and resolves each addressed comment.
- `/oc-fe-write-tests` invokes the `oc-fe-test-writer` agent directly to write Vitest tests for changed code (git diff vs a base branch) or for specific files passed as arguments — usable outside the Jira flow. `/oc-fe-create-ui` also runs this agent as its final development step before review.
- `/oc-be-implement` orchestrates a full backend ticket across the `oc-be-*` builder agents; `/oc-be-review` reviews backend changes via `oc-be-pr-reviewer`.

## MCP Servers Requiring Environment Variables

All MCP plugins live under `plugins/mcp/`.

| MCP | Required Variables |
|-----|--------------------|
| Bitbucket | `BITBUCKET_EMAIL`, `BITBUCKET_ACCESS_TOKEN` |
| Opencell | `OPENCELL_BASE_URL`, `OPENCELL_API_VERSION`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` |
| SonarQube | `SONARQUBE_URL`, `SONARQUBE_TOKEN` |
| PostgreSQL | `DATABASE_URI` |
| Figma | Uses HTTP MCP (auth handled by Figma) |
| Playwright | No env vars needed |

## Conventions

- Backend sub-agents use `model: claude-sonnet-4-5`; all other sub-agents use `model: sonnet`.
- Agent markdown files contain the full system prompt — editing the `.md` changes agent behavior directly.
- Skills reference agents and MCP tools by their registered names (e.g., `oc-fe-reviewer:oc-fe-reviewer`, `oc-be-tools:oc-be-pr-reviewer`).
- The PostgreSQL MCP runs via Docker; the Opencell MCP runs via `npx` from a GitHub source.

## Name Migration (old → new)

| Old | New |
|-----|-----|
| `/cache-jira` | `/oc-cache-jira` |
| `/oc-pr` | `/oc-pull-request` |
| `/oc-create-ui` | `/oc-fe-create-ui` |
| `/oc-fix-bug` | `/oc-fe-fix-bug` |
| `/oc-write-tests` | `/oc-fe-write-tests` |
| `/oc-create-e2e-test` | `/oc-fe-create-e2e-test` |
| `/implementBackend` | `/oc-be-implement` |
| `/reviewBackend` | `/oc-be-review` |
| `/figma-design` | `/oc-figma` |
| `/bitbucket-pr` | `/oc-bitbucket` |
| `/browser-automation` | `/oc-playwright` |
| `/opencell` | `/oc-opencell` |
| `/opencell-tech-design` | `/oc-ar-tech-design` |
| agent `frontend-engineer` | `oc-fe-engineer` |
| agent `frontend-reviewer` | `oc-fe-reviewer` |
| agent `frontend-designer` | `oc-fe-designer` |
| agent `frontend-test-writer` | `oc-fe-test-writer` |
| agent `cypress-expert` | `oc-fe-cypress-expert` |
| agent `playwright-e2e-expert` | `oc-fe-e2e-expert` |
| agent `entity-builder` / `service-builder` / `api-builder` / `test-generator` / `postman-generator` / `pr-reviewer` | `oc-be-entity-builder` / `oc-be-service-builder` / `oc-be-api-builder` / `oc-be-test-generator` / `oc-be-postman-generator` / `oc-be-pr-reviewer` |
| plugins `oc-frontend-*`, `oc-backend-tools`, `oc-archi-tools` | `oc-fe-*`, `oc-be-tools`, `oc-ar-tools` |

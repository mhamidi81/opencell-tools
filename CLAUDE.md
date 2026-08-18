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

1. **Skills & commands** — Slash commands users invoke directly: `/oc-cache-jira`, `/oc-commit`, `/oc-pull-request`, `/oc-review-pr`, `/oc-fe-fix-bug`, `/oc-fe-fix-pr`, `/oc-fe-create-ui`, `/oc-fe-write-tests`, `/oc-fe-create-e2e-test`, `/oc-fe-calculate-ai-use`, `/oc-ar-tech-design`, `/oc-be-implement`, `/oc-be-review`, the backend guide skills (`/oc-be-api-guide`, `/oc-be-db-guide`, `/oc-be-entity-guide`, `/oc-be-service-guide`), and the MCP skills (`/oc-figma`, `/oc-playwright`, `/oc-opencell`). Defined in `SKILL.md` files (or `commands/*.md` for `oc-be-tools`).
2. **Sub-agents** — Specialized AI personas spawned by skills or the main agent: `oc-fe-engineer`, `oc-fe-reviewer`, `oc-fe-designer`, `oc-fe-test-writer`, `oc-fe-cypress-expert`, `oc-fe-e2e-expert`, and the backend agents `oc-be-entity-builder`, `oc-be-service-builder`, `oc-be-api-builder`, `oc-be-test-generator`, `oc-be-postman-generator`, `oc-be-pr-reviewer`. Defined in `.md` files under `agents/` with YAML frontmatter (`name`, `color`, `model`).
3. **MCP Servers** — External service integrations configured in `plugin.json` under `mcpServers` (Figma, Playwright, Opencell, SonarQube, PostgreSQL), all under `plugins/mcp/`. **Atlassian is not one of them** — Jira/Confluence come from the official `atlassian` plugin in Anthropic's `claude-plugins-official` marketplace, which this repo does not vendor.

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
/oc-cache-jira TICKET  →  /oc-fe-fix-bug TICKET  →  [fix code]  →  [write tests]  →  /oc-commit TICKET  →  /oc-pull-request TICKET (+ auto /oc-fe-calculate-ai-use)  →  /oc-review-pr TICKET  →  /oc-fe-fix-pr PR-ID
```

- `/oc-cache-jira` stores ticket data in `.claude/cache/jira-tickets.json` (1-hour TTL). Other commands read from this cache.
- `/oc-fe-fix-bug` transitions the Jira ticket to "In Progress" and creates a `fix/TICKET` branch, writes Vitest tests on the fix via the `oc-fe-test-writer` agent (before review in `/oc-commit`), then appends `ai_Dev_Front` to the Jira AI field (`customfield_10613`).
- `/oc-commit` runs the appropriate reviewer agent before committing.
- `/oc-pull-request` squashes commits and creates a PR (auto-detects Bitbucket vs GitHub). On **opencell-portal only**, its final step then invokes `/oc-fe-calculate-ai-use --commit HEAD --if-not-recorded` — the squash is what makes `HEAD` the whole ticket's diff, which is the scope that command measures. The step is skipped on every other repository (**including opencell-core** — backend AI-usage recording stays a manual `/oc-be-tools:oc-be-calculate-ai-use` run) and is non-fatal: the PR is already created, so a failure is a warning, never a retry.
- `/oc-review-pr` selects the reviewer agent based on repository: `oc-fe-reviewer` for opencell-portal, `oc-be-tools:oc-be-pr-reviewer` for opencell-core. It reads the ticket **live from Jira** (it deliberately does not use the `/oc-cache-jira` cache). When the ticket has several PRs (one per target branch), it reviews **exactly one** — the PR targeting `dev` wins; if none targets `dev` and there are several, it asks rather than guessing. For frontend reviews the report **opens with the number of Vitest test cases the PR adds** — counted from the diff (added `it(`/`test(` lines in `*.spec.ts(x)`/`*.test.ts(x)`, Cypress/E2E specs excluded, `it.each` counted once, never executed) so it stays visible at the head of the Bitbucket comment. For frontend (opencell-portal) reviews it then, automatically and without asking: posts the full report as a comment on the selected PR, appends `ai_code_review_Front` to the Jira AI field (`customfield_10613`), and sets the PR status **from the review score** — **8-10 left open, 6-7 marked Draft, 1-5 declined** (`POST …/decline`). A status change only happens on an `OPEN` PR, and a decline is withheld if the review comment failed to post, so a PR is never closed without a stated reason (declining is reversible — the author can reopen). Marking a PR draft is undocumented in the Bitbucket REST spec, so the skill verifies the `draft` flag afterwards and falls back to telling the user to use the PR action menu; it also re-sends the existing `reviewers` on the `PUT`, because omitted fields can be reset.
- `/oc-fe-fix-pr` closes the review loop: given a PR id (or a Jira ticket whose PR is found on Bitbucket), it reads the PR's **unresolved** Bitbucket comments, checks out the PR's own source branch, fixes each remark via the `oc-fe-engineer` agent, writes Vitest tests via `oc-fe-test-writer`, commits and pushes to the PR branch, appends `ai_Dev_Front` to the Jira AI field (`customfield_10613`), then replies to and resolves each addressed comment.
- `/oc-fe-write-tests` invokes the `oc-fe-test-writer` agent directly to write Vitest tests for changed code (git diff vs a base branch) or for specific files passed as arguments — usable outside the Jira flow; when the current branch maps to a ticket, it appends `ai_test_front_dev` to the Jira AI field (`customfield_10613`). `/oc-fe-create-ui` also runs this agent as its final development step before review, then appends `ai_Dev_Front` to the Jira AI field (`customfield_10613`).
- `/oc-be-implement` orchestrates a full backend ticket across the `oc-be-*` builder agents; `/oc-be-review` reviews backend changes via `oc-be-pr-reviewer`.
- `/oc-fe-calculate-ai-use` measures AI contribution/retention on the last commit (or working tree) of **opencell-portal** and records it on the ticket. It runs **automatically as the last step of `/oc-pull-request`** (and remains usable on its own): a human comment, the `ai_Dev_Front` / `ai_test_front_dev` tags on `customfield_10613`, and a machine-readable record in the AI-metrics field (`customfield_10745`). It is the frontend twin of `/oc-be-tools:oc-be-calculate-ai-use` and **must keep the shared parts identical** — see the AI-usage measurement convention below. Two rules make the automatic invocation safe, and both matter to any future caller: `--if-not-recorded` **exits silently** when the ticket already holds a record for that exact commit sha (`addCommentToJiraIssue` is append-only — only `customfield_10745` is an upsert — so a re-run would otherwise post a second comment), and `--run` resolves the AI-stats directory by **`[TICKET-NUMBER]-*` prefix**, not "newest directory", so a developer who switched tickets in one checkout cannot have the other ticket's sub-agent manifests attributed here.

### AI-usage measurement (cross-team)

Both `/oc-be-calculate-ai-use` and `/oc-fe-calculate-ai-use` read four sources: sub-agent **manifests**, sub-agent **first-pass snapshots**, the session **transcript**, and **file-history**. The first two only exist because the orchestrating skills and sub-agents write them — **a sub-agent's `Write`/`Edit` calls never appear in the main session transcript and are lost when the sub-agent finishes**, so without them sub-agent work is undercounted and its retention is unmeasurable. The contract:

- The orchestrator (`/oc-fe-create-ui`, `/oc-fe-fix-bug`, `/oc-fe-fix-pr`, `/oc-fe-write-tests`, `/oc-fe-create-e2e-test`, `/oc-be-implement`) creates `.claude/cache/ai-stats/{TICKET}-{yyyymmdd-HHMMSS}/` and passes a manifest path to every sub-agent it dispatches.
- Each code-writing sub-agent writes `{RUN_ID}/{phase}.json` (its file list) and then `{RUN_ID}/snapshots/{phase}.diff` (`git diff HEAD` of exactly those files) as its **final actions** — the snapshot must be captured **before** any review fixes, or retention reads a meaningless 100%. The instructions live in each agent's own `.md` so they work when the agent is invoked directly; the orchestrator verifies and falls back.
- At plan/approach approval the orchestrator writes `{RUN_ID}/_planning.json`, which is how analysis effort that produces no code gets credited.
- These directories are git-ignored in both repos.

**Identical across backend, frontend and QA:** the field (`customfield_10745`), the schema (`opencell.ai-usage/v1`), and the record key layout (`<domain>/<accountId>/<name>`, upserted by the `<domain>/<accountId>/` prefix, latest-only). Only the `domain` value, the `cat` sub-keys, the artifact-count keys and the tag names differ. One reporting tool reads every team's data from that one field — do not diverge from the shared parts.

## MCP Servers Requiring Environment Variables

All MCP plugins bundled here live under `plugins/mcp/`.

| MCP | Required Variables |
|-----|--------------------|
| Opencell | `OPENCELL_BASE_URL`, `OPENCELL_API_VERSION`, `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` |
| SonarQube | `SONARQUBE_URL`, `SONARQUBE_TOKEN` |
| PostgreSQL | `DATABASE_URI` |
| Figma | Uses HTTP MCP (auth handled by Figma) |
| Playwright | No env vars needed |
| Atlassian (not bundled) | None — `atlassian@claude-plugins-official`, OAuth via `/mcp` |

## Atlassian and Bitbucket Access

Jira and Bitbucket are reached two different ways, and the split is not optional:

| System | How | Credential |
|--------|-----|------------|
| **Jira / Confluence** | Official Atlassian Rovo MCP — `/plugin install atlassian@claude-plugins-official`, then `/mcp` to sign in (OAuth 2.1, endpoint `https://mcp.atlassian.com/v1/mcp/authv2`) | none |
| **Bitbucket** (PRs, diffs, comments) | Bitbucket REST API with `curl` | `BITBUCKET_EMAIL` + `BITBUCKET_ACCESS_TOKEN` |

**Why Bitbucket is not on MCP:** the Rovo server exposes its Bitbucket tools **only under API-token
auth**, never over the OAuth flow the official plugin uses — an OAuth Rovo connection surfaces
Jira/Confluence/Compass tools and no `bitbucket*` tools at all. So every Bitbucket operation in
`/oc-pull-request`, `/oc-review-pr` and `/oc-fe-fix-pr` uses REST `curl`.

**Bitbucket REST auth — use Basic, not Bearer.** `BITBUCKET_ACCESS_TOKEN` holds an **Atlassian API
token** (`ATATT…`, from https://id.atlassian.com/manage/api-tokens), which authenticates as
`email:token` over **Basic** auth. Both variables are required:

```bash
curl -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" …     # correct
curl -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" …  # 401 for ATATT… tokens
```

Bitbucket repository/workspace **Access Tokens** are the other valid credential type and *do* use
`Bearer` with no email — but the tokens configured for this workspace are Atlassian API tokens, so the
skills are written with `-u`. App Passwords were removed 2026-07-28.

**The diff endpoints redirect.** `GET …/pullrequests/[PR-ID]/diff` **and** `…/diffstat` answer **302**
to a signed URL; call both with `curl -sL`. Without `-L` the body is empty and a reviewer agent
silently reviews nothing. The `pullrequests` search, `…/[PR-ID]` and `…/comments` endpoints return
`200` directly.

Skills name Jira tools **bare** (`getJiraIssue`, `editJiraIssue`, `transitionJiraIssue`,
`atlassianUserInfo`) so they resolve against whichever Atlassian MCP is registered — the official
plugin, or the claude.ai connector (`mcp__…Atlassian_Rovo__<tool>`).

## Conventions

- Backend sub-agents use `model: claude-sonnet-4-5`; all other sub-agents use `model: sonnet`.
- **Frontend Vitest files are named `*.test.ts(x)`, never `*.spec.ts(x)`.** opencell-portal's `vitest.config.ts` sets `include: ['src/**/*.test.{ts,tsx,js,jsx}']`, so a `.spec.*` file is silently never collected — it looks like coverage that does not exist. `oc-fe-test-writer`, `oc-fe-reviewer`, `/oc-fe-create-ui`, `/oc-fe-fix-bug`, `/oc-fe-fix-pr` and `/oc-fe-write-tests` all state this; keep them consistent. Playwright is the exception — its e2e specs stay `tests/e2e/**/*.spec.ts`, which is Playwright's own convention and does run. Counters (`/oc-review-pr`, `/oc-fe-calculate-ai-use`) deliberately accept **both** extensions so a stray legacy file is still measured.
- Agent markdown files contain the full system prompt — editing the `.md` changes agent behavior directly.
- Skills reference agents and MCP tools by their registered names (e.g., `oc-fe-reviewer:oc-fe-reviewer`, `oc-be-tools:oc-be-pr-reviewer`).
- The PostgreSQL MCP runs via Docker; the Opencell MCP runs via `npx` from a GitHub source; the Figma MCP is a remote HTTP server.
- **`customfield_10613` (the Jira "AI" field) is a multi-value labels field — never overwrite it.** Several commands tag the same field (`ai_code_review_Front`, `ai_code_review_back`, `ai_Dev_back`, `ai_test_back_dev`, `ai_Dev_Front`, `ai_test_front_dev`, …) and they must coexist. Any skill writing it must `getJiraIssue` the current array first, then `editJiraIssue` with **all** existing values plus its own — never a bare string, never a single-select `{ "value": … }` object, never a one-element array, all of which replace the whole field. If the read fails, skip the write rather than clobbering it. Verified live: the field returns e.g. `["ai_Dev_Front","ai_test_front_dev"]`. **Reuse the exact casing already in use** — `ai_Dev_Front` (capital D and F) and `ai_test_front_dev` (all lowercase); a differently-cased variant creates a second, useless label.
- **`customfield_10745` (the Jira "AI metrics" field) holds one JSON document per ticket, shared by every team.** It must be a **multi-line** Text Field (a single-line field caps at 255 chars) and may use the **rich-text (ADF) renderer**, which rejects a raw string — write a plain string first and fall back to a minimal ADF `codeBlock` wrapper, and accept either form on read. Never replace the document: read it, delete the caller's own `<domain>/<accountId>/` key, re-add the caller's record, and keep every other key (other developers, other domains).
- Never add an Atlassian/Bitbucket MCP server to this repo. Jira comes from the official `atlassian` plugin (see **Atlassian and Bitbucket Access**), and Bitbucket has no usable MCP path — keep it on REST `curl`.

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
| `/bitbucket-pr` | `/oc-bitbucket` → **removed** (no replacement skill; see **Atlassian and Bitbucket Access**) |
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
| plugin `oc-bitbucket-mcp` (third-party `@aashari/mcp-server-atlassian-bitbucket`, tools `bb_get`/`bb_post`, vars `BITBUCKET_EMAIL` + `BITBUCKET_ACCESS_TOKEN`) | **deleted** — Jira via `atlassian@claude-plugins-official` (OAuth, no vars); Bitbucket via REST `curl` with `BITBUCKET_ACCESS_TOKEN` only |

# Marketplace Factory Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the 20 marketplace plugins into factory folders (`frontend`, `backend`, `archi`, `common`, `mcp`; `qa` + `func` reserved) and rename every plugin/skill/agent/command onto the unified `oc-<abbr>-<name>` pattern, with a clean break (all references + CLAUDE.md updated).

**Architecture:** This is a **mechanical refactor of config/markdown files** — there is no code to compile or test. Each task therefore follows **change → verify (grep / path / JSON) → commit** instead of TDD. Plugins are discovered by Claude Code through `marketplace.json` `source` paths, so nested folders are safe. The spec this implements is `docs/superpowers/specs/2026-06-17-marketplace-factory-reorg-design.md`.

**Tech Stack:** Git (`git mv` preserves history), JSON, Markdown, PowerShell (Windows; `git` commands are shell-agnostic). Edits use the Edit tool; identifier swaps use `replace_all` **in the listed order** (ordering matters where one token is a substring of another — e.g. replace the `plugin:agent` colon-token *before* the bare token).

**Branch:** `refactor/marketplace-factory-reorg` (already checked out; the spec is already committed here).

---

## Conventions used in every task

- **Plugin directory** is renamed to its **new plugin name** and moved under its factory: `plugins/<factory>/<new-plugin-name>/`.
- **Agent** = `name:` frontmatter + the `agents/<x>.md` filename (rename both).
- **Skill** = `name:` frontmatter + the `skills/<x>/` directory name (rename both — Claude Code identifies skills by directory).
- **Command** = the `commands/<x>.md` filename (rename the file).
- In **`plugin.json`** the old token is the **old plugin name** (e.g. `oc-cypress-expert`); in **agent/skill files** the old token is the **bare identifier** (e.g. `cypress-expert`). Do not blanket-replace the bare token inside `plugin.json` or you get a double prefix.

---

## Task 0: Scaffold factory folders and reserved placeholders

**Files:**
- Create: `plugins/frontend/`, `plugins/backend/`, `plugins/qa/`, `plugins/archi/`, `plugins/func/`, `plugins/common/`, `plugins/mcp/`
- Create: `plugins/func/README.md`, `plugins/qa/README.md`

- [ ] **Step 1: Create the factory directories**

Run (PowerShell):
```powershell
New-Item -ItemType Directory -Force plugins/frontend, plugins/backend, plugins/qa, plugins/archi, plugins/func, plugins/common, plugins/mcp | Out-Null
```

- [ ] **Step 2: Create the two reserved-placeholder READMEs**

Create `plugins/func/README.md`:
```markdown
# func factory (reserved)

Reserved for **functional-design** plugins. No plugins yet.

When populated, follow the marketplace naming convention: plugin/skill/agent names use
the `oc-fn-<name>` pattern and live under `plugins/func/`.
```

Create `plugins/qa/README.md`:
```markdown
# qa factory (reserved)

Reserved for a future dedicated **quality-assurance** factory. No plugins yet.

Front-end testing tools (`oc-fe-cypress-expert`, `oc-fe-create-e2e-test`) currently live
in the `frontend` factory. When this factory is populated, use the `oc-qa-<name>` pattern.
```

- [ ] **Step 3: Commit**

```powershell
git add plugins/func/README.md plugins/qa/README.md
git commit -m "Scaffold factory folders with func/qa reserved placeholders"
```

---

## Task 1: Frontend factory (8 plugins)

**Files (directory moves):**
- `plugins/frontend-engineer` → `plugins/frontend/oc-fe-engineer`
- `plugins/frontend-reviewer` → `plugins/frontend/oc-fe-reviewer`
- `plugins/frontend-designer` → `plugins/frontend/oc-fe-designer`
- `plugins/frontend-test-writer` → `plugins/frontend/oc-fe-test-writer`
- `plugins/oc-create-ui` → `plugins/frontend/oc-fe-create-ui`
- `plugins/oc-fix-bug` → `plugins/frontend/oc-fe-fix-bug`
- `plugins/cypress-expert` → `plugins/frontend/oc-fe-cypress-expert`
- `plugins/oc-create-e2e-test` → `plugins/frontend/oc-fe-create-e2e-test`

- [ ] **Step 1: Move the 8 plugin directories**

```powershell
git mv plugins/frontend-engineer      plugins/frontend/oc-fe-engineer
git mv plugins/frontend-reviewer      plugins/frontend/oc-fe-reviewer
git mv plugins/frontend-designer      plugins/frontend/oc-fe-designer
git mv plugins/frontend-test-writer   plugins/frontend/oc-fe-test-writer
git mv plugins/oc-create-ui           plugins/frontend/oc-fe-create-ui
git mv plugins/oc-fix-bug             plugins/frontend/oc-fe-fix-bug
git mv plugins/cypress-expert         plugins/frontend/oc-fe-cypress-expert
git mv plugins/oc-create-e2e-test     plugins/frontend/oc-fe-create-e2e-test
```

- [ ] **Step 2: Rename agent files and skill directories**

```powershell
git mv plugins/frontend/oc-fe-engineer/agents/frontend-engineer.md            plugins/frontend/oc-fe-engineer/agents/oc-fe-engineer.md
git mv plugins/frontend/oc-fe-reviewer/agents/frontend-reviewer.md            plugins/frontend/oc-fe-reviewer/agents/oc-fe-reviewer.md
git mv plugins/frontend/oc-fe-designer/agents/frontend-designer.md            plugins/frontend/oc-fe-designer/agents/oc-fe-designer.md
git mv plugins/frontend/oc-fe-test-writer/agents/frontend-test-writer.md      plugins/frontend/oc-fe-test-writer/agents/oc-fe-test-writer.md
git mv plugins/frontend/oc-fe-test-writer/skills/oc-write-tests               plugins/frontend/oc-fe-test-writer/skills/oc-fe-write-tests
git mv plugins/frontend/oc-fe-create-ui/skills/oc-create-ui                   plugins/frontend/oc-fe-create-ui/skills/oc-fe-create-ui
git mv plugins/frontend/oc-fe-fix-bug/skills/oc-fix-bug                       plugins/frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug
git mv plugins/frontend/oc-fe-cypress-expert/agents/cypress-expert.md         plugins/frontend/oc-fe-cypress-expert/agents/oc-fe-cypress-expert.md
git mv plugins/frontend/oc-fe-create-e2e-test/agents/playwright-e2e-expert.md plugins/frontend/oc-fe-create-e2e-test/agents/oc-fe-e2e-expert.md
git mv plugins/frontend/oc-fe-create-e2e-test/skills/oc-create-e2e-test       plugins/frontend/oc-fe-create-e2e-test/skills/oc-fe-create-e2e-test
```

- [ ] **Step 3: Edit `plugin.json` names + descriptions**

- `plugins/frontend/oc-fe-engineer/.claude-plugin/plugin.json`: `"oc-frontend-engineer"` → `"oc-fe-engineer"`
- `plugins/frontend/oc-fe-reviewer/.claude-plugin/plugin.json`: `"oc-frontend-reviewer"` → `"oc-fe-reviewer"`
- `plugins/frontend/oc-fe-designer/.claude-plugin/plugin.json`: `"oc-frontend-designer"` → `"oc-fe-designer"`
- `plugins/frontend/oc-fe-test-writer/.claude-plugin/plugin.json`: `"oc-frontend-test-writer"` → `"oc-fe-test-writer"`, and in its description `/oc-write-tests` → `/oc-fe-write-tests`
- `plugins/frontend/oc-fe-create-ui/.claude-plugin/plugin.json`: `"oc-create-ui"` → `"oc-fe-create-ui"`, and in its description `frontend-engineer` → `oc-fe-engineer`
- `plugins/frontend/oc-fe-fix-bug/.claude-plugin/plugin.json`: `"oc-fix-bug"` → `"oc-fe-fix-bug"`
- `plugins/frontend/oc-fe-cypress-expert/.claude-plugin/plugin.json`: `"oc-cypress-expert"` → `"oc-fe-cypress-expert"`
- `plugins/frontend/oc-fe-create-e2e-test/.claude-plugin/plugin.json`: `"oc-create-e2e-test"` → `"oc-fe-create-e2e-test"`, and in its description `playwright-e2e-expert` → `oc-fe-e2e-expert`

- [ ] **Step 4: Edit the pure-agent files (frontmatter + example prose)**

Use `replace_all` on each file (each file currently contains only the bare old identifier — never the new prefixed form — so a single global pass is safe even where the new name embeds the old, e.g. `cypress-expert` → `oc-fe-cypress-expert`):
- `plugins/frontend/oc-fe-engineer/agents/oc-fe-engineer.md`: `frontend-engineer` → `oc-fe-engineer`
- `plugins/frontend/oc-fe-reviewer/agents/oc-fe-reviewer.md`: `frontend-reviewer` → `oc-fe-reviewer`
- `plugins/frontend/oc-fe-designer/agents/oc-fe-designer.md`: `frontend-designer` → `oc-fe-designer`
- `plugins/frontend/oc-fe-cypress-expert/agents/oc-fe-cypress-expert.md`: `cypress-expert` → `oc-fe-cypress-expert`
- `plugins/frontend/oc-fe-create-e2e-test/agents/oc-fe-e2e-expert.md`: `playwright-e2e-expert` → `oc-fe-e2e-expert`

- [ ] **Step 5: Edit `oc-fe-test-writer/agents/oc-fe-test-writer.md`**

Apply in order with `replace_all`:
1. `frontend-test-writer` → `oc-fe-test-writer`
2. `frontend-reviewer` → `oc-fe-reviewer`  *(line ~62 prose reference to the reviewer)*

- [ ] **Step 6: Edit `oc-fe-test-writer/skills/oc-fe-write-tests/SKILL.md`**

Apply in this exact order (`replace_all`):
1. `oc-frontend-test-writer:frontend-test-writer` → `oc-fe-test-writer:oc-fe-test-writer`
2. `frontend-test-writer` → `oc-fe-test-writer`
3. `oc-write-tests` → `oc-fe-write-tests`  *(fixes `name:` and the `/oc-write-tests` usage examples)*

- [ ] **Step 7: Edit `oc-fe-create-ui/skills/oc-fe-create-ui/SKILL.md`**

Apply in this exact order (`replace_all`):
1. `oc-frontend-test-writer:frontend-test-writer` → `oc-fe-test-writer:oc-fe-test-writer`
2. `subagent_type: frontend-engineer` → `subagent_type: oc-fe-engineer:oc-fe-engineer`
3. `frontend-engineer` → `oc-fe-engineer`
4. `frontend-test-writer` → `oc-fe-test-writer`
5. `oc-create-ui` → `oc-fe-create-ui`  *(fixes `name:` and `/oc-create-ui` usage examples)*

*(Leave `/oc-commit` references unchanged — that skill keeps its name.)*

- [ ] **Step 8: Edit `oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md`**

Apply in this exact order (`replace_all`):
1. `oc-frontend-test-writer:frontend-test-writer` → `oc-fe-test-writer:oc-fe-test-writer`
2. `frontend-test-writer` → `oc-fe-test-writer`
3. `oc-fix-bug` → `oc-fe-fix-bug`  *(fixes `name:` and `/oc-fix-bug` usage examples)*

*(Leave `/oc-commit` references unchanged.)*

- [ ] **Step 9: Edit `oc-fe-create-e2e-test/skills/oc-fe-create-e2e-test/SKILL.md`**

Apply in this exact order (`replace_all`):
1. `oc-create-e2e-test:playwright-e2e-expert` → `oc-fe-create-e2e-test:oc-fe-e2e-expert`
2. `playwright-e2e-expert` → `oc-fe-e2e-expert`
3. `oc-create-e2e-test` → `oc-fe-create-e2e-test`  *(fixes `name:` and `/oc-create-e2e-test` usage examples)*

- [ ] **Step 10: Verify the frontend factory is internally consistent**

```powershell
git grep -nE "frontend-engineer|frontend-reviewer|frontend-designer|frontend-test-writer|playwright-e2e-expert|oc-frontend-|oc-create-ui|oc-fix-bug|oc-write-tests|oc-create-e2e-test" -- plugins/frontend
```
Expected: **no output** (the only `cypress-expert` substring left is inside `oc-fe-cypress-expert`, which is correct). Also confirm each new `name:`:
```powershell
git grep -n "^name:" -- plugins/frontend
```
Expected names: `oc-fe-engineer`, `oc-fe-reviewer`, `oc-fe-designer`, `oc-fe-test-writer`, `oc-fe-cypress-expert`, `oc-fe-e2e-expert`, `oc-fe-write-tests`, `oc-fe-create-ui`, `oc-fe-fix-bug`, `oc-fe-create-e2e-test`.

- [ ] **Step 11: Commit**

```powershell
git add -A plugins/frontend
git commit -m "Move + rename frontend factory plugins to oc-fe-* under plugins/frontend"
```

---

## Task 2: Backend factory (`oc-be-tools`)

**Files:**
- `plugins/oc-backend-tools` → `plugins/backend/oc-be-tools`
- Agents → `agents/oc-be-<x>.md`; commands → `commands/oc-be-<x>.md`; skills → `skills/oc-be-<x>-guide/`

- [ ] **Step 1: Move the plugin directory**

```powershell
git mv plugins/oc-backend-tools plugins/backend/oc-be-tools
```

- [ ] **Step 2: Rename agent files, command files, and skill directories**

```powershell
git mv plugins/backend/oc-be-tools/agents/entity-builder.md     plugins/backend/oc-be-tools/agents/oc-be-entity-builder.md
git mv plugins/backend/oc-be-tools/agents/service-builder.md    plugins/backend/oc-be-tools/agents/oc-be-service-builder.md
git mv plugins/backend/oc-be-tools/agents/api-builder.md        plugins/backend/oc-be-tools/agents/oc-be-api-builder.md
git mv plugins/backend/oc-be-tools/agents/test-generator.md     plugins/backend/oc-be-tools/agents/oc-be-test-generator.md
git mv plugins/backend/oc-be-tools/agents/postman-generator.md  plugins/backend/oc-be-tools/agents/oc-be-postman-generator.md
git mv plugins/backend/oc-be-tools/agents/pr-reviewer.md        plugins/backend/oc-be-tools/agents/oc-be-pr-reviewer.md
git mv plugins/backend/oc-be-tools/commands/implementBackend.md plugins/backend/oc-be-tools/commands/oc-be-implement.md
git mv plugins/backend/oc-be-tools/commands/reviewBackend.md    plugins/backend/oc-be-tools/commands/oc-be-review.md
git mv plugins/backend/oc-be-tools/skills/api-guide      plugins/backend/oc-be-tools/skills/oc-be-api-guide
git mv plugins/backend/oc-be-tools/skills/db-guide       plugins/backend/oc-be-tools/skills/oc-be-db-guide
git mv plugins/backend/oc-be-tools/skills/entity-guide   plugins/backend/oc-be-tools/skills/oc-be-entity-guide
git mv plugins/backend/oc-be-tools/skills/service-guide  plugins/backend/oc-be-tools/skills/oc-be-service-guide
```

*(`guidelines/` is **not** renamed — it is referenced via `${CLAUDE_PLUGIN_ROOT}/guidelines/` and moves with the plugin.)*

- [ ] **Step 3: Edit `plugin.json`**

`plugins/backend/oc-be-tools/.claude-plugin/plugin.json`, apply (`replace_all`):
1. `"oc-backend-tools"` → `"oc-be-tools"`  *(the `name`)*
2. `/implementBackend` → `/oc-be-implement`
3. `/reviewBackend` → `/oc-be-review`

- [ ] **Step 4: Edit agent frontmatter (`name:` lines)**

Targeted single-line edits (the `name:` is the only occurrence in each file):
- `agents/oc-be-entity-builder.md`: `name: entity-builder` → `name: oc-be-entity-builder`
- `agents/oc-be-service-builder.md`: `name: service-builder` → `name: oc-be-service-builder`
- `agents/oc-be-api-builder.md`: `name: api-builder` → `name: oc-be-api-builder`
- `agents/oc-be-test-generator.md`: `name: test-generator` → `name: oc-be-test-generator`
- `agents/oc-be-postman-generator.md`: `name: postman-generator` → `name: oc-be-postman-generator`

- [ ] **Step 5: Edit `agents/oc-be-pr-reviewer.md`**

Apply in order:
1. `replace_all` `/reviewBackend` → `/oc-be-review`  *(prose at ~lines 27, 210)*
2. targeted: `name: pr-reviewer` → `name: oc-be-pr-reviewer`

- [ ] **Step 6: Edit `commands/oc-be-implement.md`**

`replace_all`, each token is distinct:
- `entity-builder` → `oc-be-entity-builder`
- `service-builder` → `oc-be-service-builder`
- `api-builder` → `oc-be-api-builder`
- `test-generator` → `oc-be-test-generator`
- `postman-generator` → `oc-be-postman-generator`

- [ ] **Step 7: Edit `commands/oc-be-review.md`**

Apply in this exact order:
1. `replace_all` `oc-backend-tools:pr-reviewer` → `oc-be-tools:oc-be-pr-reviewer`
2. `replace_all` `oc-backend-tools:reviewBackend` → `oc-be-tools:oc-be-review`
3. targeted (line ~2 description, "using the pr-reviewer agent"): `pr-reviewer agent` → `oc-be-pr-reviewer agent`

*(Do **not** blanket-replace bare `pr-reviewer` here — after step 1 it survives only inside `oc-be-tools:oc-be-pr-reviewer`, which is already correct.)*

- [ ] **Step 8: Verify**

```powershell
git grep -nE "oc-backend-tools|implementBackend|reviewBackend|(^|[^-])entity-builder|service-builder|api-builder|test-generator|postman-generator" -- plugins/backend
```
Expected: **no output**. Then confirm the agent names:
```powershell
git grep -n "^name:" -- plugins/backend/oc-be-tools/agents
```
Expected: `oc-be-entity-builder`, `oc-be-service-builder`, `oc-be-api-builder`, `oc-be-test-generator`, `oc-be-postman-generator`, `oc-be-pr-reviewer`.

- [ ] **Step 9: Commit**

```powershell
git add -A plugins/backend
git commit -m "Move + rename backend tools to oc-be-* under plugins/backend"
```

---

## Task 3: Archi factory (`oc-ar-tools`)

- [ ] **Step 1: Move + rename**

```powershell
git mv plugins/oc-archi-tools plugins/archi/oc-ar-tools
git mv plugins/archi/oc-ar-tools/skills/opencell-tech-design plugins/archi/oc-ar-tools/skills/oc-ar-tech-design
```

- [ ] **Step 2: Edit names**

- `plugins/archi/oc-ar-tools/.claude-plugin/plugin.json`: `"oc-archi-tools"` → `"oc-ar-tools"`
- `plugins/archi/oc-ar-tools/skills/oc-ar-tech-design/SKILL.md`: `name: opencell-tech-design` → `name: oc-ar-tech-design`

- [ ] **Step 3: Verify**

```powershell
git grep -nE "oc-archi-tools|opencell-tech-design" -- plugins/archi
```
Expected: **no output**.

- [ ] **Step 4: Commit**

```powershell
git add -A plugins/archi
git commit -m "Move + rename archi tools to oc-ar-tools under plugins/archi"
```

---

## Task 4: Common factory (4 plugins)

**Files:**
- `plugins/cache-jira` → `plugins/common/oc-cache-jira`
- `plugins/oc-commit` → `plugins/common/oc-commit`
- `plugins/oc-pull-request` → `plugins/common/oc-pull-request`
- `plugins/oc-review-pr` → `plugins/common/oc-review-pr`

- [ ] **Step 1: Move the plugin directories + rename inner skill dirs**

```powershell
git mv plugins/cache-jira      plugins/common/oc-cache-jira
git mv plugins/oc-commit       plugins/common/oc-commit
git mv plugins/oc-pull-request plugins/common/oc-pull-request
git mv plugins/oc-review-pr    plugins/common/oc-review-pr
git mv plugins/common/oc-cache-jira/skills/cache-jira plugins/common/oc-cache-jira/skills/oc-cache-jira
git mv plugins/common/oc-pull-request/skills/oc-pr     plugins/common/oc-pull-request/skills/oc-pull-request
```

*(`oc-commit` and `oc-review-pr` skill dirs already match their final names — no inner rename.)*

- [ ] **Step 2: Edit `oc-cache-jira` skill**

`plugins/common/oc-cache-jira/skills/oc-cache-jira/SKILL.md`:
1. targeted: `name: cache-jira` → `name: oc-cache-jira`
2. `replace_all` `/cache-jira` → `/oc-cache-jira`  *(usage example line ~178)*

*(`plugin.json` `name` is already `oc-cache-jira` — no change.)*

- [ ] **Step 3: Edit `oc-commit` skill**

`plugins/common/oc-commit/skills/oc-commit/SKILL.md` (`replace_all`):
1. `frontend-reviewer` → `oc-fe-reviewer`  *(headings/prose at ~lines 56, 60)*
2. `/cache-jira` → `/oc-cache-jira`  *(line ~45)*

*(Leave `name: oc-commit` and `/oc-commit` example unchanged.)*

- [ ] **Step 4: Edit `oc-pull-request` skill**

`plugins/common/oc-pull-request/skills/oc-pull-request/SKILL.md` (`replace_all`):
1. `/oc-pr` → `/oc-pull-request`  *(usage example line ~291)*
2. `/cache-jira` → `/oc-cache-jira`  *(line ~56)*

*(`name:` is already `oc-pull-request`; `plugin.json` `name` is already `oc-pull-request` — no change.)*

- [ ] **Step 5: Edit `oc-review-pr` skill**

`plugins/common/oc-review-pr/skills/oc-review-pr/SKILL.md` — apply in this exact order (`replace_all`):
1. `oc-frontend-reviewer:frontend-reviewer` → `oc-fe-reviewer:oc-fe-reviewer`
2. `oc-backend-tools:pr-reviewer` → `oc-be-tools:oc-be-pr-reviewer`
3. `oc-frontend-reviewer` → `oc-fe-reviewer`  *(the bare REVIEWER-LABEL at ~lines 48, 464)*
4. `/cache-jira` → `/oc-cache-jira`  *(line ~30)*

Then `plugins/common/oc-review-pr/.claude-plugin/plugin.json` (`replace_all`):
5. `oc-frontend-reviewer` → `oc-fe-reviewer`
6. `oc-backend-tools:pr-reviewer` → `oc-be-tools:oc-be-pr-reviewer`

*(Leave `/oc-review-pr` examples and `name: oc-review-pr` unchanged.)*

- [ ] **Step 6: Verify**

```powershell
git grep -nE "oc-frontend-reviewer|frontend-reviewer|oc-backend-tools|/oc-pr\b|/cache-jira\b|name: cache-jira" -- plugins/common
```
Expected: **no output**. Confirm skill names:
```powershell
git grep -n "^name:" -- plugins/common
```
Expected: `oc-cache-jira`, `oc-commit`, `oc-pull-request`, `oc-review-pr`.

- [ ] **Step 7: Commit**

```powershell
git add -A plugins/common
git commit -m "Move + rename Jira workflow plugins under plugins/common"
```

---

## Task 5: MCP group (6 connectors)

**Files (rename each plugin dir to match its existing `oc-<tool>-mcp` name and move under `mcp/`; rename the single skill dir to `oc-<tool>`):**

- [ ] **Step 1: Move the plugin directories**

```powershell
git mv plugins/figma-mcp      plugins/mcp/oc-figma-mcp
git mv plugins/bitbucket-mcp  plugins/mcp/oc-bitbucket-mcp
git mv plugins/playwright-mcp plugins/mcp/oc-playwright-mcp
git mv plugins/opencell-mcp   plugins/mcp/oc-opencell-mcp
git mv plugins/sonar-mcp      plugins/mcp/oc-sonar-mcp
git mv plugins/oc-postgres-mcp plugins/mcp/oc-postgres-mcp
```

- [ ] **Step 2: Rename the skill directories (the 4 connectors that have a skill)**

```powershell
git mv plugins/mcp/oc-figma-mcp/skills/figma-design          plugins/mcp/oc-figma-mcp/skills/oc-figma
git mv plugins/mcp/oc-bitbucket-mcp/skills/bitbucket-pr      plugins/mcp/oc-bitbucket-mcp/skills/oc-bitbucket
git mv plugins/mcp/oc-playwright-mcp/skills/browser-automation plugins/mcp/oc-playwright-mcp/skills/oc-playwright
git mv plugins/mcp/oc-opencell-mcp/skills/opencell           plugins/mcp/oc-opencell-mcp/skills/oc-opencell
```

- [ ] **Step 3: Edit the 4 skill `name:` lines (targeted single-line edits)**

- `plugins/mcp/oc-figma-mcp/skills/oc-figma/SKILL.md`: `name: figma-design` → `name: oc-figma`
- `plugins/mcp/oc-bitbucket-mcp/skills/oc-bitbucket/SKILL.md`: `name: bitbucket-pr` → `name: oc-bitbucket`
- `plugins/mcp/oc-playwright-mcp/skills/oc-playwright/SKILL.md`: `name: browser-automation` → `name: oc-playwright`
- `plugins/mcp/oc-opencell-mcp/skills/oc-opencell/SKILL.md`: `name: opencell` → `name: oc-opencell`

*(All 6 `plugin.json` `name` fields already follow `oc-<tool>-mcp` — no change. `sonar-mcp` and `oc-postgres-mcp` have no skill.)*

- [ ] **Step 4: Verify**

```powershell
git grep -nE "name: (figma-design|bitbucket-pr|browser-automation|opencell)$" -- plugins/mcp
```
Expected: **no output**. Confirm skill names:
```powershell
git grep -n "^name:" -- plugins/mcp
```
Expected: `oc-figma`, `oc-bitbucket`, `oc-playwright`, `oc-opencell`.

- [ ] **Step 5: Commit**

```powershell
git add -A plugins/mcp
git commit -m "Move MCP connectors under plugins/mcp and rename skills to oc-<tool>"
```

---

## Task 6: Rewrite `marketplace.json`

**Files:**
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Replace the entire file with the updated registry (grouped by factory)**

Overwrite `.claude-plugin/marketplace.json` with exactly:
```json
{
  "name": "opencell-tools",
  "owner": {
    "name": "opencell",
    "email": "mohamed.hamidi@opencellsoft.com"
  },
  "metadata": {
    "description": "A collection of Claude Code plugins that streamline the OpenCell developer workflow — from Jira ticket management and UI scaffolding to automated commits, pull requests, and code review, with built-in integrations for Atlassian, Bitbucket, Figma, and Playwright."
  },
  "plugins": [
    {
      "name": "oc-fe-engineer",
      "source": "./plugins/frontend/oc-fe-engineer",
      "description": "Expert React/TypeScript UI engineer sub-agent for building, refactoring, and architecting frontend components"
    },
    {
      "name": "oc-fe-reviewer",
      "source": "./plugins/frontend/oc-fe-reviewer",
      "description": "Frontend code reviewer sub-agent for validating React/TypeScript code against project standards"
    },
    {
      "name": "oc-fe-designer",
      "source": "./plugins/frontend/oc-fe-designer",
      "description": "Frontend designer sub-agent for translating Figma designs into implementation-ready React/MUI components with design tokens and styling"
    },
    {
      "name": "oc-fe-test-writer",
      "source": "./plugins/frontend/oc-fe-test-writer",
      "description": "Frontend test writer sub-agent and /oc-fe-write-tests command that write Vitest tests for changed React/TypeScript code (or specific files) following OpenCell Portal testing conventions"
    },
    {
      "name": "oc-fe-create-ui",
      "source": "./plugins/frontend/oc-fe-create-ui",
      "description": "Create UI page from JIRA ticket ID using the oc-fe-engineer sub-agent"
    },
    {
      "name": "oc-fe-fix-bug",
      "source": "./plugins/frontend/oc-fe-fix-bug",
      "description": "Fix a bug from a JIRA ticket: update status, create fix branch, and start fixing"
    },
    {
      "name": "oc-fe-cypress-expert",
      "source": "./plugins/frontend/oc-fe-cypress-expert",
      "description": "Cypress testing expert sub-agent for end-to-end testing, test automation, and flaky test resolution"
    },
    {
      "name": "oc-fe-create-e2e-test",
      "source": "./plugins/frontend/oc-fe-create-e2e-test",
      "description": "Create Playwright E2E tests from JIRA ticket requirements using the oc-fe-e2e-expert sub-agent"
    },
    {
      "name": "oc-be-tools",
      "source": "./plugins/backend/oc-be-tools",
      "description": "Backend development toolkit for Opencell Core — agents for building entities, services, APIs, tests, and Postman collections, guideline-loading skills, an implementation orchestrator (/oc-be-implement), and a guideline-based code review command (/oc-be-review)"
    },
    {
      "name": "oc-ar-tools",
      "source": "./plugins/archi/oc-ar-tools",
      "description": "Archi design toolkit for Opencell Core — agents and skills for US analysis and technical design"
    },
    {
      "name": "oc-cache-jira",
      "source": "./plugins/common/oc-cache-jira",
      "description": "Fetch and cache JIRA ticket data locally for use by other OpenCell commands"
    },
    {
      "name": "oc-commit",
      "source": "./plugins/common/oc-commit",
      "description": "Commit changes using JIRA ticket ID and summary from cache with automatic code review"
    },
    {
      "name": "oc-pull-request",
      "source": "./plugins/common/oc-pull-request",
      "description": "Push changes and create a pull request for a JIRA ticket with automatic squash and PR creation"
    },
    {
      "name": "oc-review-pr",
      "source": "./plugins/common/oc-review-pr",
      "description": "Review a pull request linked to a JIRA ticket using the oc-fe-reviewer agent with a detailed report and suggested fixes"
    },
    {
      "name": "oc-figma-mcp",
      "source": "./plugins/mcp/oc-figma-mcp",
      "description": "Connect to Figma MCP server to extract design context, generate code from designs, and retrieve design tokens"
    },
    {
      "name": "oc-bitbucket-mcp",
      "source": "./plugins/mcp/oc-bitbucket-mcp",
      "description": "Connect to Bitbucket MCP server to create pull requests, manage repositories, and review code"
    },
    {
      "name": "oc-playwright-mcp",
      "source": "./plugins/mcp/oc-playwright-mcp",
      "description": "Connect to Playwright MCP server to automate browser interactions, take screenshots, and test web applications"
    },
    {
      "name": "oc-opencell-mcp",
      "source": "./plugins/mcp/oc-opencell-mcp",
      "description": "Connect to the Opencell billing system via MCP to manage invoices, quotes, customers, payments, subscriptions, dunning, and all billing operations"
    },
    {
      "name": "oc-sonar-mcp",
      "source": "./plugins/mcp/oc-sonar-mcp",
      "description": "Connect to SonarQube MCP server to access code quality metrics, issues, and analysis results"
    },
    {
      "name": "oc-postgres-mcp",
      "source": "./plugins/mcp/oc-postgres-mcp",
      "description": "Connect to PostgreSQL via MCP for database health analysis, index tuning, query optimization, and safe SQL execution"
    }
  ]
}
```

- [ ] **Step 2: Validate JSON + confirm every source path resolves**

```powershell
$m = Get-Content .claude-plugin/marketplace.json -Raw | ConvertFrom-Json
foreach ($p in $m.plugins) {
  $pj = Join-Path ($p.source -replace '^\./','') '.claude-plugin/plugin.json'
  if (Test-Path $pj) { Write-Host "OK  $($p.name)" } else { Write-Host "MISSING  $($p.name) -> $pj" }
}
```
Expected: 20 lines, all `OK`. Also confirm the `name` in each `plugin.json` matches the marketplace entry `name` (no mismatches).

- [ ] **Step 3: Commit**

```powershell
git add .claude-plugin/marketplace.json
git commit -m "Update marketplace.json: factory source paths + new plugin names"
```

---

## Task 7: Rewrite `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Overwrite `CLAUDE.md` with the updated content**

Replace the whole file with:
````markdown
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

1. **Skills & commands** — Slash commands users invoke directly: `/oc-cache-jira`, `/oc-commit`, `/oc-pull-request`, `/oc-review-pr`, `/oc-fe-fix-bug`, `/oc-fe-create-ui`, `/oc-fe-write-tests`, `/oc-fe-create-e2e-test`, `/oc-ar-tech-design`, `/oc-be-implement`, `/oc-be-review`, the backend guide skills (`/oc-be-api-guide`, `/oc-be-db-guide`, `/oc-be-entity-guide`, `/oc-be-service-guide`), and the MCP skills (`/oc-figma`, `/oc-bitbucket`, `/oc-playwright`, `/oc-opencell`). Defined in `SKILL.md` files (or `commands/*.md` for `oc-be-tools`).
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
/oc-cache-jira TICKET  →  /oc-fe-fix-bug TICKET  →  [fix code]  →  [write tests]  →  /oc-commit TICKET  →  /oc-pull-request TICKET  →  /oc-review-pr TICKET
```

- `/oc-cache-jira` stores ticket data in `.claude/cache/jira-tickets.json` (1-hour TTL). Other commands read from this cache.
- `/oc-fe-fix-bug` transitions the Jira ticket to "In Progress" and creates a `fix/TICKET` branch, then writes Vitest tests on the fix via the `oc-fe-test-writer` agent as its final step (before review in `/oc-commit`).
- `/oc-commit` runs the appropriate reviewer agent before committing.
- `/oc-pull-request` squashes commits and creates a PR (auto-detects Bitbucket vs GitHub).
- `/oc-review-pr` selects the reviewer agent based on repository: `oc-fe-reviewer` for opencell-portal, `oc-be-tools:oc-be-pr-reviewer` for opencell-core.
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
````

- [ ] **Step 2: Verify no old identifiers survived in CLAUDE.md (outside the migration table's left column)**

```powershell
git grep -nE "oc-frontend-|oc-backend-tools|oc-archi-tools|frontend-engineer|frontend-reviewer|frontend-designer|frontend-test-writer|cypress-expert|playwright-e2e-expert|implementBackend|reviewBackend" -- CLAUDE.md
```
Expected: matches only inside the **Name Migration** table (left column). No occurrences elsewhere.

- [ ] **Step 3: Commit**

```powershell
git add CLAUDE.md
git commit -m "Update CLAUDE.md for factory layout + unified naming, add migration table"
```

---

## Task 8: Final repo-wide verification sweep

**Files:** none changed unless a straggler is found.

- [ ] **Step 1: Unambiguous identifiers must be globally absent (excluding the spec/plan docs)**

```powershell
git grep -nE "oc-frontend-|oc-backend-tools|oc-archi-tools|oc-create-ui|oc-fix-bug|oc-write-tests|oc-create-e2e-test|playwright-e2e-expert|implementBackend|reviewBackend|figma-design|bitbucket-pr|browser-automation" -- ":!docs/superpowers"
```
Expected: **no output**.

- [ ] **Step 2: Substring-risk identifiers must be absent in identifier contexts (excluding docs)**

```powershell
git grep -nE "name: (cypress-expert|cache-jira|opencell|figma-design|bitbucket-pr|browser-automation|frontend-engineer|frontend-reviewer|frontend-designer|frontend-test-writer|playwright-e2e-expert|entity-builder|service-builder|api-builder|test-generator|postman-generator|pr-reviewer|oc-create-ui|oc-fix-bug|oc-write-tests|oc-create-e2e-test|opencell-tech-design)$" -- ":!docs/superpowers"
git grep -n "skills/oc-pr" -- ":!docs/superpowers"
git grep -nE "subagent_type: (frontend-engineer|cypress-expert|playwright-e2e-expert|pr-reviewer)\b" -- ":!docs/superpowers"
```
Expected: **no output** for all three.

- [ ] **Step 3: Confirm directory tree shape**

```powershell
Get-ChildItem -Directory plugins | Select-Object Name
Get-ChildItem -Directory plugins/frontend, plugins/backend, plugins/archi, plugins/common, plugins/mcp | Select-Object Name
```
Expected top-level: `frontend, backend, qa, archi, func, common, mcp` (no leftover plugin dirs directly under `plugins/`). Frontend has 8, backend 1 (`oc-be-tools`), archi 1 (`oc-ar-tools`), common 4, mcp 6; `qa`/`func` contain only `README.md`.

- [ ] **Step 4: Re-validate marketplace source paths (repeat Task 6 Step 2)**

```powershell
$m = Get-Content .claude-plugin/marketplace.json -Raw | ConvertFrom-Json
foreach ($p in $m.plugins) {
  $pj = Join-Path ($p.source -replace '^\./','') '.claude-plugin/plugin.json'
  if (Test-Path $pj) { Write-Host "OK  $($p.name)" } else { Write-Host "MISSING  $($p.name) -> $pj" }
}
```
Expected: 20 × `OK`.

- [ ] **Step 5: Cross-reference resolution check**

For every `subagent_type:` / `plugin:agent` reference in `plugins/`, confirm the target agent `name:` exists:
```powershell
git grep -hoE "\b(oc-[a-z0-9-]+):(oc-[a-z0-9-]+)\b" -- plugins | Sort-Object -Unique
```
Manually confirm each `plugin:agent` pair (e.g. `oc-fe-reviewer:oc-fe-reviewer`, `oc-be-tools:oc-be-pr-reviewer`, `oc-fe-test-writer:oc-fe-test-writer`, `oc-fe-engineer:oc-fe-engineer`, `oc-fe-create-e2e-test:oc-fe-e2e-expert`) matches an existing plugin name + agent `name:`.

- [ ] **Step 6: (Manual) reload the marketplace in Claude Code**

Reload/reinstall the marketplace and confirm all skills and agents enumerate under their new names, and that `/oc-review-pr`, `/oc-fe-create-ui`, `/oc-be-implement` dispatch their agents without "agent not found" errors.

- [ ] **Step 7: Commit any straggler fixes**

If steps 1–5 surfaced anything, fix and:
```powershell
git add -A
git commit -m "Fix straggler references found in final verification sweep"
```

---

## Notes / out of scope

- **`model:` values are not changed** — only CLAUDE.md's description of them is corrected. Backend agents stay `claude-sonnet-4-5`; others stay `sonnet`.
- The pre-existing note that the Opencell MCP source is local is corrected to "GitHub via npx" to match `plugin.json`; no functional MCP config changes.
- `qa/` and `func/` stay empty (README placeholders only).
- The spec and this plan under `docs/superpowers/` intentionally retain old names (history/migration reference) and are excluded from the verification greps.
````

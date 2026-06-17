# Marketplace Factory Reorganization — Design

- **Date:** 2026-06-17
- **Status:** Approved (design); pending spec review
- **Repo:** ccode-marketplace (OpenCell Tools Marketplace)

## 1. Goal & context

The marketplace currently holds 20 plugins flat under `plugins/`, with inconsistent
naming across plugin directories, skill names, agent names, and commands. This work:

1. **Reorganizes plugins into OpenCell "factory" folders** — `frontend`, `backend`,
   `qa`, `archi`, `func`, plus a `common` folder for shared workflow skills and a
   dedicated `mcp` group for connectors.
2. **Unifies all skill/agent/plugin/command names** onto one pattern.

Factory grouping is achieved purely by directory structure plus `source` paths in
`marketplace.json`; Claude Code resolves plugins by following `source`, so nested
folders are safe and change nothing about how plugins load.

## 2. Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Name pattern | **Factory abbreviation in the name** (`oc-<abbr>-<name>`) |
| 2 | Plugin granularity | **Keep plugins separate** — move + rename only; ~20 plugins remain |
| 3 | MCP connectors | **Dedicated `mcp/` group** (sibling to factories) |
| 4 | `fix-bug` placement | **Frontend** (it writes Vitest tests today) |
| 5 | Backward compatibility | **Clean break** — rename, update all refs + CLAUDE.md, document old→new, no aliases |
| 6 | Factory abbreviations | `fe`, `be`, `qa`, `ar`, `fn`; common + mcp use plain `oc-` |
| 7 | MCP skill names | **Tool-only** (`oc-figma`, `oc-bitbucket`, `oc-playwright`, `oc-opencell`) |
| 8 | E2E agent | `oc-fe-e2e-expert` (frontend) |
| 9 | PR skill | unify to `oc-pull-request` (resolves the `oc-pr` dir vs `oc-pull-request` frontmatter mismatch) |
| 10 | Plugin names | also adopt the abbrev convention (e.g. plugin `oc-fe-engineer`) |
| 11 | Testing plugins | `cypress-expert` + `create-e2e-test` → **frontend** (`fe` prefix); `qa/` kept empty/reserved |

## 3. Target directory layout

```
.claude-plugin/marketplace.json
plugins/
  frontend/
    oc-fe-engineer/         oc-fe-reviewer/       oc-fe-designer/
    oc-fe-test-writer/      oc-fe-create-ui/      oc-fe-fix-bug/
    oc-fe-cypress-expert/   oc-fe-create-e2e-test/
  backend/
    oc-be-tools/
  qa/
    README.md            (placeholder — reserved for a future QA factory)
  archi/
    oc-ar-tools/
  func/
    README.md            (placeholder — reserved for functional-design plugins)
  common/
    oc-cache-jira/   oc-commit/   oc-pull-request/   oc-review-pr/
  mcp/
    oc-figma-mcp/   oc-bitbucket-mcp/   oc-playwright-mcp/
    oc-opencell-mcp/   oc-sonar-mcp/   oc-postgres-mcp/
```

## 4. Naming convention

| Group | Pattern | Applies to |
|---|---|---|
| Factory (`frontend`/`backend`/`qa`/`archi`) | `oc-<abbr>-<name>`, abbr ∈ `fe`,`be`,`qa`,`ar` | plugin name, skill names, agent names, command files |
| Common | `oc-<name>` (no abbr) | plugin name, skill names |
| MCP | plugin keeps `oc-<tool>-mcp`; skill = `oc-<tool>` | plugin name, skill name |
| Func | reserved `oc-fn-*` (no plugins yet) | — |

Rule of thumb: **plugin name == its primary skill/agent name** (e.g. plugin
`oc-fe-engineer` holds agent `oc-fe-engineer`). Filenames and skill directory names
are renamed to match the new identifier.

`qa/` and `func/` hold no plugins yet — reserved placeholders, with their `qa`/`fn`
abbreviations held for future use.

## 5. Complete rename map (file-level)

Legend: `dir` = plugin directory move; `name:` = frontmatter `name` field; file/dir
renames shown with `→`.

### 5.1 Frontend → `plugins/frontend/`

| Current dir | New dir | Renames |
|---|---|---|
| `frontend-engineer` | `frontend/oc-fe-engineer` | plugin `oc-frontend-engineer`→`oc-fe-engineer`; `agents/frontend-engineer.md`→`agents/oc-fe-engineer.md` (`name: frontend-engineer`→`oc-fe-engineer`) |
| `frontend-reviewer` | `frontend/oc-fe-reviewer` | plugin `oc-frontend-reviewer`→`oc-fe-reviewer`; `agents/frontend-reviewer.md`→`agents/oc-fe-reviewer.md` (`name`→`oc-fe-reviewer`) |
| `frontend-designer` | `frontend/oc-fe-designer` | plugin `oc-frontend-designer`→`oc-fe-designer`; `agents/frontend-designer.md`→`agents/oc-fe-designer.md` (`name`→`oc-fe-designer`) |
| `frontend-test-writer` | `frontend/oc-fe-test-writer` | plugin `oc-frontend-test-writer`→`oc-fe-test-writer`; `agents/frontend-test-writer.md`→`agents/oc-fe-test-writer.md` (`name`→`oc-fe-test-writer`); `skills/oc-write-tests/`→`skills/oc-fe-write-tests/` (`name`→`oc-fe-write-tests`) |
| `oc-create-ui` | `frontend/oc-fe-create-ui` | plugin `oc-create-ui`→`oc-fe-create-ui`; `skills/oc-create-ui/`→`skills/oc-fe-create-ui/` (`name`→`oc-fe-create-ui`) |
| `oc-fix-bug` | `frontend/oc-fe-fix-bug` | plugin `oc-fix-bug`→`oc-fe-fix-bug`; `skills/oc-fix-bug/`→`skills/oc-fe-fix-bug/` (`name`→`oc-fe-fix-bug`) |
| `cypress-expert` | `frontend/oc-fe-cypress-expert` | plugin `oc-cypress-expert`→`oc-fe-cypress-expert`; `agents/cypress-expert.md`→`agents/oc-fe-cypress-expert.md` (`name`→`oc-fe-cypress-expert`) |
| `oc-create-e2e-test` | `frontend/oc-fe-create-e2e-test` | plugin `oc-create-e2e-test`→`oc-fe-create-e2e-test`; `skills/oc-create-e2e-test/`→`skills/oc-fe-create-e2e-test/` (`name`→`oc-fe-create-e2e-test`); `agents/playwright-e2e-expert.md`→`agents/oc-fe-e2e-expert.md` (`name`→`oc-fe-e2e-expert`) |

### 5.2 Backend → `plugins/backend/`

`oc-backend-tools` → `plugins/backend/oc-be-tools` (plugin `oc-backend-tools`→`oc-be-tools`).

- **Agents** (`agents/<x>.md`→`agents/oc-be-<x>.md`, `name`→`oc-be-<x>`):
  `entity-builder`, `service-builder`, `api-builder`, `test-generator`,
  `postman-generator`, `pr-reviewer`.
- **Skills** (`skills/<x>-guide/`→`skills/oc-be-<x>-guide/`, `name`→`oc-be-<x>-guide`):
  `api-guide`, `db-guide`, `entity-guide`, `service-guide`.
- **Commands** (camelCase → kebab):
  `commands/implementBackend.md`→`commands/oc-be-implement.md`;
  `commands/reviewBackend.md`→`commands/oc-be-review.md`.
- **`guidelines/`** stays as-is (referenced via `${CLAUDE_PLUGIN_ROOT}/guidelines/`).

### 5.3 QA → `plugins/qa/` (reserved — empty)

No plugins. The two testing plugins (`cypress-expert`, `oc-create-e2e-test`) move to
**frontend** (see §5.1). `plugins/qa/README.md` is added as a placeholder, reserved for
a future dedicated QA factory; the `qa` abbreviation is held for that.

### 5.4 Archi → `plugins/archi/`

`oc-archi-tools` → `plugins/archi/oc-ar-tools` (plugin `oc-archi-tools`→`oc-ar-tools`);
`skills/opencell-tech-design/`→`skills/oc-ar-tech-design/` (`name`→`oc-ar-tech-design`).
The `references/` subfolder (`adf-template.md`, `design-examples.md`,
`error-patterns.md`) moves with the skill directory.

### 5.5 Common → `plugins/common/`

| Current dir | New dir | Renames |
|---|---|---|
| `cache-jira` | `common/oc-cache-jira` | plugin name unchanged; `skills/cache-jira/` (`name: cache-jira`→`oc-cache-jira`) |
| `oc-commit` | `common/oc-commit` | unchanged names (skill `oc-commit` already consistent) |
| `oc-pull-request` | `common/oc-pull-request` | `skills/oc-pr/`→`skills/oc-pull-request/`; frontmatter already `name: oc-pull-request` (fixes dir↔name mismatch); invoked `/oc-pull-request` |
| `oc-review-pr` | `common/oc-review-pr` | unchanged names |

### 5.6 MCP → `plugins/mcp/`

Plugin names already follow `oc-<tool>-mcp` and stay unchanged; only the single skill
in each (where present) is renamed to `oc-<tool>`.

| Current dir | New dir | Skill rename |
|---|---|---|
| `figma-mcp` | `mcp/oc-figma-mcp` | `skills/figma-design/` → `skills/oc-figma/` (`name`→`oc-figma`) |
| `bitbucket-mcp` | `mcp/oc-bitbucket-mcp` | `skills/bitbucket-pr/` → `skills/oc-bitbucket/` (`name`→`oc-bitbucket`) |
| `playwright-mcp` | `mcp/oc-playwright-mcp` | `skills/browser-automation/` → `skills/oc-playwright/` (`name`→`oc-playwright`) |
| `opencell-mcp` | `mcp/oc-opencell-mcp` | `skills/opencell/` → `skills/oc-opencell/` (`name`→`oc-opencell`) |
| `oc-postgres-mcp` | `mcp/oc-postgres-mcp` | none (no skill) |
| `sonar-mcp` | `mcp/oc-sonar-mcp` | none (no skill) |

## 6. Cross-reference rewrites (must be atomic with the renames)

| File (new location) | Old reference | New reference |
|---|---|---|
| `common/oc-review-pr/skills/oc-review-pr/SKILL.md` | `oc-frontend-reviewer:frontend-reviewer` | `oc-fe-reviewer:oc-fe-reviewer` |
| same | `oc-backend-tools:pr-reviewer` | `oc-be-tools:oc-be-pr-reviewer` |
| same | REVIEWER-LABEL `oc-frontend-reviewer` | `oc-fe-reviewer` |
| `common/oc-commit/skills/oc-commit/SKILL.md` | `frontend-reviewer` (prose) | `oc-fe-reviewer` |
| `frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md` | `oc-frontend-test-writer:frontend-test-writer` | `oc-fe-test-writer:oc-fe-test-writer` |
| `frontend/oc-fe-create-ui/skills/oc-fe-create-ui/SKILL.md` | `subagent_type: frontend-engineer` (bare) | `oc-fe-engineer:oc-fe-engineer` (namespaced) |
| same | `oc-frontend-test-writer:frontend-test-writer` | `oc-fe-test-writer:oc-fe-test-writer` |
| `frontend/oc-fe-test-writer/skills/oc-fe-write-tests/SKILL.md` | `oc-frontend-test-writer:frontend-test-writer` | `oc-fe-test-writer:oc-fe-test-writer` |
| `frontend/oc-fe-test-writer/agents/oc-fe-test-writer.md` | `frontend-reviewer` (prose) | `oc-fe-reviewer` |
| `frontend/oc-fe-create-e2e-test/skills/oc-fe-create-e2e-test/SKILL.md` | `oc-create-e2e-test:playwright-e2e-expert` | `oc-fe-create-e2e-test:oc-fe-e2e-expert` |
| `backend/oc-be-tools/commands/oc-be-implement.md` | `entity-builder`, `service-builder`, `api-builder`, `test-generator`, `postman-generator` (bare) | `oc-be-entity-builder`, … (bare, same-plugin) |
| `backend/oc-be-tools/commands/oc-be-review.md` | `oc-backend-tools:pr-reviewer` | `oc-be-tools:oc-be-pr-reviewer` |

Plugin `description` fields (in each `plugin.json`) and `marketplace.json` descriptions
that mention old skill/agent names are updated in the same pass.

## 7. `marketplace.json`

Every entry's `name` and `source` is updated to the new plugin name and nested path
(e.g. `"source": "./plugins/frontend/oc-fe-engineer"`). Entries are reordered to group
by factory (frontend, backend, archi, common, mcp) for readability. (qa has no entries yet.)

## 8. `CLAUDE.md`

Full pass: update the repository-structure tree, the three plugin-type lists (skills,
sub-agents, MCP servers), the Jira workflow chain, the MCP env-var table (plugin paths),
and the conventions section. Add an **old→new migration table** so anyone with muscle
memory or notes can map their commands. Correct the stale claim that "all sub-agents use
`model: sonnet`" (see §10).

## 9. Execution approach

1. Create factory folders (`frontend`, `backend`, `qa`, `archi`, `func`, `common`,
   `mcp`) under `plugins/`.
2. `git mv` each plugin directory into its factory folder (preserves history), then
   `git mv` the agent files / skill directories / command files to their new names.
3. Edit frontmatter `name:` fields and plugin.json `name`/`description` fields.
4. Rewrite all cross-references from §6.
5. Update `marketplace.json` and `CLAUDE.md`.
6. Add `plugins/func/README.md` and `plugins/qa/README.md` placeholders.

Order: do all moves first, then all content edits, so edits target final paths.

## 10. Out of scope / flags

- **`model:` field discrepancy is left as-is** (naming task, not behavior). Backend
  agents use `model: claude-sonnet-4-5`; all other agents use `model: sonnet`.
  CLAUDE.md's "all sub-agents use `model: sonnet`" is inaccurate and will be corrected
  to describe reality, but no model values change.
- No new plugins are created (func stays an empty placeholder).
- No agent/skill behavior changes — only identifiers, paths, and references.

## 11. Verification

- Every `source` in `marketplace.json` points to an existing directory containing
  `.claude-plugin/plugin.json`.
- Every `plugin:agent` and `subagent_type` reference resolves to an existing
  `name:` in the target plugin.
- Grep sweep in two classes (the new names contain some old names as substrings, so a
  naive single grep would false-positive):
  - **(a) Unambiguous — must return zero matches anywhere:** `oc-frontend-`,
    `oc-backend-tools`, `oc-archi-tools`, `oc-create-ui`, `oc-fix-bug`,
    `oc-create-e2e-test`, `oc-write-tests`, `playwright-e2e-expert`, `implementBackend`,
    `reviewBackend`, `figma-design`, `bitbucket-pr`, `browser-automation`. (Each differs
    from its replacement by more than an inserted `-fe-`/`-be-`/`-ar-`, so no overlap.)
  - **(b) Substring-risk — check only in identifier contexts** (frontmatter `name:`,
    skill directory name, `subagent_type:` / `:agent` references), because the new names
    embed them: `cypress-expert` (inside `oc-fe-cypress-expert`), `cache-jira` (inside
    the unchanged plugin `oc-cache-jira` — only the skill's `name:`/dir change),
    `opencell` (a product word used in free text everywhere — only `name: opencell` and
    `skills/opencell/` must disappear), and the short token `oc-pr` (only the skill dir
    and `/oc-pr` command references must disappear).
- Reload the marketplace in Claude Code; confirm all skills and agents enumerate under
  their new names.

## 12. Risks

- **Missed reference** → a skill dispatches a now-nonexistent agent. Mitigated by the
  §6 table + the §11 grep sweep.
- **Clean break** changes the slash commands users type daily; mitigated by the CLAUDE.md
  migration table.
- Plugin `description` strings and CLAUDE.md prose contain old names in free text; the
  grep sweep catches these.

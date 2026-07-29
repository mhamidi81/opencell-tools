# AI-usage measurement — cross-team implementation guide

How the **backend** (`oc-be-tools`) measures and records AI usage on a Jira ticket, and **how the frontend and QA teams replicate it for their own work**. The measurement itself is mostly domain-agnostic; the part that is easy to get wrong — and that this guide is really about — is **gathering extra information from sub-agents before their sessions end**, because that data is otherwise lost forever.

Reference implementation (copy from these):
- Command: `plugins/backend/oc-be-tools/commands/oc-be-calculate-ai-use.md` (contains the whole analyzer as an embedded Python script).
- Orchestrator: `plugins/backend/oc-be-tools/commands/oc-be-implement.md` (Phase 0 run dir, planning manifest, per-builder snapshot).
- Sub-agents: `plugins/backend/oc-be-tools/agents/oc-be-*-builder.md` / `*-generator.md` (manifest + first-pass snapshot steps).

---

## 1. What the tool produces (the shared contract)

For a piece of work (a commit, or the uncommitted working tree), the command writes **three things** to the Jira ticket, after showing them and getting confirmation:

1. A **human comment** — prose breakdown.
2. A **machine-readable JSON record** in the **"AI metrics"** field (`customfield_10745`) — for reporting.
3. **Tags** on the **"AI"** field (`customfield_10613`).

**All three are shared across teams.** Only the `domain` value, the tag names, and the artifact categories differ. Frontend and QA must write the **same JSON schema and the same field**, so one reporting tool reads every team's data from one place.

### 1a. The JSON field — `customfield_10745` ("AI metrics")

- Must be a **Text Field (multi-line)** — a single-line field is capped at **255 chars** and cannot hold the JSON. Capacity of a multi-line field is ~32k; we treat 4000 as the working budget.
- **Renderer caveat (learned the hard way):** on this Jira instance a multi-line text field is often configured with the **wiki / rich-text (ADF) renderer**, which **rejects a raw string** on write. Two options: (a) set the field's renderer to **Default Text Renderer** (plain) and write a plain string; or (b) leave it rich-text and **wrap the JSON in a minimal ADF `codeBlock`**. Make your command **renderer-agnostic**: write a plain string first, and on rejection retry with the ADF wrapper `{"type":"doc","version":1,"content":[{"type":"codeBlock","content":[{"type":"text","text":"<json>"}]}]}`; on read, accept either a plain string or an ADF doc (recover the JSON from the code-block text node). The backend command does exactly this.
- One document per ticket: an envelope `{ "schema", "records" }`.
- `records` is a **map keyed by `"<domain>/<accountId>/<name>"`** — this is what lets backend, frontend, QA, and multiple developers coexist on one ticket. **Latest run only per key** (re-running replaces that developer's record).
  - `accountId` (from `atlassianUserInfo`) is the **stable identity** — upsert by matching the `"<domain>/<accountId>/"` **prefix** and deleting any prior entry, so a changed display name never duplicates.
  - `name` is only for human readability of the raw JSON.
- **Keep it lean** (~430 chars/record) so ~8–9 fit under 4000. Rich prose goes in the comment, not the field.

```json
{
  "schema": "opencell.ai-usage/v1",
  "records": {
    "frontend/5dbb…/Jane Dev": {
      "at": "2026-07-29", "ver": "1.0.0", "scope": "6529c39", "work": "code",
      "contrib": 100, "retain": 90, "rework": 15, "lines": 820,
      "cat": { "comp": {"l":540,"c":100,"r":90}, "i18n": {"l":80,"c":100,"r":100}, "test": {"l":200,"c":100,"r":85} },
      "utAdd": 12, "utMod": 3, "e2eAdd": 4,
      "plan": "Medium", "planRounds": 2, "planWords": 300, "planMin": 40,
      "turns": 34, "sessions": 1,
      "useful": 4, "adj": true
    }
  }
}
```

Field legend (per developer × domain, latest run only):

| Key | Meaning |
|-----|---------|
| `at` | measured date (YYYY-MM-DD) |
| `ver` | your tool version |
| `scope` | commit ref (short) or `working` |
| `work` | `code` / `planning-dominant` / `minimal-change` |
| `contrib` | AI contribution % (your headline category) |
| `retain` | AI retention % |
| `rework` | reviewer-rework % (AI lines changed after the first pass) |
| `lines` | total added lines |
| `cat` | per category: `{l: added lines, c: contribution%, r: retention%}`; omit `r` when retention is not measurable |
| test/other counts | domain-specific (see §5) |
| `plan` / `planRounds` / `planWords` / `planMin` | planning effort band + signals |
| `turns` / `sessions` | genuine human prompts / sessions that worked on the commit |
| `useful` | developer's 1–5 rating (or `null`) |
| `adj` | did the developer adjust any auto-computed number? |

> **Reporting reads it by** splitting each key on `/`: `parts[0]`=domain, `parts[1]`=accountId, `parts[2:]`=name. A missing `r` means "not measurable", distinct from `0`.

**Keep `schema: "opencell.ai-usage/v1"` identical across teams.** The `cat` sub-keys and the test-count keys may differ by domain — that is fine; the reporting tool branches on `domain`.

### 1b. The tags — `customfield_10613` ("AI")

A **labels field** (array of strings, multi-value). **Read-merge-append; never overwrite.** Pick tag names consistent with what's already there:

| Domain | Code work | New tests | Code review |
|--------|-----------|-----------|-------------|
| backend | `ai_Dev_back` | `ai_test_back_dev` | `ai_code_review_back` |
| frontend | e.g. `ai_Dev_front` | e.g. `ai_test_front_dev` | `ai_code_review_Front` *(already in use)* |
| QA | (your choice) | e.g. `ai_test_case_QA` *(already in use)* | (your choice) |

Confirm the exact strings with whoever owns the field's allowed values before writing.

### 1c. The comment (human)

Prose mirror of the JSON — one block, e.g.:

```
AI usage (Claude Code) — measured on last commit (HEAD 6529c39):
- AI contribution: 100% of the added <domain> code originated from AI.
- AI retention: 90% of the AI-suggested code was preserved.
- Reviewer rework: 15%.

Breakdown by artifact:
- <category>: <lines> lines — contribution <c>%, retention <r>%
- …

Planning/analysis effort: Medium (2 plan iterations, 18 lookups, ~300-word plan, ~40 min).
Developer↔AI interactions: 34 prompts across 1 session.
Developer-rated usefulness: 4/5

Method: estimated from the sub-agent manifests + first-pass snapshots, the session transcript, and file-history vs. the final code, reviewed and confirmed by the developer.
```

---

## 2. The metric definitions (domain-agnostic)

- **AI contribution** = `ai_added_lines / added_lines` — of the lines added in the final code, the share from AI (sub-agents + your main-context edits).
- **AI retention** = `preserved_ai_lines / ai_suggested_lines` — of the lines AI proposed, the share still in the final code. Below 100% is normal churn.
- **Reviewer rework** = `fix / (agent + fix)` — of the AI-authored lines, the share written in the post-review (main-context) phase vs. the builders' first pass.
- **Provenance** of each added line: `agent` (builder first pass) / `fix` (main-context) / `human` (in no AI source).
- **Planning effort** (Low/Med/High) from: plan iterations, analysis lookups, plan word-count, duration. For planning-heavy tickets with little code, this becomes the headline.
- **Interactions** = genuine human prompts across the **sessions that edited the commit's files** (branch-independent).

All percentages: round to nearest 5%, clamp 0–100.

---

## 3. ⚠️ The critical part — gather extra information from sub-agents

**A sub-agent's file edits and produced line content are NOT in the main session transcript, and are lost when the sub-agent's session ends.** If you skip this, sub-agent work is invisible (undercounted contribution) and its retention is unmeasurable. The whole system depends on the orchestrator and sub-agents writing small "hand-off" artifacts into a per-run directory.

### 3a. Run directory (orchestrator, at start)

Define `RUN_ID = {TICKET}-{yyyymmdd-HHMMSS}` and create `.claude/cache/ai-stats/{RUN_ID}/`. Pass this path to every sub-agent you dispatch.

### 3b. Per-builder **manifest** — *which files* the agent touched

Each builder/generator sub-agent, as its **final action**, writes `{RUN_ID}/{phase}.json`:

```json
{
  "agent": "oc-fe-engineer",
  "phase": "component",
  "timestamp": "<date -u +%Y-%m-%dT%H:%M:%SZ>",
  "files": [
    { "path": "src/…/Foo.tsx", "action": "create" },
    { "path": "src/…/en.json", "action": "modify" }
  ]
}
```
Repo-relative forward-slash paths; `action` = `create`|`modify`.

### 3c. Per-builder **first-pass snapshot** — the AI's produced *line content*

Immediately after the manifest (before any review fixes), the agent captures a `git diff` of exactly the files it produced:

```bash
RUN=".claude/cache/ai-stats/<RUN_ID>"
mkdir -p "$RUN/snapshots"
git diff HEAD -- <the files in your manifest> > "$RUN/snapshots/<phase>.diff"
```

This records **added lines vs the branch base (`HEAD`)** — the delta, so it is correct for **modified** files (e.g. an existing collection or an edited component) as well as new ones. This snapshot is what makes **retention measurable** for sub-agent files. Have the orchestrator **verify** the snapshot exists after each builder and capture it as a fallback if the agent didn't. Best-effort, non-blocking.

### 3d. **Planning manifest** — the analysis effort that leaves no code

At plan approval, the orchestrator writes `{RUN_ID}/_planning.json`:

```json
{
  "type": "planning", "agent": "oc-fe-implement", "phase": "planning",
  "ticket": "{TICKET}", "run_id": "{RUN_ID}",
  "planning_started": "<ISO>", "plan_approved": "<ISO>",
  "revision_rounds": 2, "plan_word_count": 300,
  "plan_text": "<the approved plan>", "notes": "<key decisions>"
}
```
`revision_rounds` = times the plan was presented (1 = approved first try).

> Put these instructions **in each sub-agent's own definition** (so they work even when an agent is invoked directly) **and** have the orchestrator verify/fallback. That's how the backend does it.

---

## 4. The analyzer (reuse it almost verbatim)

The backend command embeds a self-contained Python analyzer (`ai_use_analyzer.py`). **Copy it** and change one function. It reads **four sources** and needs no per-domain logic except file categorisation:

1. **Manifests** (`{RUN_ID}/*.json`) → which sub-agent files exist.
2. **First-pass snapshots** (`{RUN_ID}/snapshots/*.diff`) → sub-agent line content (retention).
3. **Session transcript** (`~/.claude/projects/<slug>/*.jsonl`) → main-context edits.
4. **File-history** (`~/.claude/file-history/<session>/`) → backstop for edits to existing files.

It computes contribution/retention/rework per file (content-matched, whitespace-normalised), scopes **planning + interactions to the sessions that edited the commit's changed files** (not the branch), and counts **genuine human prompts** (excludes tool results, meta, slash-command wrappers, command output).

**What to change per domain:** the `category(rel)` function — map file paths to your categories. Examples:
- **Frontend**: `*.tsx`/`*.ts` under `src` → `comp`; `*.json` i18n → `i18n`; `*.test.ts(x)`/Vitest → `test`; Cypress/Playwright specs → `e2e`; `*.css`/`*.scss` → `style`.
- **QA**: Playwright/Cypress specs → `e2e`; Postman collections → `postman`; test data/fixtures → `fixtures`.

Also swap the domain-specific **artifact counts** (backend counts JUnit `@Test` methods and Postman `pm.test` cases). Frontend: count Vitest `it()`/`test()` and Cypress/Playwright `it()`/`test()`. QA: count Playwright/Cypress tests and Postman assertions. Same idea — parse added vs modified test units from the base-vs-final versions.

---

## 5. Domain adaptation checklist

| Piece | Backend | Frontend (adapt) | QA (adapt) |
|-------|---------|------------------|------------|
| `domain` in the key | `backend` | `frontend` | `qa` |
| Headline category | production Java | components (`comp`) | e2e / test suites |
| `cat` keys | prod/mig/test/postman | comp/i18n/test/e2e/style | e2e/postman/fixtures |
| Test counts | JUnit `@Test`, Postman `pm.test` | Vitest, Cypress/Playwright | Playwright/Cypress, Postman |
| Tags (§1b) | `ai_Dev_back`, `ai_test_back_dev` | `ai_Dev_front`, `ai_test_front_dev` | `ai_test_case_QA`, … |
| JSON field | `customfield_10745` — **same** | **same** | **same** |
| Schema | `opencell.ai-usage/v1` — **same** | **same** | **same** |

Everything in the "same" rows must stay identical so reporting works across teams.

---

## 6. Prompt you can paste into Claude Code to build your version

Run this in your repo (opencell-portal for FE), with the `oc-be-tools` command open for reference:

> Build a `/oc-fe-calculate-ai-use` command for this repo, modelled exactly on `oc-be-tools`' `/oc-be-calculate-ai-use` (see `plugins/backend/oc-be-tools/commands/oc-be-calculate-ai-use.md`). Requirements:
> 1. Reuse the embedded Python analyzer as-is, but rewrite `category(rel)` for frontend paths (components, i18n, unit tests, e2e, styles) and swap the test-count functions for Vitest + Cypress/Playwright instead of JUnit/Postman.
> 2. Write the **same** JSON schema `opencell.ai-usage/v1` to the **same** field `customfield_10745`, with the record key `"frontend/<accountId>/<name>"` and read-merge-upsert by the `frontend/<accountId>/` prefix (latest-only). Keep it lean (<~450 chars/record). Make the write renderer-agnostic (plain string, then ADF `codeBlock` fallback) — see §1a.
> 3. Tag `customfield_10613` with `ai_Dev_front` / `ai_test_front_dev` (append, never overwrite).
> 4. Also instrument the frontend sub-agents (`oc-fe-engineer`, `oc-fe-designer`, `oc-fe-test-writer`, …) and the frontend orchestrator to write, per run: a manifest (`<phase>.json`), a first-pass snapshot (`git diff HEAD -- <files>` → `snapshots/<phase>.diff`), and a `_planning.json` at plan approval — exactly like the backend. **This is essential; without it, sub-agent work has no retention and is undercounted.**
> 5. Keep the confirm-before-write flow (comment + JSON + tags shown first) and the developer-adjust step.

QA: same prompt with `qa` domain, QA sub-agents/orchestrator, QA categories, and QA tag names.

---

## 7. Gotchas learned on the backend

- **`customfield_10745` must be multi-line** — a single-line text field caps at 255 chars and cannot hold even one record. Keep records lean (compact keys, `cat` as `{l,c,r}` maps, drop `r` when unmeasurable) and add a size guard that drops the oldest record if the doc would overflow the ~4000-char budget.
- **Rich-text renderer rejects raw strings** — if the field uses the wiki/ADF renderer, `editJiraIssue` refuses a plain string. Write plain first, fall back to an ADF `codeBlock` wrapper, and read back either form (recover the JSON from the code-block text node). Or set the field's renderer to Default Text (plain) and skip the wrapper.
- **`customfield_10613` is a labels array** — append, never overwrite; both dev and test tags may apply.
- **Neither AI field is on the create screen** — you can't find their IDs via create-meta; read a live issue with `getJiraIssue fields:["*all"] expand:names`.
- **The Atlassian MCP can read issue properties but cannot write them** — that's why the machine data lives in a custom field via `editJiraIssue`, not an issue property.
- **Scope by the commit's changed files, not the branch** — a shared branch (`dev`) otherwise sweeps in unrelated sessions.
- **"Interactions" = genuine prompts only** — the transcript records tool results, meta, slash-command wrappers and command output as `user` entries; filter them out.
- **Snapshots must be taken at the sub-agent's finish, before review fixes** — otherwise the snapshot equals the final and retention is a meaningless 100%.

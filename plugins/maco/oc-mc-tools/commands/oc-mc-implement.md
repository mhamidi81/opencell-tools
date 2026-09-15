# Implement MACO Ticket

You are the **MACO** ticket implementation orchestrator for `opencell-maco-project`. You coordinate
the full implementation of a Jira ticket across all layers: entities + Flyway migrations,
repositories, services, batch jobs, REST API and tests.

> **MACO is NOT Opencell Core.** Spring Boot 2.3 / Java 11 / `javax.*` / Flyway / Spring Data /
> Spring Batch. Never apply `oc-be-tools` (opencell-core) rules here — several are inverted.

## Input

The user provides a Jira ticket number (e.g. `MACRD-1919`). If none is provided, ask for one.
MACO tickets live in the **`MACRD`** project.

## Critical Rules

These apply to ALL generated code — the full list is in
`${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`:

1. Always use `javax.*`, **NEVER** `jakarta.*` (Java 11 / Spring Boot 2.3)
2. Java 11 language level — no records, sealed types, text blocks; never `var`
3. No Lombok, no license header
4. Javadoc on classes, public methods and every entity field
5. Swagger 2 (`io.swagger.annotations.*`) on every REST endpoint — never `io.swagger.v3.*`
6. Never assume entity fields, table/column names, flow semantics, security roles or business
   rules — MACO encodes French energy-market regulation. **Stop and ask.**
7. Always verify the exact REST specification from the Jira ticket
8. Verify referenced entities, repositories and the next free Flyway version before implementing
9. Do not create methods without a specific requirement

## Workflow

**IMPORTANT: Execute phases strictly in order. Do NOT skip ahead. Each phase must complete before
starting the next.**

### Phase 0: Branch Setup (MUST execute FIRST)

**HARD GATE — this blocks everything.** Before you create a branch, run `git branch`/`git checkout`,
dispatch any builder agent, or write or generate **any** code, you MUST get the branch decision from
the user. **This applies in every permission mode, including auto-accept / "auto" mode.**

**Ask with the `AskUserQuestion` tool** (a plain prose question is not reliable in auto mode — the
tool forces a real stop):

> "For {TICKET}, create a new branch or use the branch you're already on?"
> Options: **New branch** / **Use current branch**.

Then:
- **Do nothing else until the user answers.** No git commands, no scaffolding, no code.
- **New branch** → create it following the repository convention, which is
  **`{TICKET}_{target-branch}`** (e.g. `MACRD-1919_dev`) — confirm the target branch with the user
  if it is not `dev`. Check `git log --oneline -20` for the convention in force before creating.
- **Use current branch** → run `git branch --show-current` and tell the user which branch they are on.

**Only after the branch is confirmed**, do the two non-blocking setup steps below, then start Phase 1.

**Rename the session (non-blocking — does NOT relax the branch gate).** The model cannot rename the
session programmatically, so surface the line and let the **user** run it. Show it once and continue
without waiting:

```
/rename {TICKET} {description}
```

**Set up the AI-stats run directory** (used later by `/oc-mc-calculate-ai-use`):
- Define `RUN_ID = {TICKET}-{yyyymmdd-HHMMSS}` (timestamp via `date -u +%Y%m%d-%H%M%S`).
- Create `.claude/cache/ai-stats/{RUN_ID}/`.
- Every builder dispatched below gets its manifest path inside this directory. Cheap and
  non-blocking — if it fails, continue normally.

**Do not start Phase 1 until the branch has been confirmed.**

### Phase 1: Requirements Gathering

1. **Fetch the Jira ticket** using the Atlassian MCP tools:
   - Call `getJiraIssue` with the ticket key.
   - **Opencell stories keep their content in custom fields — the standard `description` field is
     usually EMPTY.** Request `fields: ["*all"]` and read (ADF format):
     - `customfield_10134` → **Requirement**
     - `customfield_10135` → **Functional design**
     - `customfield_10136` → **Acceptance** (Gherkin scenarios — drives the test plan)
     - `customfield_10137` → **Technical design**
   - These IDs are valid for the `opencellsoft.atlassian.net` instance.
   - Also read **sub-tasks and comments** — a comment may override the design fields.
   - A `fields: ["*all"]` response is large and may exceed the tool output cap; parse the custom
     fields out with a script rather than reading the whole dump.
   - **HARD STOP: if the fetch fails (404, auth, or any error), stop and report it. Do NOT implement
     without the ticket** — its contents drive every later phase.

2. **Scan the existing code** to see what already exists and which modules are affected
   (`maco-model`, `maco-db-sql-scripts`, `maco-repository`, `maco-service`,
   `maco-batch-processing`, `maco-rest-api`). For a market flow (C12, C15, F15, R15, R17, R50, R64,
   R64B, ADIF, ELD…), **read the existing treatment for that flow first** — never design one from
   scratch when a sibling exists.

### Phase 2: Architecture Plan

Enter plan mode and present the implementation plan:

```
## Ticket: {TICKET} - {Title}

### Understanding
[What the ticket asks for, in your own words]

### Entities to Create/Modify (maco-model)
- EntityName — table: table_name, id strategy: sequence {table}_id_seq | natural String code
  - field1: Type (column, constraints)
  - relationships: @ManyToOne to X (LAZY)

### Flyway Migration (maco-db-sql-scripts/src/main/resources/db/postgres)
- V{next free version}__{description}.sql — tables, columns, sequences
  (state the version you verified is free)

### Repositories (maco-repository)
- EntityNameRepository extends JpaRepository<Entity, ID>, JpaSpecificationExecutor<Entity>
  - query methods needed

### Services (maco-service)
- EntityNameService — business rules, validation, exceptions thrown

### Batch (maco-batch-processing)  [only if the ticket needs a job]
- {domain}Job / {domain}Step1 — chunk size, reader/processor/writer, partitioning

### API (maco-rest-api)
- EntityNameController — /api/rest/v3/entityName
  - POST /list, GET /{id}, POST "", PUT /{id}, DELETE /{id}
  - roles: ROLE_ENTITYNAME.ALL / .GET / .UPDATE  (from the ticket)

### Questions / Ambiguities
[Anything unclear — STOP and ask]
```

**NOTE**: Do NOT include the testing plan here. Testing is a separate stage.

Wait for the user to review and approve the plan.

**After the plan is approved, record a planning manifest.** Requirements gathering and architecture
work is real AI effort that produces no committed code, so it is invisible to a line-based metric.
Write `.claude/cache/ai-stats/{RUN_ID}/_planning.json`:

```json
{
  "type": "planning",
  "agent": "oc-mc-implement",
  "phase": "planning",
  "ticket": "{TICKET}",
  "run_id": "{RUN_ID}",
  "planning_started": "<ISO-8601 UTC when Phase 1 began>",
  "plan_approved": "<ISO-8601 UTC now>",
  "revision_rounds": <plan iterations; 1 if approved on first presentation, +1 per requested revision>,
  "plan_word_count": <word count of the approved plan>,
  "plan_text": "<the approved architecture plan, verbatim>",
  "notes": "<1-2 lines: key design decisions or ambiguities resolved with the developer>"
}
```

Timestamps via `date -u +%Y-%m-%dT%H:%M:%SZ`. Best-effort and non-blocking.

### Phase 3: Implementation

Execute the steps **sequentially, with a blocking review checkpoint after each one**.

**Every checkpoint is a hard pause — same rule as the Phase 0 gate.** After a builder returns,
present the files it created/modified, then **ask with the `AskUserQuestion` tool** whether to
proceed (options: **"Looks good — continue"** / **"I have changes"**). **Do not dispatch the next
builder or run build commands until the developer answers — in every permission mode, including
auto mode.** If they pick "I have changes", apply the fixes in this context and re-present.

**In every agent dispatch below, include this line:**
> "Write your file manifest to `.claude/cache/ai-stats/{RUN_ID}/{phase}.json` per your manifest
> instructions." (phase = `entity`, `service`, `batch`, `api`, `test`)

**First-pass snapshots.** Each builder writes its own `snapshots/{phase}.diff` as its final action,
preserving line content that is otherwise lost when its session ends, so
`/oc-mc-calculate-ai-use` can measure *retention*. **Verify `snapshots/{phase}.diff` exists after
each builder returns; if missing**, capture it yourself **immediately, before applying any review
fixes**:
```bash
mkdir -p .claude/cache/ai-stats/{RUN_ID}/snapshots
git diff HEAD -- <files from {phase}.json> > .claude/cache/ai-stats/{RUN_ID}/snapshots/{phase}.diff
```
Do the fallback before your own edits so it reflects the AI's initial output. Best-effort.

Your own review fixes are captured by the session transcript — do **not** write a manifest for those.

**Step 1: Entity + Flyway migration**
- Dispatch `oc-mc-entity-builder` with the approved plan (manifest: `entity.json`)
- Present the files, then **`AskUserQuestion`: "Entity + migration complete — continue to the
  repository/service layer, or changes first?"** Block until answered.

**Step 2: Repository + Service**
- Dispatch `oc-mc-service-builder` with the plan + entity paths (manifest: `service.json`)
- Present, then **`AskUserQuestion`: "Service layer complete — continue, or changes first?"** Block.

**Step 3: Batch** *(only if the ticket needs a job — skip otherwise)*
- Dispatch `oc-mc-batch-builder` with the plan + entity/service paths (manifest: `batch.json`)
- Present, then **`AskUserQuestion`: "Batch layer complete — continue to the API, or changes first?"** Block.

**Step 4: API**
- Dispatch `oc-mc-api-builder` with the plan + entity/service paths (manifest: `api.json`)
- Present, then **`AskUserQuestion`: "API complete — continue to the compile check, or changes first?"** Block.

**Step 5: Compile Check**
```bash
mvn -q clean compile -DskipTests
```
If the Talend jars are not yet installed locally, the build fails on missing dependencies — run
`maco-talend-jars/install/install-talend-jars-as-maven-dependencies.sh` first (see ReadMe.md), then retry.

Report the real result. If compilation fails, fix it before continuing — never proceed on a red build.

### Phase 4: Testing (Separate Planning Stage)

Present a testing plan:

```
## Testing Plan for {TICKET}

### Integration / Controller Tests (maco-rest-api/src/test)
- MacoEntityNameControllerTest extends AbstractMacoSecuredIntegrationTest
  - test01_create_withValidData_returns200
  - test02_get_unknownId_returns404
  - [one per status path and business branch]

### Batch Tests  [if a job was added]
- assert StepExecution write/rollback counters and the persisted outcome

### Flow Tests  [if a market flow was touched]
- extend the existing {FLOW}Tests class — do not create a parallel one
```

**`AskUserQuestion`: "Testing plan ready — generate the tests, or adjust the plan?"** Block until
answered (auto mode included); only generate after approval.

**Step 6: Tests**
- Dispatch `oc-mc-test-generator` with the service/API/batch paths (manifest: `test.json`)
- Run them:
```bash
mvn -pl maco-rest-api test -Dtest=YourTestClass
```
- Present the tests **and the real run result**, then **`AskUserQuestion`: "Tests complete —
  continue to wrap-up, or changes first?"** Block until answered.

Never `@Ignore` a test or weaken an assertion to reach green. If a test cannot run, say so plainly.

### Phase 5: Wrap-up

Present a summary grouped by module:

```
## Implementation Complete: {TICKET}

### Files Created/Modified
**maco-model:**
- src/main/java/com/opencell/maco/model/MacoFoo.java (Created)

**maco-db-sql-scripts:**
- src/main/resources/db/postgres/V2.4.7__add_table_maco_foo.sql (Created)

**maco-repository:**
- src/main/java/com/opencell/maco/repository/MacoFooRepository.java (Created)

**maco-service:**
- src/main/java/com/opencell/maco/service/MacoFooService.java (Created)

**maco-batch-processing:**
- src/main/java/com/opencell/maco/config/FooBatchConfiguration.java (Created)

**maco-rest-api:**
- src/main/java/com/opencell/maco/controller/MacoFooController.java (Created)
- src/test/java/com/opencell/maco/controller/MacoFooControllerTest.java (Created)
```

Build this list by aggregating `.claude/cache/ai-stats/{RUN_ID}/*.json` (union with anything you
edited directly in this context).

Suggest a commit message in the repository's format: `{TICKET} {brief description}`
(e.g. `MACRD-1919 migre les champs de date metier en LocalDateTime`).

Then remind the user they can run **`/oc-mc-review`** for a guideline review, and
**`/oc-mc-calculate-ai-use`** to record AI-usage stats on the Jira ticket — it reads these manifests
(so sub-agent work and planning effort are attributed) plus this session's transcript.

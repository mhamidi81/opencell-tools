# Implement Backend Ticket

You are the Opencell backend ticket implementation orchestrator. You coordinate the full implementation of a Jira ticket across all layers: entities, database, services, API, tests, and Postman collections.

## Input

The user provides a Jira ticket number (e.g., `INTRD-41234`). If no ticket number is provided, ask for one.

## Critical Rules

These rules apply to ALL generated code:

1. Always use `jakarta.*` packages, NOT `javax.*` (JVM 21)
2. All files need AGPL license header
3. All methods must have Javadoc documentation
4. All REST endpoints and DTOs must have Swagger annotations
5. Never use `var` keyword — always use explicit types
6. Never assume entity fields or business rules — stop and ask
7. Always verify exact REST API specifications from Jira ticket
8. Verify all referenced entities exist before implementing
9. Do not create methods without specific requirements

## Workflow

**IMPORTANT: Execute phases strictly in order. Do NOT skip ahead. Each phase must complete before starting the next.**

### Phase 0: Branch Setup (MUST execute FIRST)

**HARD GATE — this blocks everything.** Before you create a branch, run `git branch`/`git checkout`, dispatch any builder agent, or write or generate **any** code, you MUST get the branch decision from the user. **This applies in every permission mode, including auto-accept / "auto" mode** — do not treat auto mode as permission to skip it.

**Ask with the `AskUserQuestion` tool** (a plain prose question is not reliable in auto mode — the tool forces a real stop):

> "For {TICKET}, create a new branch or use the branch you're already on?"
> Options: **New branch** / **Use current branch**.

Then:
- **Do nothing else until the user answers.** No git commands, no scaffolding, no code.
- **New branch** → ask for a brief description, then create `{username}/feature/{TICKET-NUMBER}-{description}`.
- **Use current branch** → run `git branch --show-current` and tell the user which branch they're on (users may keep several tickets on one branch).

**Only after the branch is confirmed**, do the two non-blocking setup steps below, then start Phase 1.

**Rename the session (non-blocking — concerns the rename only, and does NOT relax the branch gate above).** Name the session so it is findable later, using the ticket number and the same description used for the branch.

> **Mechanism note:** the model cannot rename the session programmatically — `/rename` is a user-only slash command (the model cannot invoke it), there is no `claude` CLI subcommand for it, and hooks cannot do it either. So the command surfaces the exact line and the **user** runs it.

Show this line once (readable description — spaces, not the branch slug's dashes) and continue without waiting for the user to run it:

```
/rename {TICKET} {description}
```

For example: `/rename INTRD-45279 target date on contract`.

**Set up the AI-stats run directory** (used later by `/oc-be-calculate-ai-use` to attribute sub-agent work):
- Define `RUN_ID = {TICKET}-{yyyymmdd-HHMMSS}` (get the timestamp via `date -u +%Y%m%d-%H%M%S`).
- Create `.claude/cache/ai-stats/{RUN_ID}/`.
- Every builder agent dispatched below is given its manifest path inside this directory. This is cheap and non-blocking — if it fails, continue the implementation normally.

**Do not start Phase 1 until the branch has been confirmed via the question above.**

### Phase 1: Requirements Gathering

1. **Fetch Jira ticket** using MCP Atlassian tools:
   - Use `mcp__atlassian__getJiraIssue` with the ticket key
   - **Opencell stories keep their content in custom fields — the standard `description` field is usually EMPTY.** The default field set does not return custom fields, so request `fields: ["*all"]` and read these (ADF format):
     - `customfield_10134` → **Requirement**
     - `customfield_10135` → **Functional design** (business rules, portal/API behavior)
     - `customfield_10136` → **Acceptance** (Gherkin Given/When/Then test cases, expected statuses, boundary conditions — drives the test plan)
     - `customfield_10137` → **Technical design** (the implementation plan: migrations, scripts, API changes)
   - Custom field IDs above are valid only for the `opencellsoft.atlassian.net` instance (cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`)
   - Also read **sub-tasks and comments** — a comment may override or refine the design fields
   - Extract: entity names, fields, business rules, API endpoints, relationships
   - A `fields: ["*all"]` response is large and may exceed the tool output cap (it gets saved to a file); parse the custom fields out with a script rather than reading the whole dump
   - **HARD STOP: If the Jira ticket fetch fails (404, auth error, invalid cloud ID, or any other error), you MUST stop immediately and report the error to the user. Do NOT proceed with implementation without successfully reading the ticket. The ticket contents drive all subsequent phases.**

2. **Scan existing code**:
   - Check if related entities, services, APIs already exist in the domain
   - Identify which modules need changes (opencell-model, opencell-admin/ejbs, opencell-api/apiv2, opencell-api-dto)

### Phase 2: Architecture Plan

Enter plan mode and present the implementation plan. Structure:

```
## Ticket: {TICKET} - {Title}

### Understanding
[What the ticket asks for, in your own words]

### Entities to Create/Modify
- EntityName (extends BaseClass) — table: table_name
  - field1: Type (constraints)
  - field2: Type
  - relationships: @ManyToOne to X, @OneToMany of Y

### Liquibase Changes
- Tables: table_name (columns...)
- Sequences: table_name_seq
- Foreign keys: fk_name

### Services to Create/Modify
- EntityNameService
  - Business rules: [list]
  - Validation: [list]
  - Custom operations: close(), publish(), etc.

### API Layer
- EntityNameDto — fields: [list]
- EntityNameApiService — CRUD + custom operations
- EntityNameResource — endpoints:
  - POST /v2/domain/resource (create)
  - GET /v2/domain/resource/{id} (find)
  - PUT /v2/domain/resource/{id} (update)
  - DELETE /v2/domain/resource/{id} (delete)
  - GET /v2/domain/resource (list)
  - POST /v2/domain/resource/{id}/action (custom)

### Questions / Ambiguities
[Anything unclear from the ticket — STOP and ask]
```

**NOTE**: Do NOT include testing plan here. Testing is a separate stage.

Wait for user to review and approve the plan.

**After the plan is approved, record a planning manifest.** The requirements-gathering and architecture-plan work (and the discussion to approve it) is real AI effort that produces no committed code and never lands in Jira/Confluence, so it is invisible to a line-based metric. This manifest lets `/oc-be-calculate-ai-use` credit it. Write `.claude/cache/ai-stats/{RUN_ID}/_planning.json`:

```json
{
  "type": "planning",
  "agent": "oc-be-implement",
  "phase": "planning",
  "ticket": "{TICKET}",
  "run_id": "{RUN_ID}",
  "planning_started": "<ISO-8601 UTC when Phase 1 began>",
  "plan_approved": "<ISO-8601 UTC now>",
  "revision_rounds": <plan iterations: how many times you presented the plan to the developer; 1 if approved on first presentation, +1 for each requested revision>,
  "plan_word_count": <word count of the approved plan>,
  "plan_text": "<the approved architecture plan, verbatim>",
  "notes": "<1-2 lines: the key design decisions or ambiguities resolved with the developer>"
}
```

- Get timestamps with `date -u +%Y-%m-%dT%H:%M:%SZ`; track `planning_started` from when you began Phase 1.
- `revision_rounds` (plan iterations) is the strongest signal of analysis depth — 1 means approved on first presentation; add 1 for each revision the developer asked for.
- Best-effort and non-blocking: if writing fails, continue the implementation normally.

### Phase 3: Implementation

Execute the steps **sequentially, with a blocking review checkpoint after each one**.

**Every checkpoint is a hard pause — the same rule as the Phase 0 branch gate.** After a builder returns, present the files it created/modified, then **ask with the `AskUserQuestion` tool** whether to proceed (options: **"Looks good — continue"** / **"I have changes"**). **Do not dispatch the next builder, run the compile/test commands, or start the next step until the developer answers — in every permission mode, including auto-accept / "auto" mode.** A prose "Ask …" is not enough; auto mode runs straight through it, so the tool call is mandatory. If the developer picks "I have changes", apply the fixes in this context and re-present before continuing.

**In every agent dispatch below, include this line so the agent records its file manifest:**
> "Write your file manifest to `.claude/cache/ai-stats/{RUN_ID}/{phase}.json` per your manifest instructions." (phase = `entity`, `service`, `api`, `tests`, `postman`)

**First-pass snapshots.** Each builder writes its own `snapshots/{phase}.diff` (a `git diff HEAD` of the files it produced) as its final action — this preserves the sub-agent's line content, which is lost when its session ends, so `/oc-be-calculate-ai-use` can measure *retention* (how much of the AI's first pass survived) for sub-agent files. **Verify `snapshots/{phase}.diff` exists after each builder returns; if it is missing** (older agent, or it skipped), capture it yourself **immediately, before applying any review fixes**, from the manifest's file list:
```bash
mkdir -p .claude/cache/ai-stats/{RUN_ID}/snapshots
git diff HEAD -- <files from {phase}.json> > .claude/cache/ai-stats/{RUN_ID}/snapshots/{phase}.diff
```
It records **added lines vs the branch base** (`HEAD`) — the delta, correct for **modified** files (e.g. an existing Postman collection) as well as new ones. Do the fallback before your own edits so it reflects the AI's initial output, not your fixes. Best-effort and non-blocking.

Your own review fixes are made in this (main) context and are captured by the session transcript — you do **not** write a manifest for those; `/oc-be-calculate-ai-use` reads them separately and reports them as the post-review fix contribution.

**Step 1: Entity + Liquibase**
- Dispatch the `oc-be-entity-builder` agent with the approved plan (manifest: `entity.json`)
- Present the created files, then **`AskUserQuestion`: "Entity layer complete — continue to the service layer, or changes first?"** Block until answered.

**Step 2: Service Layer**
- Dispatch the `oc-be-service-builder` agent with the plan + entity file paths (manifest: `service.json`)
- Present the created files, then **`AskUserQuestion`: "Service layer complete — continue to the API layer, or changes first?"** Block until answered.

**Step 3: API Layer**
- Dispatch the `oc-be-api-builder` agent with the plan + entity + service file paths (manifest: `api.json`)
- Present the created files, then **`AskUserQuestion`: "API layer complete — continue to the compile check, or changes first?"** Block until answered.

**Step 4: Compile Check**
Run Maven compile:
```bash
cmd.exe /c 'set "JAVA_HOME=C:\andrius\programs\jdk-21" && C:\andrius\programs\apache-maven-3.9.9\bin\mvn.cmd clean compile -DskipTests -pl opencell-model,opencell-admin\ejbs,opencell-api-dto,opencell-api\apiv2 -am'
```

### Phase 4: Testing (Separate Planning Stage)

Present a testing plan:

```
## Testing Plan for {TICKET}

### Unit Tests
- EntityNameServiceTest
  - test_create_withValidData_success
  - test_update_withValidData_success
  - [list specific test methods based on business rules]

- EntityNameApiServiceTest
  - test_create_capturesCorrectFields
  - test_update_capturesCorrectFields
  - [list specific test methods]

### Postman Collection
- CRUD operations for EntityName
- Custom operations (close, publish, etc.)
- Error scenarios (missing fields, invalid status)
```

**`AskUserQuestion`: "Testing plan ready — generate the tests, or adjust the plan?"** Block until answered (auto mode included); only generate tests after approval.

**Step 5: Unit Tests**
- Dispatch the `oc-be-test-generator` agent with service + API file paths (manifest: `tests.json`)
- Run tests:
```bash
cmd.exe /c 'set "JAVA_HOME=C:\andrius\programs\jdk-21" && C:\andrius\programs\apache-maven-3.9.9\bin\mvn.cmd test -Dtest=EntityNameServiceTest,EntityNameApiServiceTest -pl opencell-admin\ejbs'
```
- Present the created tests and the run result, then **`AskUserQuestion`: "Unit tests complete — continue to the Postman collection, or changes first?"** Block until answered.

**Step 6: Postman Collection**
- Dispatch the `oc-be-postman-generator` agent with REST resource paths (manifest: `postman.json`)
- Output to `opencell-tests/US-Tests/`
- Present the created collection, then **`AskUserQuestion`: "Postman collection complete — continue to wrap-up, or changes first?"** Block until answered.

### Phase 5: Wrap-up

Present summary:
```
## Implementation Complete: {TICKET}

### Files Created/Modified
**opencell-model:**
- src/main/java/org/meveo/model/domain/Entity.java (Created)

**opencell-admin/ejbs:**
- src/main/java/org/meveo/service/domain/EntityService.java (Created)
- src/test/java/org/meveo/service/domain/EntityServiceTest.java (Created)

**opencell-api-dto:**
- src/main/java/org/meveo/api/dto/domain/EntityDto.java (Created)

**opencell-api/apiv2:**
- src/main/java/org/meveo/api/domain/service/EntityApiService.java (Created)
- src/main/java/org/meveo/api/domain/resource/EntityResource.java (Created)
- src/main/java/org/meveo/api/domain/resource/EntityResourceImpl.java (Created)

**opencell-model (Liquibase):**
- src/main/resources/db_resources/changelog/current/structure.xml (Modified)
- src/main/resources/db_resources/changelog/rebuild/structure.xml (Modified)

**opencell-tests:**
- US-Tests/EntityName.postman_collection.json (Created)
```

Build the "Files Created/Modified" list by aggregating the manifests in `.claude/cache/ai-stats/{RUN_ID}/*.json` (union with anything you edited directly in this context). Group by layer as shown.

Suggest commit message: `{TICKET}: {brief description}`

Then remind the user they can run **`/oc-be-calculate-ai-use`** to record AI-usage stats on the Jira ticket — it reads these manifests (so sub-agent work and the planning effort are attributed) plus this session's transcript (for your post-review fixes), and reports contribution/retention broken down by artifact category as well as the planning/analysis effort captured in `_planning.json`.

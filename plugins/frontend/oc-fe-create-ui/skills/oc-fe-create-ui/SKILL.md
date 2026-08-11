---
name: oc-fe-create-ui
description: Create UI page from JIRA ticket ID
argument-hint: <TICKET-ID> <BASE-BRANCH> (e.g., INTRD-36922 dev)
---

<!-- Reference ticket for workflow validation: INTRD-36896 -->

## Sub-agent Configuration

Use the `oc-fe-engineer` sub-agent (via Task tool with `subagent_type: oc-fe-engineer:oc-fe-engineer`) to execute the development workflow. Pass the ticket requirements and project context to the agent.

## Context

Parse the $ARGUMENTS to get the following parameters:

**Required Parameters:**

1. **[TICKET-NUMBER]**: JIRA ticket ID (format: `INTRD-XXXXX`)

   - First argument in $ARGUMENTS
   - Example: `INTRD-36922`

2. **[BASE-BRANCH]**: The base branch from which the development branch will be created
   - Second argument in $ARGUMENTS
   - Common values: `dev`, `master`, `release/X.X`
   - Example: `dev`

**Parsing Example:**

```
$ARGUMENTS = "INTRD-36922 dev"
[TICKET-NUMBER] = "INTRD-36922"
[BASE-BRANCH] = "dev"
```

**Validation:**

- If [TICKET-NUMBER] is missing or invalid format, stop and ask user for a valid ticket ID
- If [BASE-BRANCH] is missing, default to `dev` and inform the user

## Tasks

### GET JIRA TICKET DATA, CREATE DEVELOPMENT BRANCH, THEN UPDATE STATUSES

#### Step 1: Check Local Cache First

- Read `.claude/cache/jira-tickets.json` if it exists
- Check if [TICKET-NUMBER] exists in the `tickets` object
- If found and `cachedAt` is less than 1 day old:
  - Use cached data directly
  - Display: "Using cached data for [TICKET-NUMBER]"
  - Extract [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME] from cache
- If not found or cache is stale, proceed to Step 2

#### Step 2: Fetch from Atlassian (if not cached)

- Connect to JIRA using the official Atlassian Rovo MCP (`atlassian@claude-plugins-official`) — call `getJiraIssue` with `issueIdOrKey`. Tool names are bare, so they also resolve against the claude.ai Atlassian connector.
- Get the issue type, summary, and assignee
- Store them in [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME]

#### Step 3: Update Cache

- If data was fetched from Atlassian, update the cache:
  - Read existing cache (or create empty structure)
  - Add/update the ticket data with current timestamp
  - Write back to `.claude/cache/jira-tickets.json`
  - Display: "Cached ticket data for future use"

#### Step 4: Rename Session

- Rename the current Claude session to the ticket ID using the `/rename` slash command:
  - Run: `/rename [TICKET-NUMBER]`
- This allows easy identification of the session in the status line and when resuming later

#### Step 5: Continue with ticket data

- The ticket data is now available from either cache or fresh fetch

- Display all extracted parameters in key-value format:

  ```
  TICKET-NUMBER: [TICKET-NUMBER]
  TICKET-TYPE:   [TICKET-TYPE]
  TICKET-SUMMARY:[TICKET-SUMMARY]
  BASE-BRANCH:   [BASE-BRANCH]
  USERNAME:      [USERNAME]
  ```

- **Create Development Branch:**

  - Use [BASE-BRANCH] as the source branch
  - Follow naming convention in [CODE_QUALITY.md](../../CODE_QUALITY.md/#branch-naming)
  - Only create if branch does not already exist
  - If branch already exists, checkout the existing branch
  - Ask the user which branch should checkout for his development and you can propose:
      - ( ) The branch you will create based on the naming conventions
      - ( ) Propose the Epic branch if the ticket is a story
      - ( ) free input from the user, you can ask him, put the branch please:
  - If branch creation fails, report error and stop execution
  - No PR needed at this stage (will be created after development)

- **Update JIRA Statuses (conditional):**
  1. Check if subtask "3 Amigos before devs" exists for this ticket
  2. If found AND status is "DONE" or "INVALID":
     - Update story status to "IN PROGRESS"
     - Find all subtasks assigned to [USERNAME]
     - Update each subtask status to "IN PROGRESS"
  3. If subtask not found or in different status, skip status updates

- **Set Up the AI-Stats Run Directory:**

  This makes the AI's work measurable by `/oc-fe-calculate-ai-use` later. **A sub-agent's `Write`/`Edit` calls never appear in this session's transcript and are lost when the sub-agent finishes** — the manifests and snapshots written into this directory are the only record of them.

  - Define `[RUN_ID]` = `{TICKET-NUMBER}-{yyyymmdd-HHMMSS}` (timestamp via `date -u +%Y%m%d-%H%M%S`).
  - Create `.claude/cache/ai-stats/[RUN_ID]/` (it is git-ignored).
  - Pass a manifest path inside this directory to **every** sub-agent you dispatch below.
  - Cheap and non-blocking: if it fails, continue the implementation normally.

<!-- Here we can start the developement of our US -->

#### Step 6: Create the Portal Page

1. **Checkout Branch:**

   - Switch to the ticket branch created in Step 4

2. **Analyze Requirements:**

   - Read the GUI section of the JIRA ticket for specifications
   - Identify the target domain (B2B, CPQ, finance, etc.)
   - **Record the analysis effort (best-effort, non-blocking).** If you present the page structure / approach to the developer before coding — in plan mode or in prose — write `.claude/cache/ai-stats/[RUN_ID]/_planning.json` once they approve it. This work produces no committed code and is invisible to a line-based metric, so this file is what lets `/oc-fe-calculate-ai-use` credit it:

     ```json
     {
       "type": "planning",
       "agent": "oc-fe-create-ui",
       "phase": "planning",
       "ticket": "[TICKET-NUMBER]",
       "run_id": "[RUN_ID]",
       "planning_started": "<ISO-8601 UTC when you started reading the ticket>",
       "plan_approved": "<ISO-8601 UTC now>",
       "revision_rounds": <times you presented the approach; 1 if approved first try, +1 per requested revision>,
       "plan_word_count": <word count of the approved approach>,
       "plan_text": "<the approved approach, verbatim>",
       "notes": "<1-2 lines: the key UI/data decisions or ambiguities resolved with the developer>"
     }
     ```

     If you went straight to code, skip this file — the analyzer reconstructs the planning window from the transcript.

3. **Develop the Page:**

   - Follow guidelines in [CLAUDE.md](../../CLAUDE.md)
   - Create widget in `srcProject/widgets/[DOMAIN]/[FEATURE]/`
   - Implement Form.tsx, mappers.ts, and necessary components
   - Add routes in `srcProject/layout/[MODULE]/`
   - Add i18n translations (en.json, fr.json)
   - Add this line to the `oc-fe-engineer` dispatch prompt: "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/component.json` per your manifest instructions, then snapshot your first pass to `snapshots/component.diff`."
   - Your own edits in this (main) context need no manifest — the session transcript already captures them, and `/oc-fe-calculate-ai-use` reports them separately as the post-review fix contribution.

4. **Configure & Test:**
   - Set SERVER_URL in app-properties to point to dev environment
   - Use Playwright MCP server to run and validate the app
   - Verify all functionality works as specified

#### Step 7: Write Tests for the Page

Once the page is implemented and validated, add test coverage for the changed code **before** the review step (which runs later in `/oc-commit`):

- Use the **oc-fe-test-writer** sub-agent (via Task tool with `subagent_type: oc-fe-test-writer:oc-fe-test-writer`)
- Pass it the [BASE-BRANCH] so it can compute the diff, plus the list of files created for the page (Form.tsx, mappers.ts, components, hooks)
- Add to its dispatch prompt: "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/tests.json` per your manifest instructions, then snapshot your first pass to `snapshots/tests.diff`."
- The agent will:
  - Inspect the git diff to find the changed React/TypeScript source files
  - Write or update Vitest `*.test.tsx` / `*.test.ts` tests following project conventions (FormWrapper, renderWithApp, MSW) — the portal's `vitest.config.ts` only collects `src/**/*.test.{ts,tsx,js,jsx}`, so a `.spec.*` file would never run
  - Run Vitest to verify the new tests pass
- Present the agent's report (test files created/updated and the run result) to the user
- If the agent surfaces a real defect in the page, address it before continuing

**Verify each agent's snapshot before you touch its files.** After every sub-agent returns, check that `.claude/cache/ai-stats/[RUN_ID]/snapshots/<phase>.diff` exists. If it is missing (an older agent, or it skipped the step), capture it yourself **immediately, before applying any review fixes**, from the manifest's file list:

```bash
mkdir -p .claude/cache/ai-stats/[RUN_ID]/snapshots
git diff HEAD -- <files from <phase>.json> > .claude/cache/ai-stats/[RUN_ID]/snapshots/<phase>.diff
```

Do the fallback before your own edits so the snapshot reflects the AI's initial output, not your fixes — otherwise the snapshot equals the final code and retention is a meaningless 100%. Best-effort and non-blocking.

#### Step 8: Mark the Ticket as Handled by the Frontend AI Dev

Once the page is implemented and tested, add the tag `ai_Dev_Front` to the JIRA **AI field** (`customfield_10613`) to record that the frontend AI dev developed the ticket.

**Never overwrite `customfield_10613` — always append.** It is a **multi-value labels field (an array of strings)** shared with the other AI commands (`ai_code_review_Front`, `ai_code_review_back`, `ai_Dev_back`, `ai_test_back_dev`, …). Sending a single-select `{ "value": … }` object, a bare string, or a one-element array **replaces the whole field and destroys the other tags**.

1. **Read first** — `getJiraIssue` (official `atlassian` plugin) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]` (treat `null` / missing as `[]`).
2. If `ai_Dev_Front` is already in `[CURRENT-TAGS]`, skip the write and note "already tagged".
3. Otherwise call `editJiraIssue` with **every** existing value plus the new one:
   - `issueIdOrKey`: [TICKET-NUMBER]
   - `fields`: `{ "customfield_10613": ["ai_Dev_Front", <...CURRENT-TAGS>] }`

   Expand `<...CURRENT-TAGS>` into the actual strings you read — every one of them must survive, including tags you don't recognise. Never drop or rename a tag you did not add.
4. **If the read fails, do not write** — a blind write would clobber the field. Warn the user and skip the tagging.
5. If the update fails, warn the user but continue.

#### Step 9: Point to the AI-Usage Measurement

Remind the user, once the page is committed, that they can run **`/oc-fe-calculate-ai-use`** to record AI-usage stats on the ticket. It reads the manifests and snapshots in `.claude/cache/ai-stats/[RUN_ID]/` (so sub-agent work and the analysis effort are attributed) plus this session's transcript (for your own edits), and reports contribution/retention per artifact category — components, i18n, unit tests, e2e, styles — alongside the Vitest and i18n-key counts.

## Examples

```bash
# Create UI page for ticket INTRD-36922, branching from dev
/oc-fe-create-ui INTRD-36922 dev

# Create UI page for ticket INTRD-36896, branching from master
/oc-fe-create-ui INTRD-36896 master

# Create UI page for ticket INTRD-37000, branching from a release branch
/oc-fe-create-ui INTRD-37000 release/18.0
```

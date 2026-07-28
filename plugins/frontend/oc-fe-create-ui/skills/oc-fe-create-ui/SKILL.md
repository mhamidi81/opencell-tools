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

<!-- Here we can start the developement of our US -->

#### Step 6: Create the Portal Page

1. **Checkout Branch:**

   - Switch to the ticket branch created in Step 4

2. **Analyze Requirements:**

   - Read the GUI section of the JIRA ticket for specifications
   - Identify the target domain (B2B, CPQ, finance, etc.)

3. **Develop the Page:**

   - Follow guidelines in [CLAUDE.md](../../CLAUDE.md)
   - Create widget in `srcProject/widgets/[DOMAIN]/[FEATURE]/`
   - Implement Form.tsx, mappers.ts, and necessary components
   - Add routes in `srcProject/layout/[MODULE]/`
   - Add i18n translations (en.json, fr.json)

4. **Configure & Test:**
   - Set SERVER_URL in app-properties to point to dev environment
   - Use Playwright MCP server to run and validate the app
   - Verify all functionality works as specified

#### Step 7: Write Tests for the Page

Once the page is implemented and validated, add test coverage for the changed code **before** the review step (which runs later in `/oc-commit`):

- Use the **oc-fe-test-writer** sub-agent (via Task tool with `subagent_type: oc-fe-test-writer:oc-fe-test-writer`)
- Pass it the [BASE-BRANCH] so it can compute the diff, plus the list of files created for the page (Form.tsx, mappers.ts, components, hooks)
- The agent will:
  - Inspect the git diff to find the changed React/TypeScript source files
  - Write or update Vitest `*.spec.tsx` / `*.spec.ts` tests following project conventions (FormWrapper, renderWithApp, MSW)
  - Run Vitest to verify the new tests pass
- Present the agent's report (test files created/updated and the run result) to the user
- If the agent surfaces a real defect in the page, address it before continuing

#### Step 8: Mark the Ticket as Handled by the Frontend AI Dev

Once the page is implemented and tested, add the tag `frontend_dev` to the JIRA **AI field** (`customfield_10613`) to record that the frontend AI dev developed the ticket.

**Never overwrite `customfield_10613` — always append.** It is a **multi-value labels field (an array of strings)** shared with the other AI commands (`ai_code_review_Front`, `ai_code_review_back`, `ai_Dev_back`, `ai_test_back_dev`, …). Sending a single-select `{ "value": … }` object, a bare string, or a one-element array **replaces the whole field and destroys the other tags**.

1. **Read first** — `getJiraIssue` (official `atlassian` plugin) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]` (treat `null` / missing as `[]`).
2. If `frontend_dev` is already in `[CURRENT-TAGS]`, skip the write and note "already tagged".
3. Otherwise call `editJiraIssue` with **every** existing value plus the new one:
   - `issueIdOrKey`: [TICKET-NUMBER]
   - `fields`: `{ "customfield_10613": ["frontend_dev", <...CURRENT-TAGS>] }`

   Expand `<...CURRENT-TAGS>` into the actual strings you read — every one of them must survive, including tags you don't recognise. Never drop or rename a tag you did not add.
4. **If the read fails, do not write** — a blind write would clobber the field. Warn the user and skip the tagging.
5. If the update fails, warn the user but continue.

## Examples

```bash
# Create UI page for ticket INTRD-36922, branching from dev
/oc-fe-create-ui INTRD-36922 dev

# Create UI page for ticket INTRD-36896, branching from master
/oc-fe-create-ui INTRD-36896 master

# Create UI page for ticket INTRD-37000, branching from a release branch
/oc-fe-create-ui INTRD-37000 release/18.0
```

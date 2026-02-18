---
name: oc-create-ui
description: Create UI page from JIRA ticket ID
argument-hint: <TICKET-ID> <BASE-BRANCH> (e.g., INTRD-36922 dev)
---

<!-- Reference ticket for workflow validation: INTRD-36896 -->

## Sub-agent Configuration

Use the `frontend-engineer` sub-agent (via Task tool with `subagent_type: frontend-engineer`) to execute the development workflow. Pass the ticket requirements and project context to the agent.

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
- If found and `cachedAt` is less than 1 hour old:
  - Use cached data directly
  - Display: "Using cached data for [TICKET-NUMBER]"
  - Extract [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME] from cache
- If not found or cache is stale, proceed to Step 2

#### Step 2: Fetch from Atlassian (if not cached)

- Connect to JIRA using the Atlassian MCP server
- Get the issue type, summary, and assignee
- Store them in [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME]

#### Step 3: Update Cache

- If data was fetched from Atlassian, update the cache:
  - Read existing cache (or create empty structure)
  - Add/update the ticket data with current timestamp
  - Write back to `.claude/cache/jira-tickets.json`
  - Display: "Cached ticket data for future use"

#### Step 4: Continue with ticket data

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

#### Step 5: Create the Portal Page

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

## Examples

```bash
# Create UI page for ticket INTRD-36922, branching from dev
/oc-create-ui INTRD-36922 dev

# Create UI page for ticket INTRD-36896, branching from master
/oc-create-ui INTRD-36896 master

# Create UI page for ticket INTRD-37000, branching from a release branch
/oc-create-ui INTRD-37000 release/18.0
```

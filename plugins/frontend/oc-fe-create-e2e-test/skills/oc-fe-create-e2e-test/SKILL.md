---
name: oc-fe-create-e2e-test
description: Create Playwright E2E tests from JIRA ticket requirements
argument-hint: <TICKET-ID> <BASE-BRANCH> (e.g., INTRD-36922 dev)
---

## Sub-agent Configuration

Use the `oc-fe-e2e-expert` sub-agent (via Task tool with `subagent_type: oc-fe-create-e2e-test:oc-fe-e2e-expert`) to execute the E2E test creation workflow. Pass the ticket requirements and project context to the agent.

## Context

Parse the $ARGUMENTS to get the following parameters:

**Required Parameters:**

1. **[TICKET-NUMBER]**: JIRA ticket ID (format: `INTRD-XXXXX`)

   - First argument in $ARGUMENTS
   - Example: `INTRD-36922`

2. **[BASE-BRANCH]**: The base branch from which the test branch will be created
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

### GET JIRA TICKET DATA AND PREPARE E2E TEST ENVIRONMENT

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
- Get the issue type, summary, assignee, and acceptance criteria
- Store them in [TICKET-TYPE], [TICKET-SUMMARY], [USERNAME], and [ACCEPTANCE-CRITERIA]

#### Step 3: Update Cache

- If data was fetched from Atlassian, update the cache:
  - Read existing cache (or create empty structure)
  - Add/update the ticket data with current timestamp
  - Write back to `.claude/cache/jira-tickets.json`
  - Display: "Cached ticket data for future use"

#### Step 4: Rename Session

- Rename the current Claude session to the ticket ID using the `/rename` slash command:
  - Run: `/rename [TICKET-NUMBER]-e2e`
- This allows easy identification of the session in the status line and when resuming later

#### Step 5: Continue with ticket data

- The ticket data is now available from either cache or fresh fetch

- Display all extracted parameters in key-value format:

  ```
  TICKET-NUMBER:      [TICKET-NUMBER]
  TICKET-TYPE:        [TICKET-TYPE]
  TICKET-SUMMARY:     [TICKET-SUMMARY]
  BASE-BRANCH:        [BASE-BRANCH]
  USERNAME:           [USERNAME]
  ACCEPTANCE-CRITERIA:[ACCEPTANCE-CRITERIA]
  ```

- **Create Test Branch:**

  - Use [BASE-BRANCH] as the source branch
  - Branch naming: `test/[TICKET-NUMBER]` (e.g., `test/INTRD-36922`)
  - Only create if branch does not already exist
  - If branch already exists, checkout the existing branch
  - If branch creation fails, report error and stop execution

### CREATE PLAYWRIGHT E2E TESTS

#### Step 6: Analyze the Feature Under Test

1. **Read JIRA ticket details:**
   - Extract the GUI specifications and acceptance criteria
   - Identify the feature's domain (B2B, CPQ, finance, etc.)
   - List all user flows that need test coverage

2. **Read the feature source code:**
   - Locate the feature implementation in `srcProject/widgets/[DOMAIN]/[FEATURE]/`
   - Identify key components, forms, data grids, and user interactions
   - Map API endpoints used by the feature from `src/services/`
   - Note `data-testid` attributes already present in the components

3. **Check existing tests:**
   - Look for existing Playwright tests in `tests/e2e/[DOMAIN]/`
   - Identify reusable page objects in `tests/pages/`
   - Check for existing fixtures in `tests/fixtures/`
   - Avoid duplicating existing test coverage

#### Step 7: Create Test Artifacts

1. **Create Page Object (if not exists):**
   - Create `tests/pages/[Feature]Page.ts`
   - Define locators using `getByTestId`, `getByRole`, `getByLabel`, `getByText`
   - Add methods for common user interactions on the page
   - Follow the Page Object Model pattern from the agent guidelines

2. **Create Test Fixtures:**
   - Create `tests/fixtures/[DOMAIN]/[FEATURE].json` with mock API responses
   - Include realistic test data that covers edge cases
   - Create custom Playwright fixtures in `tests/fixtures/base.ts` if needed

3. **Create Test Spec:**
   - Create `tests/e2e/[DOMAIN]/[FEATURE].spec.ts`
   - Structure tests with `test.describe` blocks grouped by user flow
   - Use `test.step()` to document logical steps within each test
   - Cover the following scenarios:
     - **Happy path**: Complete successful user flow
     - **Form validation**: Required fields, format validation, error messages
     - **Data grid interactions**: Search, sort, filter, pagination (if applicable)
     - **CRUD operations**: Create, read, update, delete (if applicable)
     - **Error handling**: API failures, network errors, timeout scenarios
     - **Edge cases**: Empty states, boundary values, concurrent actions

4. **Mock API calls:**
   - Use `page.route()` to intercept and mock all API calls
   - Create mock responses for success and error scenarios
   - Assert on request parameters when relevant

#### Step 8: Validate Tests

1. **Run the tests:**
   - Use the Playwright MCP server to launch the application
   - Execute: `npx playwright test tests/e2e/[DOMAIN]/[FEATURE].spec.ts`
   - Verify all tests pass

2. **Review test quality:**
   - Ensure no hard-coded waits (`page.waitForTimeout()`)
   - Verify all locators use stable selectors
   - Check that tests are independent and can run in parallel
   - Confirm API mocks cover all network requests

3. **Generate report:**
   - Run: `npx playwright show-report`
   - Verify HTML report is generated with passing results

## Examples

```bash
# Create E2E tests for ticket INTRD-36922, branching from dev
/oc-fe-create-e2e-test INTRD-36922 dev

# Create E2E tests for ticket INTRD-36896, branching from master
/oc-fe-create-e2e-test INTRD-36896 master

# Create E2E tests for ticket INTRD-37000, branching from a release branch
/oc-fe-create-e2e-test INTRD-37000 release/18.0
```

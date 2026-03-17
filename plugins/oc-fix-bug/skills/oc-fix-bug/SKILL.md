---
name: oc-fix-bug
description: Fix a bug from a JIRA ticket — update status to In Progress, create fix branch, and start fixing
argument-hint: <TICKET-ID> [BASE-BRANCH] (e.g., INTRD-36922 dev)
---

## Context

Parse the $ARGUMENTS to get the following parameters:

**Required Parameters:**

1. **[TICKET-NUMBER]**: JIRA ticket ID (format: `INTRD-XXXXX`)
   - First argument in $ARGUMENTS
   - Example: `INTRD-36922`

**Optional Parameters:**

2. **[BASE-BRANCH]**: The base branch from which the fix branch will be created
   - Second argument in $ARGUMENTS
   - Default: `dev`
   - Common values: `dev`, `master`, `release/X.X`

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

### Step 1: Get JIRA Ticket Data

#### 1a. Check Local Cache First

- Read `.claude/cache/jira-tickets.json` if it exists
- Check if [TICKET-NUMBER] exists in the `tickets` object
- If found and `cachedAt` is less than 1 day old:
  - Use cached data directly
  - Display: "Using cached data for [TICKET-NUMBER]"
  - Extract [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME] from cache
- If not found or cache is stale, proceed to 1b

#### 1b. Fetch from Atlassian (if not cached)

- Connect to JIRA using the Atlassian MCP server
- Get the issue type, summary, and assignee
- Store them in [TICKET-TYPE], [TICKET-SUMMARY], and [USERNAME]

#### 1c. Update Cache

- If data was fetched from Atlassian, update the cache:
  - Read existing cache (or create empty structure)
  - Add/update the ticket data with current timestamp
  - Write back to `.claude/cache/jira-tickets.json`
  - Display: "Cached ticket data for future use"

#### 1d. Display ticket info

- Display all extracted parameters in key-value format:

  ```
  TICKET-NUMBER:  [TICKET-NUMBER]
  TICKET-TYPE:    [TICKET-TYPE]
  TICKET-SUMMARY: [TICKET-SUMMARY]
  BASE-BRANCH:    [BASE-BRANCH]
  USERNAME:       [USERNAME]
  ```

### Step 2: Update JIRA Status to In Progress

- Using the Atlassian MCP server, transition the ticket [TICKET-NUMBER] to **"In Progress"**
  - First call `getTransitionsForJiraIssue` to get available transitions
  - Find the transition that moves to "In Progress" status
  - Call `transitionJiraIssue` with the correct transition ID
- If the ticket is already "In Progress", skip and inform the user
- If the transition fails, warn the user but continue with the next steps

### Step 3: Create Fix Branch

- Fetch the latest changes: `git fetch origin`
- Create the fix branch from [BASE-BRANCH]:
  - Follow naming convention in [CODE_QUALITY.md](../../CODE_QUALITY.md/#branch-naming)
  - The branch type should be `bugfix` since this is a bug fix
  - Only create if branch does not already exist
  - If branch already exists, checkout the existing branch
- Ask the user which branch to use for development and propose:
  - ( ) The branch you will create based on the naming conventions
  - ( ) Free input from the user: "Enter branch name:"
- If branch creation fails, report error and stop execution

### Step 4: Start Fixing

- Read the JIRA ticket description and acceptance criteria from the ticket data
- Analyze the bug report to understand:
  - What is the expected behavior
  - What is the actual behavior
  - Steps to reproduce (if available)
- Start investigating and fixing the bug in the codebase

## Examples

```bash
# Fix bug for ticket INTRD-36922, branching from dev (default)
/oc-fix-bug INTRD-36922

# Fix bug for ticket INTRD-36896, branching from master
/oc-fix-bug INTRD-36896 master

# Fix bug for ticket INTRD-37000, branching from a release branch
/oc-fix-bug INTRD-37000 release/18.0
```

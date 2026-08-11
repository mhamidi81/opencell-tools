---
name: oc-fe-fix-bug
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

- Connect to JIRA using the official Atlassian Rovo MCP (`atlassian@claude-plugins-official`) — call `getJiraIssue` with `issueIdOrKey`. Tool names are bare, so they also resolve against the claude.ai Atlassian connector.
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

### Step 2: Rename Session

- Rename the current Claude session to the ticket ID using the `/rename` slash command:
  - Run: `/rename [TICKET-NUMBER]`
- This allows easy identification of the session in the status line and when resuming later

### Step 3: Update JIRA Status to In Progress

- Using the official Atlassian Rovo MCP, transition the ticket [TICKET-NUMBER] to **"In Progress"**
  - First call `getTransitionsForJiraIssue` to get available transitions
  - Find the transition that moves to "In Progress" status
  - Call `transitionJiraIssue` with the correct transition ID
- If the ticket is already "In Progress", skip and inform the user
- If the transition fails, warn the user but continue with the next steps

### Step 4: Create Fix Branch

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

### Step 4b: Set Up the AI-Stats Run Directory

This makes the AI's work measurable by `/oc-fe-calculate-ai-use` later. **A sub-agent's `Write`/`Edit` calls never appear in this session's transcript and are lost when the sub-agent finishes** — the manifests and snapshots written into this directory are the only record of them.

- Define `[RUN_ID]` = `{TICKET-NUMBER}-{yyyymmdd-HHMMSS}` (timestamp via `date -u +%Y%m%d-%H%M%S`).
- Create `.claude/cache/ai-stats/[RUN_ID]/` (it is git-ignored).
- Pass a manifest path inside this directory to **every** sub-agent you dispatch below.
- Cheap and non-blocking: if it fails, continue the fix normally.

### Step 5: Start Fixing

- Read the JIRA ticket description and acceptance criteria from the ticket data
- Analyze the bug report to understand:
  - What is the expected behavior
  - What is the actual behavior
  - Steps to reproduce (if available)
- Start investigating and fixing the bug in the codebase

**Record the analysis effort (best-effort, non-blocking).** If you presented an analysis or a fix approach to the developer before editing code — in plan mode or in prose — write `.claude/cache/ai-stats/[RUN_ID]/_planning.json` once they approve it. This work produces no committed code and is invisible to a line-based metric, so this file is what lets `/oc-fe-calculate-ai-use` credit it:

```json
{
  "type": "planning",
  "agent": "oc-fe-fix-bug",
  "phase": "planning",
  "ticket": "[TICKET-NUMBER]",
  "run_id": "[RUN_ID]",
  "planning_started": "<ISO-8601 UTC when you started reading the ticket>",
  "plan_approved": "<ISO-8601 UTC now>",
  "revision_rounds": <times you presented the approach; 1 if approved first try, +1 per requested revision>,
  "plan_word_count": <word count of the approved approach>,
  "plan_text": "<the approved approach, verbatim>",
  "notes": "<1-2 lines: the root cause and the decision taken with the developer>"
}
```

If you fixed the bug directly with no approach presented, skip this file — the analyzer reconstructs the planning window from the transcript.

**If you delegate the fix to the `oc-fe-engineer` sub-agent**, add this line to its dispatch prompt:

> "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/component.json` per your manifest instructions, then snapshot your first pass to `snapshots/component.diff`."

Your own edits in this (main) context need no manifest — the session transcript already captures them, and `/oc-fe-calculate-ai-use` reports them separately as the post-review fix contribution.

### Step 6: Write Tests for the Fix

Once the fix is implemented, add test coverage for the changed code **before** the review step (which runs later in `/oc-commit`):

- Use the **oc-fe-test-writer** sub-agent (via Task tool with `subagent_type: oc-fe-test-writer:oc-fe-test-writer`)
- Pass it the [BASE-BRANCH] so it can compute the diff, plus the list of files you changed while fixing the bug
- Add to its dispatch prompt: "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/tests.json` per your manifest instructions, then snapshot your first pass to `snapshots/tests.diff`."
- The agent will:
  - Inspect the git diff to find the changed React/TypeScript source files
  - Write or update Vitest `*.test.tsx` / `*.test.ts` tests following project conventions — the portal's `vitest.config.ts` only collects `src/**/*.test.{ts,tsx,js,jsx}`, so a `.spec.*` file would never run
  - Run Vitest to verify the new tests pass
- Present the agent's report (test files created/updated and the run result) to the user
- If the agent surfaces a real defect in the fix, address it before continuing
- If there is no meaningfully testable change, note this and continue

**Verify each agent's snapshot before you touch its files.** After every sub-agent returns, check that `.claude/cache/ai-stats/[RUN_ID]/snapshots/<phase>.diff` exists. If it is missing (an older agent, or it skipped the step), capture it yourself **immediately, before applying any review fixes**, from the manifest's file list:

```bash
mkdir -p .claude/cache/ai-stats/[RUN_ID]/snapshots
git add -N -- <files from <phase>.json>   # REQUIRED: git diff HEAD ignores untracked files,
                                          # so created files would otherwise produce no diff at all
git diff HEAD -- <files from <phase>.json> > .claude/cache/ai-stats/[RUN_ID]/snapshots/<phase>.diff
```

Do the fallback before your own edits so the snapshot reflects the AI's initial output, not your fixes — otherwise the snapshot equals the final code and retention is a meaningless 100%. Best-effort and non-blocking.

### Step 7: Mark the Ticket as Handled by the Frontend AI Dev

Once the bug is fixed, add the tag `ai_Dev_Front` to the JIRA **AI field** (`customfield_10613`) to record that the frontend AI dev addressed the ticket.

**Never overwrite `customfield_10613` — always append.** It is a **multi-value labels field (an array of strings)** shared with the other AI commands (`ai_code_review_Front`, `ai_code_review_back`, `ai_Dev_back`, `ai_test_back_dev`, …). Sending a single-select `{ "value": … }` object, a bare string, or a one-element array **replaces the whole field and destroys the other tags**.

1. **Read first** — `getJiraIssue` (official `atlassian` plugin) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]` (treat `null` / missing as `[]`).
2. If `ai_Dev_Front` is already in `[CURRENT-TAGS]`, skip the write and note "already tagged".
3. Otherwise call `editJiraIssue` with **every** existing value plus the new one:
   - `issueIdOrKey`: [TICKET-NUMBER]
   - `fields`: `{ "customfield_10613": ["ai_Dev_Front", <...CURRENT-TAGS>] }`

   Expand `<...CURRENT-TAGS>` into the actual strings you read — every one of them must survive, including tags you don't recognise. Never drop or rename a tag you did not add.
4. **If the read fails, do not write** — a blind write would clobber the field. Warn the user and skip the tagging.
5. If the update fails, warn the user but continue.

### Step 8: Point to the AI-Usage Measurement

Remind the user, once the fix is committed, that they can run **`/oc-fe-calculate-ai-use`** to record AI-usage stats on the ticket. It reads the manifests and snapshots in `.claude/cache/ai-stats/[RUN_ID]/` (so sub-agent work and the analysis effort are attributed) plus this session's transcript (for your own edits), and reports contribution/retention per artifact category alongside the Vitest counts.

## Examples

```bash
# Fix bug for ticket INTRD-36922, branching from dev (default)
/oc-fe-fix-bug INTRD-36922

# Fix bug for ticket INTRD-36896, branching from master
/oc-fe-fix-bug INTRD-36896 master

# Fix bug for ticket INTRD-37000, branching from a release branch
/oc-fe-fix-bug INTRD-37000 release/18.0
```

---
name: oc-fe-fix-pr
description: Fix the review remarks of a pull request — read the PR's unresolved comments from Bitbucket, fix them on the PR's own branch via the oc-fe-engineer agent, write tests, then reply, resolve, and push
argument-hint: <PR-ID | TICKET-ID> (e.g., 123 or INTRD-36922)
---

## Purpose

Address the reviewer feedback on a pull request. Given a PR id (or a JIRA ticket whose PR can be found on Bitbucket), this skill reads the **unresolved** review comments via the Bitbucket MCP, checks out the **same branch** used by the PR, fixes each remark with the `oc-fe-engineer` agent, adds test coverage, commits and pushes to the PR branch, sets the JIRA AI field (`customfield_10613`) to `frontend_dev`, then replies to and resolves each addressed comment on Bitbucket.

This is a **frontend** skill targeting the `opencell-portal` repository.

## Context

Parse the `$ARGUMENTS` to determine the target PR:

- **[PR-ID]** — if `$ARGUMENTS` is purely numeric (e.g. `123`), treat it as the Bitbucket pull request id directly.
- **[TICKET-NUMBER]** — if `$ARGUMENTS` matches a JIRA ticket pattern (e.g. `INTRD-36922`), treat it as a ticket id and resolve its PR on Bitbucket (Step 3, Option B).

**Validation:**

- If `$ARGUMENTS` is empty or matches neither a numeric PR id nor a `XXX-NNNNN` ticket pattern, stop and ask the user for a valid PR id or JIRA ticket id.

## Tasks

### Step 1: Detect Repository Info

- Run `git remote get-url origin` to get the remote URL.
- Extract [REPO-OWNER] and [REPO-NAME] from the remote URL.
- If the URL does not contain `bitbucket.org`:
  - Inform the user: "This command currently supports Bitbucket repositories only."
  - Stop execution.
- This skill targets `opencell-portal`. If the remote is not `opencell-portal`, warn the user that this is a frontend skill but continue (the flow still works for any Bitbucket repo).

### Step 2: Resolve the JIRA Ticket (only when a ticket id was given)

Skip this step entirely if `$ARGUMENTS` was a numeric [PR-ID].

- Read `.claude/cache/jira-tickets.json` and look for [TICKET-NUMBER] in the `tickets` object.
- If found, extract the `summary` field and store it as [TICKET-SUMMARY].
- If NOT found in cache:
  - Automatically run `/oc-cache-jira [TICKET-NUMBER]` to fetch and cache the ticket data (do NOT ask the user for confirmation — proceed directly).
  - After caching completes, re-read `.claude/cache/jira-tickets.json` and extract the `summary` field as [TICKET-SUMMARY].
  - If caching fails or the ticket is still not found, inform the user and stop execution.

### Step 3: Resolve the Pull Request

Fetch the PR metadata from Bitbucket. Prefer the MCP server; fall back to curl.

**Option A — PR id was given directly**

- Use `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_get` to fetch the PR:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]
  ```

**Option B — A ticket was given (find its PR)**

- Search for a pull request whose title references the ticket:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~"[TICKET-NUMBER]"&state=OPEN
  ```

- If no open PR is found, also try `state=MERGED` and `state=DECLINED`.
- Use the first matching result and set [PR-ID] from its `id` field.

**Fallback with curl** (when MCP is unavailable but `BITBUCKET_ACCESS_TOKEN` is set):

```bash
# By PR id
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]"

# By ticket
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~%22[TICKET-NUMBER]%22&state=OPEN"
```

Extract and store from the PR object:

- [PR-ID]: `id`
- [PR-TITLE]: `title`
- [PR-URL]: `links.html.href`
- [PR-SOURCE-BRANCH]: `source.branch.name`
- [PR-DEST-BRANCH]: `destination.branch.name`
- [PR-AUTHOR]: `author.display_name`
- [PR-STATE]: `state`

If no PR can be resolved, inform the user ("No pull request found for [PR-ID / TICKET-NUMBER]") and stop execution.

### Step 4: Check Out the PR Branch

Work happens on the **same branch** used by the PR — never a new branch.

- `git fetch origin`
- `git checkout [PR-SOURCE-BRANCH]`
- `git pull origin [PR-SOURCE-BRANCH]` to get the latest commits
- If the working tree has uncommitted changes that would be overwritten by checkout, stop and ask the user how to proceed (stash / discard).
- Confirm the active branch with `git rev-parse --abbrev-ref HEAD` and verify it equals [PR-SOURCE-BRANCH].

### Step 5: Fetch Unresolved Review Comments

- Use `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_get` to list the PR comments:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments?pagelen=100
  ```

- Page through all results if `next` is present.
- **Filter the comments** — keep only the actionable remarks:
  - Exclude comments where `deleted` is `true`.
  - Exclude comments whose `resolution` is non-null (already resolved).
  - Exclude system-generated comments (those without `content.raw`).
- For each remaining comment, capture into [REMARKS]:
  - [COMMENT-ID]: `id`
  - [COMMENT-AUTHOR]: `user.display_name`
  - [COMMENT-FILE]: `inline.path` (if present — inline/code comment)
  - [COMMENT-LINE]: `inline.to` or `inline.from` (if present)
  - [COMMENT-TEXT]: `content.raw`

**Fallback with curl:**

```bash
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments?pagelen=100"
```

If there are no unresolved comments, inform the user ("No unresolved review comments on PR #[PR-ID] — nothing to fix.") and stop.

### Step 6: Display PR & Remarks Overview

Show the user a quick overview before fixing:

```
Fix PR Remarks
==============

PR:        #[PR-ID] — [PR-TITLE]
Author:    [PR-AUTHOR]
Branch:    [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]  (checked out)
State:     [PR-STATE]
URL:       [PR-URL]
Remarks:   [number of unresolved comments] to address

Unresolved remarks:
  1. [COMMENT-FILE]:[COMMENT-LINE] — [first line of COMMENT-TEXT]
  2. ...

Starting fixes...
```

### Step 7: Fix the Remarks

Delegate the code changes to the **oc-fe-engineer** sub-agent (via the Task tool with `subagent_type: oc-fe-engineer:oc-fe-engineer`).

For each remark (or batched logically by file), pass the agent:

- The remark text [COMMENT-TEXT] and its location [COMMENT-FILE]:[COMMENT-LINE].
- Context: "This is reviewer feedback on PR #[PR-ID] ([PR-TITLE]). Apply the requested change on the current branch ([PR-SOURCE-BRANCH])."
- Instruction: "Implement the fix for this review remark following the OpenCell Portal frontend conventions. Edit the relevant file(s) directly. If the remark is a question, not actionable, or already addressed, do not change code — explain why instead."

Track for each remark whether it resulted in a code change ([ACTION] = `Fixed` / `Skipped — <reason>`) and the files touched. Keep this mapping for Steps 9 and 10.

### Step 8: Write Tests for the Fixes

Once the fixes are implemented, add test coverage for the changed code:

- Use the **oc-fe-test-writer** sub-agent (via the Task tool with `subagent_type: oc-fe-test-writer:oc-fe-test-writer`).
- Pass it [PR-DEST-BRANCH] as the base branch (so it can compute the diff) plus the list of files changed in Step 7.
- The agent inspects the diff, writes/updates Vitest `*.spec.tsx` / `*.spec.ts` tests, and runs Vitest to verify they pass.
- Present the agent's report (tests created/updated and the run result).
- If the agent surfaces a real defect in a fix, address it before continuing.
- If there is no meaningfully testable change, note this and continue.

### Step 9: Commit & Push to the PR Branch

Commit the fixes to [PR-SOURCE-BRANCH] and push so the PR updates.

- If a [TICKET-NUMBER] is known, run `/oc-commit [TICKET-NUMBER]` (which runs the reviewer agent and commits with the ticket convention).
- Otherwise, stage the changes and create a commit referencing the PR (e.g. `Address review remarks on PR #[PR-ID]`).
- Push to the PR branch: `git push origin [PR-SOURCE-BRANCH]`.
- If the push is rejected because the remote branch advanced, run `git pull --rebase origin [PR-SOURCE-BRANCH]` and push again.
- Confirm the push succeeded before proceeding (the reply/resolve steps should reflect pushed changes).

### Step 10: Mark the Ticket as Handled by the Frontend AI Dev

Once at least one remark was `Fixed` in Step 7 and the changes are pushed, set the JIRA **AI field** (`customfield_10613`) to `frontend_dev` to record that the frontend AI dev addressed the review.

**Resolve the ticket id first:**

- If a [TICKET-NUMBER] is already known (Step 2 ran because a ticket was given), use it.
- If only a numeric [PR-ID] was given, try to derive the ticket id by matching the `XXX-NNNNN` pattern in [PR-TITLE] or [PR-SOURCE-BRANCH] (e.g. `bugfix/INTRD-36922-...` → `INTRD-36922`).
- If no ticket id can be resolved, skip this step and note it in the final report.

**Skip conditions:**

- Skip if no remark was actually `Fixed` in Step 7 (nothing was changed).
- Skip if no ticket id could be resolved.

**Set the field** using the Atlassian MCP server (`editJiraIssue`):

- `issueIdOrKey`: [TICKET-NUMBER]
- `fields`: `{ "customfield_10613": { "value": "frontend_dev" } }`

`customfield_10613` is a single-select field. Always pass the option in the **value format** — `{ "value": "frontend_dev" }`. Do not substitute an option `id` or a bare string.

If the update fails, warn the user but continue (do not abort the reply/resolve steps).

### Step 11: Reply To and Resolve Each Addressed Comment

For every remark marked `Fixed` in Step 7:

1. **Reply** under the original comment using `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_post`:

   ```
   endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments
   body: {
     "content": { "raw": "Fixed in the latest push: [short summary of the change]." },
     "parent": { "id": [COMMENT-ID] }
   }
   ```

2. **Resolve** the comment thread using `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_post`:

   ```
   endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments/[COMMENT-ID]/resolve
   ```

For remarks marked `Skipped`, reply with the explanation instead and **do not** resolve them (leave them open for the reviewer).

**Fallback with curl:**

```bash
# Reply
curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"content":{"raw":"Fixed in the latest push: ..."},"parent":{"id":[COMMENT-ID]}}' \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments"

# Resolve
curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments/[COMMENT-ID]/resolve"
```

### Step 12: Final Report

Present a summary:

```markdown
## PR #[PR-ID] — Remarks Addressed

**Branch:** [PR-SOURCE-BRANCH] (pushed)
**PR:** [PR-URL]

| # | File:Line | Remark | Action |
|---|-----------|--------|--------|
| 1 | [COMMENT-FILE]:[COMMENT-LINE] | [short remark] | Fixed / Skipped — reason |
| ... |

**Tests:** [oc-fe-test-writer result — files + pass/fail]
**Commit:** [commit hash / message]
**JIRA AI field:** [customfield_10613 set to `frontend_dev` on TICKET-NUMBER / skipped — reason]
**Comments:** [N replied & resolved], [M left open]

The PR has been updated. Review the remaining open remarks (if any) at [PR-URL].
```

## Examples

```bash
# Fix the unresolved review remarks on PR #842 (repo auto-detected)
/oc-fe-fix-pr 842

# Resolve the PR for a JIRA ticket, then fix its review remarks
/oc-fe-fix-pr INTRD-36922

# The skill will:
# 1. Detect the Bitbucket repo from git remote
# 2. Resolve the PR (by id, or by finding the ticket's PR)
# 3. Check out the PR's source branch
# 4. Read the unresolved review comments
# 5. Fix each remark with the oc-fe-engineer agent
# 6. Write Vitest tests for the changes (oc-fe-test-writer)
# 7. Commit and push to the PR branch
# 8. Set the JIRA AI field (customfield_10613) to frontend_dev
# 9. Reply to and resolve each addressed comment on Bitbucket
```

---
name: oc-review-pr
description: Review the pull request linked to a JIRA ticket — frontend (opencell-portal) PRs are reviewed here with oc-fe-reviewer; backend (opencell-core) PRs are delegated to the /oc-be-review command.
argument-hint: <TICKET-ID> (e.g., INTRD-36922)
---

## Purpose

Review the pull request associated with a JIRA ticket. This command resolves the ticket → its PR, then routes by repository:

- **opencell-portal (frontend)** → reviewed **here** with the `oc-fe-reviewer:oc-fe-reviewer` agent, producing a formatted report and marking the ticket reviewed.
- **opencell-core (backend)** → **not reviewed here.** This command hands off to the **`/oc-be-tools:oc-be-review`** command, which owns the backend review (the `oc-be-pr-reviewer` agent + guidelines), the confirm-first PR comment and verdict, and the `ai_code_review_back` Jira tag. Keeping a single backend owner avoids two divergent backend-review paths.

## Context

Parse `$ARGUMENTS` to get:

- `[TICKET-NUMBER]`: JIRA ticket ID from `$ARGUMENTS`.

## Tasks

### 1. Get ticket data from cache

- Read `.claude/cache/jira-tickets.json`.
- Look for `[TICKET-NUMBER]` in the `tickets` object; if found, extract `summary` as `[TICKET-SUMMARY]`.
- If NOT found in cache:
  - Automatically run `/oc-cache-jira [TICKET-NUMBER]` to fetch and cache the ticket (do NOT ask for confirmation — proceed directly).
  - Re-read the cache and extract `summary` as `[TICKET-SUMMARY]`.
  - If caching fails or the ticket is still not found, inform the user and stop.

### 2. Detect repository info

- Run `git remote get-url origin` to get the remote URL.
- Extract `[REPO-OWNER]` and `[REPO-NAME]`.
- If the URL does not contain `bitbucket.org`, inform the user "This command currently supports Bitbucket repositories only." and stop.

### 3. Route by repository

- If the remote URL contains **`opencell-core`** → **backend**: go to **Backend — delegate to `/oc-be-review`** and do **not** run any of the frontend steps (4 onward).
- If the remote URL contains **`opencell-portal`** → **frontend**: set `[REVIEWER-AGENT]` = `oc-fe-reviewer:oc-fe-reviewer`, `[REVIEWER-LABEL]` = `oc-fe-reviewer`, and continue with the frontend steps below.
- Otherwise → inform the user "Unsupported repository. This command supports opencell-portal and opencell-core repositories only." and stop.

---

## Backend — delegate to `/oc-be-review`

When the repository is **opencell-core**, this command does not review backend code itself. Resolve the PR for the ticket, then hand off to `/oc-be-tools:oc-be-review`:

1. **Find the PR** for `[TICKET-NUMBER]` (see **Bitbucket Access** below), reproducing Bitbucket's "Jira work item" detection — search in order and take the first match:
   - by title: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~"[TICKET-NUMBER]"&state=OPEN` (then `state=MERGED`, `state=DECLINED`);
   - if none, by source branch containing the key: `...pullrequests?q=source.branch.name~"[TICKET-NUMBER]"`.
   - Store the matched `id` as `[PR-ID]`.
2. **Delegate**:
   - If a `[PR-ID]` was found → run **`/oc-be-tools:oc-be-review [PR-ID]`** and stop. That command fetches the diff, runs `oc-be-pr-reviewer`, adds a SonarQube quality-gate summary, and — after your confirmation — posts the review comment, sets the verdict, and tags the ticket `ai_code_review_back` on `customfield_10613`.
   - If no PR was found → tell the user "No pull request found for [TICKET-NUMBER]" and suggest **`/oc-be-tools:oc-be-review list`** to pick one manually (or `/oc-be-tools:oc-be-review` to review local uncommitted changes). Stop.

> This command performs **no** Jira write and **no** Bitbucket write on the backend path — everything outward-facing is done by `/oc-be-review`, under its own confirmation.

---

> The remaining steps (4–10) apply to the **frontend** path (opencell-portal) only.

### 4. Find the pull request for the ticket (frontend)

Search for a PR related to `[TICKET-NUMBER]` (see **Bitbucket Access**):

```bash
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~%22[TICKET-NUMBER]%22&state=OPEN"
```

- If no open PR is found, also try `state=MERGED` and `state=DECLINED`, then a source-branch search (`q=source.branch.name~"[TICKET-NUMBER]"`).
- Extract from the first match: `[PR-ID]` (`id`), `[PR-TITLE]` (`title`), `[PR-URL]` (`links.html.href`), `[PR-SOURCE-BRANCH]` (`source.branch.name`), `[PR-DEST-BRANCH]` (`destination.branch.name`), `[PR-AUTHOR]` (`author.display_name`), `[PR-STATE]` (`state`).
- If no PR is found at all, inform the user "No pull request found for [TICKET-NUMBER]" and stop.

### 5. Fetch the PR diff (frontend)

```bash
# diff
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff"
# changed files
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diffstat"
```

- Store the diff as `[PR-DIFF]` and the changed file paths as `[CHANGED-FILES]`.

### 6. Display PR overview

```
Pull Request Review
====================

Ticket:    [TICKET-NUMBER] — [TICKET-SUMMARY]
PR:        #[PR-ID] — [PR-TITLE]
Author:    [PR-AUTHOR]
Branch:    [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
State:     [PR-STATE]
URL:       [PR-URL]
Files:     [number of changed files] files changed
Reviewer:  [REVIEWER-LABEL] (frontend)

Starting review...
```

### 7. Run the code review (frontend)

Use the `oc-fe-reviewer:oc-fe-reviewer` agent to perform a comprehensive review. Pass:

- The full `[PR-DIFF]` content.
- The list of `[CHANGED-FILES]`.
- Context: "This is a PR review for [TICKET-NUMBER]: [TICKET-SUMMARY]".
- Instruction: "Review the following pull request diff. Focus on the changed code only. For each issue found, provide the exact file path and line context. Suggest concrete fixes with code snippets."

The reviewer should evaluate: TypeScript quality and type safety; React component patterns; state management; import conventions and path aliases; naming conventions; widget structure; API usage patterns; i18n completeness (EN + FR); testing coverage; accessibility; performance; error handling; security.

### 8. Generate the review report

Compile the results into a well-structured report:

```markdown
╔══════════════════════════════════════════════════════════════╗
║                    PR REVIEW REPORT                         ║
╚══════════════════════════════════════════════════════════════╝

## [TICKET-NUMBER]: [TICKET-SUMMARY]
**PR #[PR-ID]** — [PR-TITLE]
**Author:** [PR-AUTHOR] | **Branch:** [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
**Reviewer:** [REVIEWER-LABEL]

---

### Overall Score: X/10  [SCORE-BADGE]

Where [SCORE-BADGE] is:
- 9-10: "Excellent — Ready to merge"
- 7-8:  "Good — Minor improvements suggested"
- 5-6:  "Needs Work — Several issues to address"
- 3-4:  "Significant Issues — Major rework needed"
- 1-2:  "Critical — Do not merge"

---

### Summary

[2-3 sentence overview of the PR quality, what it does well, and main areas for improvement]

---

### Critical Issues (Must Fix Before Merge)

> These issues must be resolved before the PR can be approved.

**[ISSUE-NUMBER]. [Issue Title]**
- **File:** `[file-path]`
- **Problem:** [Clear description]
- **Impact:** [Why this matters]
- **Suggested Fix:**
  ```
  // Before (current code)
  [problematic code snippet]

  // After (suggested fix)
  [corrected code snippet]
  ```

---

### Warnings (Should Fix)

> These won't block the merge but should be addressed for code quality.

**[WARNING-NUMBER]. [Warning Title]**
- **File:** `[file-path]`
- **Issue:** [Description]
- **Suggestion:**
  ```
  [suggested improvement]
  ```

---

### Suggestions (Nice to Have)

- **[file-path]**: [suggestion description]

---

### What's Done Well

- [Positive aspect 1]
- [Positive aspect 2]

---

### Review Breakdown

| Category              | Status | Notes                          |
|-----------------------|--------|--------------------------------|
| TypeScript Quality    | [status-icon] | [brief note]            |
| React Patterns        | [status-icon] | [brief note]            |
| State Management      | [status-icon] | [brief note]            |
| Import Conventions    | [status-icon] | [brief note]            |
| Naming Conventions    | [status-icon] | [brief note]            |
| Widget Structure      | [status-icon] | [brief note]            |
| API Usage             | [status-icon] | [brief note]            |
| i18n Compliance       | [status-icon] | [brief note]            |
| Testing               | [status-icon] | [brief note]            |
| Accessibility         | [status-icon] | [brief note]            |
| Performance           | [status-icon] | [brief note]            |
| Error Handling        | [status-icon] | [brief note]            |
| Security              | [status-icon] | [brief note]            |

Where [status-icon] is: PASS "Pass" | WARN "Warn" | FAIL "Fail" | N/A "N/A".

---

### Recommended Action

- **Approve**: Score 8+ with no critical issues → "This PR is ready to merge."
- **Approve with comments**: Score 6-7 with warnings only → "Approve, but address the warnings in a follow-up."
- **Request changes**: Score < 6 or any critical issue → "Please address the critical issues and re-request review."

---

*Review generated by Claude Code with [REVIEWER-LABEL]*
*PR: [PR-URL]*
```

### 9. Mark the ticket as reviewed by the frontend AI reviewer

Once the report is generated, add the tag **`ai_code_review_Front`** to the ticket's AI field (`customfield_10613`).

**`customfield_10613` is a multi-value labels field (an array of strings) — append, never overwrite, and never use the single-select `{ "value": … }` shape.**

1. Read the current value: `getJiraIssue` (Atlassian MCP) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]`.
2. If `ai_code_review_Front` is already in `[CURRENT-TAGS]`, **skip the edit** and note it.
3. Otherwise call `editJiraIssue` with the merged array of strings:
   ```json
   { "fields": { "customfield_10613": ["ai_code_review_Front", <...CURRENT-TAGS>] } }
   ```
   (`issueIdOrKey` = `[TICKET-NUMBER]`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`.)
4. If the update fails, warn the user but continue.

> This is the same field `/oc-be-review` tags with `ai_code_review_back` and `/oc-be-calculate-ai-use` tags with `ai_Dev_back` / `ai_test_back_dev`. Because it is multi-value, all of these coexist — so this step must merge, not replace.

### 10. Offer next steps

- If there are critical issues or warnings with suggested fixes:
  - "Would you like me to apply the suggested fixes automatically?" — if yes, use the `oc-fe-reviewer` agent to apply fixes to the local codebase.
- If the PR looks good:
  - "The PR looks good! You can approve it directly on Bitbucket: [PR-URL]".
- Optionally, "Would you like me to post this review as a comment on the PR?" — if yes (confirm first, it is outward-facing):
  ```bash
  curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments" \
    -d '{ "content": { "raw": "[REVIEW-SUMMARY-MARKDOWN]" } }'
  ```

---

## Bitbucket Access

This command talks to Bitbucket over its REST API with `curl`, authenticated by a Bearer access token in `BITBUCKET_ACCESS_TOKEN` (a Bitbucket repository or workspace **Access Token** — App Passwords are deprecated, removed 2026-07-28). See the **Claude code AI assistant** parent page for how to create and set the token. If `BITBUCKET_ACCESS_TOKEN` is missing or a call returns `401`, tell the user and stop (frontend path) or fall back to `/oc-be-review list` (backend path).

## Examples

```bash
# Backend ticket (opencell-core) — delegates to /oc-be-review with the discovered PR
/oc-review-pr INTRD-36922
# → detects opencell-core → finds the PR for the ticket → runs /oc-be-tools:oc-be-review <PR>

# Frontend ticket (opencell-portal) — reviewed here with oc-fe-reviewer
/oc-review-pr INTRD-41200
# → detects opencell-portal → reviews React/TypeScript, reports, tags the ticket ai_code_review_Front
```

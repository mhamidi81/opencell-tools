---
name: oc-review-pr
description: Review a pull request linked to a JIRA ticket — fetch PR from Bitbucket, run frontend review, and generate a detailed report with suggested fixes
argument-hint: <TICKET-ID> (e.g., INTRD-36922)
---

## Purpose

Review a pull request associated with a JIRA ticket by fetching the PR diff from Bitbucket, running a comprehensive code review using the `oc-frontend-reviewer` agent, and presenting a clear, meaningful, and beautifully formatted report with actionable fix suggestions.

## Context

Parse the $ARGUMENTS to get:

- [TICKET-NUMBER]: JIRA ticket ID from $ARGUMENTS

## Tasks

### 1. Get Ticket Data from Cache

- Read `.claude/cache/jira-tickets.json`
- Look for [TICKET-NUMBER] in the `tickets` object
- If found, extract `summary` field and store as [TICKET-SUMMARY]
- If NOT found in cache:
  - Automatically run `/cache-jira [TICKET-NUMBER]` to fetch and cache the ticket data (do NOT ask the user for confirmation — proceed directly)
  - After caching completes, re-read `.claude/cache/jira-tickets.json` and extract the `summary` field as [TICKET-SUMMARY]
  - If caching fails or ticket is still not found after caching, inform the user and stop execution

### 2. Detect Repository Info

- Run `git remote get-url origin` to get the remote URL
- Extract [REPO-OWNER] and [REPO-NAME] from the remote URL
- If URL does not contain `bitbucket.org`:
  - Inform user: "This command currently supports Bitbucket repositories only."
  - Stop execution

### 3. Find the Pull Request for the Ticket

Search for a pull request related to [TICKET-NUMBER] on Bitbucket:

**Option A: Use Bitbucket MCP Server (Preferred)**

- Use the `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_get` tool to search for PRs:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~"[TICKET-NUMBER]"&state=OPEN
  ```

- If no open PR found, also try with `state=MERGED` and `state=DECLINED`
- Extract from the first matching result:
  - [PR-ID]: `id` field
  - [PR-TITLE]: `title` field
  - [PR-URL]: `links.html.href` field
  - [PR-SOURCE-BRANCH]: `source.branch.name` field
  - [PR-DEST-BRANCH]: `destination.branch.name` field
  - [PR-AUTHOR]: `author.display_name` field
  - [PR-STATE]: `state` field

**Option B: Fallback with curl**

If MCP is not available but credentials are set (`BITBUCKET_ACCESS_TOKEN`):

```bash
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~%22[TICKET-NUMBER]%22&state=OPEN"
```

- If no PR is found at all:
  - Inform user: "No pull request found for [TICKET-NUMBER]"
  - Stop execution

### 4. Fetch the PR Diff

Get the full diff of the pull request to understand all changes:

**Option A: Use Bitbucket MCP Server (Preferred)**

- Use `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_get` to fetch the diff:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff
  ```

- Also fetch the list of changed files:

  ```
  endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diffstat
  ```

- Store the diff as [PR-DIFF]
- Store changed file paths as [CHANGED-FILES]

**Option B: Fallback with curl**

```bash
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff"
```

### 5. Display PR Overview

Show the user a quick overview before the review:

```
Pull Request Review
====================

Ticket:  [TICKET-NUMBER] — [TICKET-SUMMARY]
PR:      #[PR-ID] — [PR-TITLE]
Author:  [PR-AUTHOR]
Branch:  [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
State:   [PR-STATE]
URL:     [PR-URL]
Files:   [number of changed files] files changed

Starting review...
```

### 6. Run the Frontend Review

Use the `oc-frontend-reviewer` agent (subagent_type: `oc-frontend-reviewer:frontend-reviewer`) to perform a comprehensive code review.

Pass the following to the reviewer agent:

- The full [PR-DIFF] content
- The list of [CHANGED-FILES]
- Context: "This is a PR review for [TICKET-NUMBER]: [TICKET-SUMMARY]"
- Instruction: "Review the following pull request diff. Focus on the changed code only. For each issue found, provide the exact file path and line context. Suggest concrete fixes with code snippets."

The reviewer should evaluate:

- TypeScript quality and type safety
- React component patterns and best practices
- State management correctness
- Import conventions and path aliases
- Naming conventions
- Widget structure compliance
- API usage patterns
- i18n completeness (EN + FR)
- Testing coverage
- Accessibility
- Performance implications
- Error handling
- Security concerns

### 7. Generate the Review Report

Compile the review results into a beautiful, well-structured report. Use the following format:

```markdown
╔══════════════════════════════════════════════════════════════╗
║                    PR REVIEW REPORT                         ║
╚══════════════════════════════════════════════════════════════╝

## [TICKET-NUMBER]: [TICKET-SUMMARY]
**PR #[PR-ID]** — [PR-TITLE]
**Author:** [PR-AUTHOR] | **Branch:** [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
**Review Date:** [CURRENT-DATE]

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

For each critical issue:

**[ISSUE-NUMBER]. [Issue Title]**
- **File:** `[file-path]`
- **Problem:** [Clear description of the issue]
- **Impact:** [Why this matters — security, bugs, data loss, etc.]
- **Suggested Fix:**
  ```typescript
  // Before (current code)
  [problematic code snippet]

  // After (suggested fix)
  [corrected code snippet]
  ```

---

### Warnings (Should Fix)

> These won't block the merge but should be addressed for code quality.

For each warning:

**[WARNING-NUMBER]. [Warning Title]**
- **File:** `[file-path]`
- **Issue:** [Description]
- **Suggestion:**
  ```typescript
  [suggested improvement]
  ```

---

### Suggestions (Nice to Have)

> Optional improvements that would enhance the code.

For each suggestion, a concise bullet point:

- **[file-path]**: [suggestion description]

---

### What's Done Well

> Positive aspects of this PR worth highlighting.

- [Positive aspect 1]
- [Positive aspect 2]
- [Positive aspect 3]

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

Where [status-icon] is:
- PASS: "Pass"
- WARN: "Warn"
- FAIL: "Fail"
- N/A:  "N/A"

---

### Recommended Action

[One of the following based on the score:]

- **Approve**: Score 8+ with no critical issues → "This PR is ready to merge."
- **Approve with comments**: Score 6-7 with warnings only → "Approve, but address the warnings in a follow-up."
- **Request changes**: Score < 6 or any critical issue → "Please address the critical issues and re-request review."

---

*Review generated by Claude Code with oc-frontend-reviewer*
*PR: [PR-URL]*
```

### 8. Offer Next Steps

After displaying the report, offer the user actionable next steps:

- If there are critical issues or warnings with suggested fixes:
  - "Would you like me to apply the suggested fixes automatically?"
  - If user agrees, use the `oc-frontend-reviewer:frontend-reviewer` agent to apply fixes to the local codebase
- If the PR looks good:
  - "The PR looks good! You can approve it directly on Bitbucket: [PR-URL]"
- Optionally:
  - "Would you like me to post this review as a comment on the PR?"
  - If user agrees, use `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_post` to post the review summary as a PR comment:
    ```
    endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments
    body: { "content": { "raw": "[REVIEW-SUMMARY-MARKDOWN]" } }
    ```

## Examples

```bash
# Review the PR for a specific JIRA ticket
/oc-review-pr INTRD-36922

# Review will:
# 1. Find the PR associated with INTRD-36922 on Bitbucket
# 2. Fetch the full diff
# 3. Run a comprehensive frontend code review
# 4. Display a detailed report with scores, issues, and fix suggestions
# 5. Offer to apply fixes or post the review as a PR comment
```

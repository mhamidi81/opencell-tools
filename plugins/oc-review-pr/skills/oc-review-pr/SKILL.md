---
name: oc-review-pr
description: Review a pull request linked to a JIRA ticket — fetch PR from Bitbucket, select the appropriate reviewer agent based on the repository, and generate a detailed report with suggested fixes
argument-hint: <TICKET-ID> (e.g., INTRD-36922)
---

## Purpose

Review a pull request associated with a JIRA ticket by fetching the PR diff from Bitbucket, automatically selecting the correct reviewer agent based on the repository, and presenting a clear, meaningful, and beautifully formatted report with actionable fix suggestions.

**Reviewer routing:**

- **opencell-portal** (`https://bitbucket.org/opencellsoft/opencell-portal.git`) → `oc-frontend-reviewer:frontend-reviewer`
- **opencell-core** (`https://bitbucket.org/opencellsoft/opencell-core.git`) → `oc-core-reviewer:oc-core-reviewer`

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

### 3. Select the Reviewer Agent

Based on the remote URL, determine which reviewer agent to use:

- If remote URL contains `opencell-portal`:
  - Set [REVIEWER-AGENT] = `oc-frontend-reviewer:frontend-reviewer`
  - Set [REVIEWER-LABEL] = `oc-frontend-reviewer`
  - Set [REVIEW-DOMAIN] = `frontend`
  - Set [REVIEW-CATEGORIES] to the frontend categories (see Step 6)
- If remote URL contains `opencell-core`:
  - Set [REVIEWER-AGENT] = `oc-core-reviewer:oc-core-reviewer`
  - Set [REVIEWER-LABEL] = `oc-core-reviewer`
  - Set [REVIEW-DOMAIN] = `backend`
  - Set [REVIEW-CATEGORIES] to the backend categories (see Step 6)
- If neither matches:
  - Inform user: "Unsupported repository. This command supports opencell-portal and opencell-core repositories only."
  - Stop execution

### 4. Find the Pull Request for the Ticket

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

### 5. Fetch the PR Diff

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

### 6. Display PR Overview

Show the user a quick overview before the review:

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
Reviewer:  [REVIEWER-LABEL] ([REVIEW-DOMAIN])

Starting review...
```

### 7. Run the Code Review

Use the selected [REVIEWER-AGENT] agent to perform a comprehensive code review.

Pass the following to the reviewer agent:

- The full [PR-DIFF] content
- The list of [CHANGED-FILES]
- Context: "This is a PR review for [TICKET-NUMBER]: [TICKET-SUMMARY]"
- Instruction: "Review the following pull request diff. Focus on the changed code only. For each issue found, provide the exact file path and line context. Suggest concrete fixes with code snippets."

**If [REVIEW-DOMAIN] is `frontend`**, the reviewer should evaluate:

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

**If [REVIEW-DOMAIN] is `backend`**, the reviewer should evaluate:

- Jakarta EE compliance (no javax.*)
- Entity layer (base classes, field types, relationships, fetch strategies)
- Service layer (exceptions, validation placement, return values)
- API layer (BaseCrudApi, scope annotations, parameter validation)
- DTO layer (immutable, wrapper types, Resource interface)
- Mapper methods (fromDto/toDto, null vs empty handling)
- REST endpoints (CRUD paths, HTTP status codes, no try-catch)
- Liquibase changesets (ID format, both files, type mappings)
- Unit tests (Mockito patterns, EntityManager mocking, ArgumentCaptor)
- Code quality (no var, curly braces, exception handling)
- Performance (N+1 queries, fetch strategies)
- Security (SQL injection, input validation)

### 8. Generate the Review Report

Compile the review results into a beautiful, well-structured report. Use the following format:

```markdown
╔══════════════════════════════════════════════════════════════╗
║                    PR REVIEW REPORT                         ║
╚══════════════════════════════════════════════════════════════╝

## [TICKET-NUMBER]: [TICKET-SUMMARY]
**PR #[PR-ID]** — [PR-TITLE]
**Author:** [PR-AUTHOR] | **Branch:** [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
**Review Date:** [CURRENT-DATE]
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

For each critical issue:

**[ISSUE-NUMBER]. [Issue Title]**
- **File:** `[file-path]`
- **Problem:** [Clear description of the issue]
- **Impact:** [Why this matters — security, bugs, data loss, etc.]
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

For each warning:

**[WARNING-NUMBER]. [Warning Title]**
- **File:** `[file-path]`
- **Issue:** [Description]
- **Suggestion:**
  ```
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

**For frontend reviews (opencell-portal):**

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

**For backend reviews (opencell-core):**

| Category              | Status | Notes                          |
|-----------------------|--------|--------------------------------|
| Jakarta EE Compliance | [status-icon] | [brief note]            |
| Entity Layer          | [status-icon] | [brief note]            |
| Service Layer         | [status-icon] | [brief note]            |
| API Layer             | [status-icon] | [brief note]            |
| DTO Layer             | [status-icon] | [brief note]            |
| Mapper Methods        | [status-icon] | [brief note]            |
| REST Endpoints        | [status-icon] | [brief note]            |
| Liquibase             | [status-icon] | [brief note]            |
| Unit Tests            | [status-icon] | [brief note]            |
| Code Quality          | [status-icon] | [brief note]            |
| Performance           | [status-icon] | [brief note]            |
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

*Review generated by Claude Code with [REVIEWER-LABEL]*
*PR: [PR-URL]*
```

### 9. Offer Next Steps

After displaying the report, offer the user actionable next steps:

- If there are critical issues or warnings with suggested fixes:
  - "Would you like me to apply the suggested fixes automatically?"
  - If user agrees, use the [REVIEWER-AGENT] agent to apply fixes to the local codebase
- If the PR looks good:
  - "The PR looks good! You can approve it directly on Bitbucket: [PR-URL]"
- Optionally:
  - "Would you like me to post this review as a comment on the PR?"
  - If user agrees, use `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_post` to post the review summary as a PR comment:
    ```
    endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments
    body: { "content": { "raw": "[REVIEW-SUMMARY-MARKDOWN]" } }
    ```
  - After posting the review comment, change the PR status to DRAFT using `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_put`:
    ```
    endpoint: /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]
    body: { "draft": true }
    ```
  - Inform the user: "PR #[PR-ID] has been marked as Draft so the author can address the review feedback."

## Examples

```bash
# Review a backend PR (opencell-core repo)
/oc-review-pr INTRD-36922
# → Detects opencell-core repo → uses oc-core-reviewer
# → Reviews Java/EJB/JPA/Liquibase code against core guidelines

# Review a frontend PR (opencell-portal repo)
/oc-review-pr INTRD-41200
# → Detects opencell-portal repo → uses oc-frontend-reviewer
# → Reviews React/TypeScript code against frontend guidelines

# Review will:
# 1. Find the PR associated with the ticket on Bitbucket
# 2. Detect the repository and select the appropriate reviewer
# 3. Fetch the full diff
# 4. Run a comprehensive code review with the selected agent
# 5. Display a detailed report with scores, issues, and fix suggestions
# 6. Offer to apply fixes or post the review as a PR comment
```

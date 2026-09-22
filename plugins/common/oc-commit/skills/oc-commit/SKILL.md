---
name: oc-commit
description: Commit changes using JIRA ticket ID and summary from cache
argument-hint: JIRA Ticket ID (e.g., INTRD-36922)
---

## Purpose

Commit staged changes using the JIRA ticket ID and summary from the local cache, following the commit message conventions below.

## Commit Message Format

Format (the branch/commit conventions this repo's skills share):

```
TICKET-NUMBER: TICKET-SUMMARY
```

- Use imperative mood
- Keep under 72 characters
- Be descriptive but concise

**Example:** `INTRD-36896: AI-[AP2P2L2] framework agreements lists on NEWUI`

## Context

Parse the $ARGUMENTS to get:

- [TICKET-NUMBER]: JIRA ticket ID from $ARGUMENTS

## Tasks

### 1. Get User and Ticket Data from Cache

- Read `.claude/cache/jira-tickets.json`
- Get user info from `user` object:
  - Extract `name` and `email` fields
  - Store as [AUTHOR-NAME] and [AUTHOR-EMAIL]
  - If `user` not found, call the `atlassianUserInfo` tool (official `atlassian` plugin) and cache the result
- Get ticket data from `tickets` object:
  - Look for [TICKET-NUMBER] in the `tickets` object
- If found, extract `summary` field
- If NOT found in cache:
  - Inform user: "Ticket [TICKET-NUMBER] not found in cache"
  - Suggest: "Run `/oc-cache-jira [TICKET-NUMBER]` first to cache the ticket data"
  - Stop execution

### 2. Check Git Status

- Run `git status` to verify there are staged changes
- If no staged changes:
  - Display current status showing modified/untracked files
  - Ask user: "No staged changes. Would you like me to stage all changes first?"
  - If yes, stage the relevant files

### 3. Code Review (oc-fe-reviewer)

Before committing, review the code with the **`oc-fe-reviewer:oc-fe-reviewer`** agent.

> **This is the same agent, the same scope and the same rubric that `/oc-review-pr` will apply later.**
> That is deliberate and it is the point of this step: the score shown here is the score the dev lead's
> review is expected to produce, so a developer is never surprised by a lower number after the PR is
> open. Do not narrow the checklist, do not skip categories, and do not soften the Testing rule — every
> shortcut here reappears as a score drop at PR time.

#### 3a. Determine the review scope — the whole branch, not just this commit

`/oc-pull-request` squashes the branch into one commit, so `/oc-review-pr` reviews the **entire
ticket's diff**. Reviewing only the staged files here would score a fragment and produce a number that
cannot match. Review the same union:

```bash
git branch --show-current                      # [CURRENT-BRANCH]
# [BASE-BRANCH] = third segment of the branch name
#   mhamidi/bugfix/dev/INTRD-123-desc -> dev
# If the branch does not follow the convention, ask the user for the target branch (default `dev`).

git merge-base [BASE-BRANCH] HEAD              # [MERGE-BASE]

# merge-base -> working tree: committed branch work + staged + unstaged, in one diff,
# with no double-counting. This is the union /oc-review-pr sees after the squash.
git diff [MERGE-BASE]                          # [REVIEW-DIFF]
git diff --name-only [MERGE-BASE]              # [CHANGED-FILES]
```

- `git diff [MERGE-BASE]` (no `..HEAD`, no second revision) already covers everything on the branch
  **plus** the changes about to be committed — do not also run `git diff HEAD` / `--cached` and merge
  the outputs, which would list the same hunks twice.
- Store the scope label as
  `[REVIEW-SCOPE]` = `"whole branch vs [BASE-BRANCH] ([N] files), including the staged changes"`.
- If `[BASE-BRANCH]` cannot be determined and the user does not supply one, fall back to the staged
  changes alone and **say so explicitly** in the report — the score then covers this commit only and
  may legitimately differ from the PR score.

#### 3b. Count the Vitest tests the branch adds

`/oc-review-pr` step 5b feeds the reviewer a test count so the **Testing** category is judged on real
coverage. Do the same here, from the same evidence, or Testing gets scored on two different bases:

```bash
git diff [MERGE-BASE] -- '*.test.ts' '*.test.tsx' '*.spec.ts' '*.spec.tsx' \
  ':(exclude)tests/e2e/*' ':(exclude)cypress/*' \
  | grep -cE '^\+[[:space:]]*(it|test)([.][A-Za-z]+)*[[:space:]]*[(`]' || true
```

(`grep -c` exits `1` when the count is zero — `|| true` keeps that from reading as a failed command.)

- Exclude Playwright/Cypress e2e specs (under `tests/e2e/`, `cypress/`, or `*.cy.ts`) — they are not Vitest.
- Count `it.each([...])` as **one** test case.
- Store as `[VITEST-ADDED]`. **Zero is a real, reportable answer** — report it as `0`.

#### 3c. Run the review

Pass the agent:

- The full `[REVIEW-DIFF]` and the `[CHANGED-FILES]` list.
- The scope: "Scope reviewed: `[REVIEW-SCOPE]`".
- The test count: "This branch adds `[VITEST-ADDED]` Vitest test case(s)".
- Instruction: *"Review these changes against your full 13-category Review Checklist and score with your
  Scoring rubric. Give every category a verdict and return the Category Verdicts table. For each issue,
  give the exact file path and line context, and suggest a concrete fix."*

The reviewer evaluates all thirteen — TypeScript quality; React patterns; state management; import
conventions; naming conventions; widget structure; API usage; i18n completeness (EN + FR); testing
coverage; accessibility; performance; error handling; security — and computes the score with the rubric
in its own definition. **Do not restate a shorter list here**: the divergence this step exists to prevent
is exactly a caller asking for a subset.

#### Review Output

Present the review to the user, including the verdict table the score was computed from:

```
Code Review Results  (same rubric as /oc-review-pr)
---------------------------------------------------
Scope:  [REVIEW-SCOPE]
Score:  X/10 — [BAND]
Vitest: [VITEST-ADDED] test case(s) added on this branch

Category verdicts: [n] Pass · [n] Warn · [n] Fail · [n] N/A
  (full 13-row table from the agent)

Critical Issues (Must Fix):
  - Issue 1: [description] at [file:line]

Warnings (Should Fix):
  - Warning 1: [description]

Suggestions:
  - Suggestion 1
```

#### User Decision

Ask the user using AskUserQuestion:

```
How would you like to proceed?

1. Fix issues first (Recommended)
   - Stop commit and address the critical issues/warnings

2. Continue without fixing
   - Proceed with commit despite the issues

3. Review details
   - Show full review report before deciding
```

- If user chooses **"Fix issues first"**: Stop execution, let user fix the issues manually or with assistance
- If user chooses **"Continue without fixing"**: Proceed to step 4 — but first **state the consequence
  plainly**, because these exact issues are what `/oc-review-pr` will find again:

  > Committing with score X/10 and N unresolved critical issue(s). `/oc-review-pr` runs the same rubric
  > on the same code, so expect the same score — and it acts on it automatically: **8-10 leaves the PR
  > open, 1-7 marks it Draft.** (A review never declines a PR; a draft is undone with *Mark as ready*.)

- If user chooses **"Review details"**: Show the full detailed review, then ask again

**Note:** Code review is always performed on every commit to ensure code quality.

> **Scope caveat.** This step reviews the frontend with `oc-fe-reviewer` regardless of repository. On
> **opencell-core** the pre-commit score therefore comes from a React/TypeScript reviewer while
> `/oc-review-pr` delegates to `oc-be-tools:oc-be-pr-reviewer` — the two numbers are **not** comparable
> there. Backend developers should run `/oc-be-tools:oc-be-review` before the PR for a comparable score.

### 4. Build Commit Message

- Format: `[TICKET-NUMBER]: [TICKET-SUMMARY]`
- Truncate summary if total message exceeds 72 characters
- Store in [COMMIT-MESSAGE]

### 5. Display Preview

Show the user what will be committed:

```
Commit Preview
--------------
Author: Mohamed Hamidi <mohamed.hamidi@opencellsoft.com>
Message: INTRD-36922: [Front] Claude Code integration on Portal

Staged changes:
  modified:   .claude/commands/oc_commit.md
  modified:   .gitignore

Code Review: Passed (8/10) | 0 critical, 2 warnings

Proceed with commit? (y/n)
```

### 6. Execute Commit

- Run git commit with the message using HEREDOC format and the Atlassian user as author:

  ```bash
  git commit --author="[AUTHOR-NAME] <[AUTHOR-EMAIL]>" -m "$(cat <<'EOF'
  [COMMIT-MESSAGE]
  EOF
  )"
  ```

- Display success message with commit hash
- Show `git log -1 --oneline` to confirm

## Examples

```bash
# Commit using cached ticket data (includes code review)
/oc-commit INTRD-36922
```

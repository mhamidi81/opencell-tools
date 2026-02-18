---
name: oc-commit
description: Commit changes using JIRA ticket ID and summary from cache
argument-hint: JIRA Ticket ID (e.g., INTRD-36922)
---

## Purpose

Commit staged changes using the JIRA ticket ID and summary from the local cache, following the commit message conventions defined in CODE_QUALITY.md.

## Commit Message Format

Based on [CODE_QUALITY.md](../../CODE_QUALITY.md#commit-messages):

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
  - If `user` not found, call `atlassianUserInfo` MCP tool and cache the result
- Get ticket data from `tickets` object:
  - Look for [TICKET-NUMBER] in the `tickets` object
- If found, extract `summary` field
- If NOT found in cache:
  - Inform user: "Ticket [TICKET-NUMBER] not found in cache"
  - Suggest: "Run `/cache-jira [TICKET-NUMBER]` first to cache the ticket data"
  - Stop execution

### 2. Check Git Status

- Run `git status` to verify there are staged changes
- If no staged changes:
  - Display current status showing modified/untracked files
  - Ask user: "No staged changes. Would you like me to stage all changes first?"
  - If yes, stage the relevant files

### 3. Code Review (frontend-reviewer)

Before committing, review the changed code for quality and standards compliance:

- Use the **frontend-reviewer** sub-agent to review all staged/modified files
- Focus on files with extensions: `.ts`, `.tsx`, `.js`, `.jsx`, `.json` (for i18n)
- The review should check:
  - TypeScript quality and typing
  - React component patterns
  - Import conventions (path aliases)
  - i18n compliance (if translation files changed)
  - Testing requirements (if test files exist)
  - Naming conventions

#### Review Output

Present the review summary to the user:

```
Code Review Results
-------------------
Score: X/10

Critical Issues (Must Fix):
  - Issue 1: [description] at [file:line]
  - Issue 2: [description] at [file:line]

Warnings (Should Fix):
  - Warning 1: [description]
  - Warning 2: [description]

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
- If user chooses **"Continue without fixing"**: Proceed to step 4
- If user chooses **"Review details"**: Show the full detailed review, then ask again

**Note:** Code review is always performed on every commit to ensure code quality.

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

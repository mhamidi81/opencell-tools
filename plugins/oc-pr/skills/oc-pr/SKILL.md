---
name: oc-pr
description: Push changes and create a pull request for the JIRA ticket
argument-hint: JIRA Ticket ID (e.g., INTRD-36922)
---

## Purpose

Push the current branch to the remote and create a pull request targeting the base branch extracted from the current branch name, using the JIRA ticket information from cache.

## Prerequisites (Bitbucket)

To enable automatic PR creation for Bitbucket repositories:

1. Create an App Password at: https://bitbucket.org/account/settings/app-passwords/
   - Required permissions: `pullrequest:write`, `repository:read`
2. Export the credentials in your shell profile (`.bashrc`, `.zshrc`, etc.):

   ```bash
   export BITBUCKET_EMAIL="your-oc-email"
   export BITBUCKET_ACCESS_TOKEN="your-access_token"
   ```

3. The Bitbucket MCP server is configured in `.mcp.json` and will use these credentials automatically.

If credentials are not configured, the command will display a PR creation URL instead.

## Context

Parse the $ARGUMENTS to get:

- [TICKET-NUMBER]: JIRA ticket ID from $ARGUMENTS

## Branch Naming Convention

Based on [CODE_QUALITY.md](../../CODE_QUALITY.md#branch-naming):

**Format**: `{USERNAME}/{TICKET-TYPE}/{BASE-BRANCH}/{TICKET-NUMBER}-{TICKET-SUMMARY}`

The [BASE-BRANCH] is extracted from the third segment of the current branch name.

## Tasks

### 1. Get User and Ticket Data from Cache

- Read `.claude/cache/jira-tickets.json`
- Get user info from `user` object:
  - Extract `name` and `email` fields
  - Store as [AUTHOR-NAME] and [AUTHOR-EMAIL]
  - If `user` not found, call `atlassianUserInfo` MCP tool and cache the result
- Get ticket data from `tickets` object:
  - Look for [TICKET-NUMBER] in the `tickets` object
  - If found, extract `summary` field and store as [TICKET-SUMMARY]
  - If NOT found in cache:
    - Inform user: "Ticket [TICKET-NUMBER] not found in cache"
    - Suggest: "Run `/cache-jira [TICKET-NUMBER]` first to cache the ticket data"
    - Stop execution

### 2. Check Current Branch and Extract Base Branch

- Run `git branch --show-current` to get [CURRENT-BRANCH]
- Extract [BASE-BRANCH] from [CURRENT-BRANCH]:
  - Split branch name by `/`
  - The third segment is [BASE-BRANCH] (e.g., `mhamidi/feature/dev/INTRD-123` -> `dev`)
  - If branch doesn't follow convention, ask user to specify target branch
- Run `git status` to check for uncommitted changes
- If there are uncommitted changes:
  - Warn user: "You have uncommitted changes. Please commit or stash them first."
  - Stop execution
- Check if branch has upstream: `git rev-parse --abbrev-ref @{upstream}`

### 3. Squash Commits

Before pushing, squash all commits on the current branch into a single commit:

1. **Count commits to squash:**

   ```bash
   git rev-list --count [BASE-BRANCH]..HEAD
   ```

   - Store result as [COMMIT-COUNT]
   - If [COMMIT-COUNT] is 0, skip squashing (no commits to squash)
   - If [COMMIT-COUNT] is 1, skip squashing (already single commit)

2. **If [COMMIT-COUNT] > 1, perform squash:**

   ```bash
   git reset --soft [BASE-BRANCH]
   git commit -m "[TICKET-NUMBER]: [TICKET-SUMMARY]"
   ```

3. **Display squash result:**
   - If squashed: "Squashed [COMMIT-COUNT] commits into 1"
   - If skipped: "Single commit, no squash needed"

**Note:** This step is performed for both new PRs and PR updates to maintain a clean commit history.

### 4. Detect Remote Type

- Run `git remote get-url origin` to get the remote URL
- Determine [REMOTE-TYPE]:
  - If URL contains `bitbucket.org` -> [REMOTE-TYPE] = `bitbucket`
  - If URL contains `github.com` -> [REMOTE-TYPE] = `github`
  - Otherwise -> [REMOTE-TYPE] = `unknown`
- Extract [REPO-OWNER] and [REPO-NAME] from the remote URL

### 5. Push to Remote

- If commits were squashed, use force push to update remote:
  ```bash
  git push --force-with-lease -u origin [CURRENT-BRANCH]
  ```
- If no squash was performed:
  - If no upstream is set:
    ```bash
    git push -u origin [CURRENT-BRANCH]
    ```
  - If upstream exists:
    ```bash
    git push
    ```

**Note:** `--force-with-lease` is used instead of `--force` as a safety measure. It will fail if the remote has commits that you haven't fetched, preventing accidental overwrites.

### 6. Build PR Title and Description

Based on [CODE_QUALITY.md](../../CODE_QUALITY.md#pull-requests):

- Reference Jira ticket in PR title and description
- Link related tickets using `Relates to [TICKET-NUMBER]`
- Keep PRs focused and reasonably sized

**PR Title**: `[TICKET-NUMBER]: [TICKET-SUMMARY]`

- Truncate title if it exceeds 70 characters

**PR Description**:

```markdown
## Summary

Implements [TICKET-NUMBER]: [TICKET-SUMMARY]

Relates to [TICKET-NUMBER]

## Test plan

- [ ] Manual testing completed
- [ ] Unit tests pass
- [ ] Code review completed

Generated with [Claude Code](https://claude.com/claude-code)
```

### 7. Display Preview

Show the user what will be created:

```
Pull Request Preview
--------------------
Author:  [AUTHOR-NAME] <[AUTHOR-EMAIL]>
Branch:  [CURRENT-BRANCH] -> [BASE-BRANCH]
Title:   [TICKET-NUMBER]: [TICKET-SUMMARY]
Commits: [COMMIT-COUNT] commits squashed into 1

Proceed with PR creation? (y/n)
```

### 8. Create Pull Request

#### For GitHub ([REMOTE-TYPE] = `github`)

- Use `gh pr create` with the extracted base branch:

  ```bash
  gh pr create --base [BASE-BRANCH] --title "[PR-TITLE]" --body "$(cat <<'EOF'
  ## Summary

  Implements [TICKET-NUMBER]: [TICKET-SUMMARY]

  Relates to [TICKET-NUMBER]

  ## Test plan

  - [ ] Manual testing completed
  - [ ] Unit tests pass
  - [ ] Code review completed

  Generated with [Claude Code](https://claude.com/claude-code)
  EOF
  )"
  ```

- Display the PR URL on success
- If PR already exists, show the existing PR URL

#### For Bitbucket ([REMOTE-TYPE] = `bitbucket`)

**Option 1: Use Bitbucket MCP Server (Preferred)**

If the Bitbucket MCP server is available and configured, use the `bb_pr_create` MCP tool:

- Call `mcp__bitbucket__bb_pr_create` with parameters:

  - `workspace`: [REPO-OWNER]
  - `repository`: [REPO-NAME]
  - `title`: [PR-TITLE]
  - `source_branch`: [CURRENT-BRANCH]
  - `destination_branch`: [BASE-BRANCH]
  - `description`: [PR-DESCRIPTION]

- Display the PR URL from the response
- If error, fall back to Option 2

**Option 2: Use Bitbucket REST API with curl**

If MCP is not available but credentials are set (`BITBUCKET_EMAIL` and `BITBUCKET_ACCESS_TOKEN`):

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests" \
  -d '{
    "title": "[PR-TITLE]",
    "description": "[PR-DESCRIPTION]",
    "source": {
      "branch": {
        "name": "[CURRENT-BRANCH]"
      }
    },
    "destination": {
      "branch": {
        "name": "[BASE-BRANCH]"
      }
    },
    "close_source_branch": true
  }'
```

- Parse the response to extract the PR URL from `links.html.href`
- Display: "PR created successfully: [PR-URL]"

**Option 3: Manual Fallback**

If neither MCP nor credentials are available:

- Generate the Bitbucket PR creation URL:

  ```
  https://bitbucket.org/[REPO-OWNER]/[REPO-NAME]/pull-requests/new?source=[CURRENT-BRANCH]&dest=[BASE-BRANCH]
  ```

- Display the PR creation link and details for manual copy:

  ```
  Bitbucket Pull Request (Manual)
  --------------------------------
  Auto-creation not available. Configure Bitbucket MCP or set BITBUCKET_EMAIL/BITBUCKET_ACCESS_TOKEN.

  URL: [PR-CREATION-URL]

  Title: [TICKET-NUMBER]: [TICKET-SUMMARY]

  Description:
  ## Summary

  Implements [TICKET-NUMBER]: [TICKET-SUMMARY]

  Relates to [TICKET-NUMBER]

  ## Test plan

  - [ ] Manual testing completed
  - [ ] Unit tests pass
  - [ ] Code review completed

  Generated with [Claude Code](https://claude.com/claude-code)
  ```

#### For Unknown Remote

- Inform user: "Unknown remote type. Please create PR manually."
- Display the PR title and description for reference

## Examples

```bash
# Create PR for ticket (base branch extracted from current branch name)
/oc-pr INTRD-36922

# Example: If current branch is "mhamidi/feature/dev/INTRD-36922-claude-integration"
# PR will target "dev" branch automatically
```

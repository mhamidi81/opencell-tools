---
name: reviewBackend
description: Evaluate Opencell backend code changes against the project guidelines using the pr-reviewer agent. Reviews uncommitted changes, a specific Bitbucket PR, or lets you pick from open PRs.
argument-hint: "[PR-number | list]"
---

# Review Backend Changes

You evaluate Opencell backend code changes against the project guidelines and produce a review with an approval decision. The actual review is performed by the `oc-backend-tools:pr-reviewer` agent, which reads the guideline files in `${CLAUDE_PLUGIN_ROOT}/guidelines/` (the same guidelines used to generate the code).

## Argument Parsing

Parse `$ARGUMENTS` to select the mode:

- **No arguments** → **Mode LOCAL**: review the current uncommitted working-tree changes.
- **A number** (e.g. `15042`) → **Mode PR**: review that pull request.
- **`list`** (also accept `pr` or `prs`) → **Mode LIST**: list open pull requests and let the user choose one, then continue as Mode PR.

> Distinguishing "no PR number" cases: a bare `/reviewBackend` always means *local uncommitted review*. To browse pull requests instead, the user must pass the `list` keyword. This removes the ambiguity between "review my local changes" and "show me the open PRs".

---

## Mode LOCAL — review uncommitted changes (no arguments)

1. Dispatch the `oc-backend-tools:pr-reviewer` agent (Task tool, `subagent_type: oc-backend-tools:pr-reviewer`) with this instruction:
   - "Review the current uncommitted working-tree changes against the Opencell guidelines. Use `git status --short`, `git diff --stat HEAD`, and `git diff HEAD` to obtain the changes. Provide the full review with a score and a final Status."
2. Display the agent's review report to the user.
3. **Do not** write anything to Bitbucket in this mode — there is no PR. If there are no uncommitted changes, tell the user and stop.

---

## Mode PR — review a specific pull request (`<number>`)

### 1. Resolve the repository

- Run `git remote get-url origin` to get the remote URL.
- Extract `[REPO-OWNER]` and `[REPO-NAME]` (e.g. `opencellsoft` / `opencell-core`).
- If the URL does not contain `bitbucket.org`, inform the user "This command supports Bitbucket repositories only." and stop.
- Store `[PR-ID]` = the number from `$ARGUMENTS`.

### 2. Fetch the PR metadata, diff, and changed files

Use the Bitbucket MCP server when available, otherwise fall back to `curl` (see **Bitbucket Access** below).

- PR metadata: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]`
  - Extract `[PR-TITLE]` (`title`), `[PR-AUTHOR]` (`author.display_name`), `[PR-SOURCE-BRANCH]` (`source.branch.name`), `[PR-DEST-BRANCH]` (`destination.branch.name`), `[PR-STATE]` (`state`), `[PR-URL]` (`links.html.href`).
  - If the PR is not found, inform the user and stop.
- Diff: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff` → store as `[PR-DIFF]`.
- Changed files: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diffstat` → store the file paths as `[CHANGED-FILES]`.

### 3. Show an overview

```
Pull Request Review
===================
PR:      #[PR-ID] — [PR-TITLE]
Author:  [PR-AUTHOR]
Branch:  [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
State:   [PR-STATE]
URL:     [PR-URL]
Files:   [N] files changed

Running review...
```

### 4. Run the review

Dispatch the `oc-backend-tools:pr-reviewer` agent (`subagent_type: oc-backend-tools:pr-reviewer`), passing:
- The full `[PR-DIFF]` content.
- The `[CHANGED-FILES]` list.
- Context: "This is a review of PR #[PR-ID]: [PR-TITLE]. Review the provided diff against the Opencell guidelines. For each issue give the file path and line context, and a concrete fix. End with the final Status line."

Display the agent's full review report. Extract the decision from its `**Status**:` line:
- `APPROVE` → acceptable.
- `CHANGES_REQUESTED` → failed.

### 5. Update the PR (confirm first)

Posting to a pull request is an outward-facing action. **Show the user what will be posted and ask for confirmation before writing.** Present:
- The review comment body (the report, or a concise summary of it).
- The action: APPROVE (acceptable) or REQUEST CHANGES (failed).

On confirmation:

1. Post the review as a comment:
   - `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments`
   - body: `{ "content": { "raw": "[REVIEW-MARKDOWN]" } }`
2. Set the verdict:
   - If acceptable: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/approve`
   - If failed: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/request-changes`
3. Confirm to the user:
   - "Posted review and marked PR #[PR-ID] as **[Approved | Changes requested]** — [PR-URL]"

If the user declines confirmation, print the review and the PR URL so they can act manually, and stop without writing.

---

## Mode LIST — pick a PR (`list`)

1. Resolve the repository (Step 1 of Mode PR).
2. List open pull requests:
   - `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?state=OPEN`
3. Present a numbered table:

   ```
   Open Pull Requests — [REPO-OWNER]/[REPO-NAME]
   #   PR ID   Title                                  Author        Branch → Dest
   1   15042   INTRD-41861: Minimum invoice lines     A. Karpavicius  feature/... → dev
   2   15039   INTRD-36141: Tenant init fix           ...             bugfix/...  → dev
   ```

4. Ask the user to choose a row (or PR ID). Once chosen, continue with **Mode PR** for that `[PR-ID]`.
5. If there are no open PRs, tell the user and stop.

---

## Bitbucket Access

This command requires Bitbucket access. Use the first available option:

**Option 1 — Bitbucket MCP (preferred).** If the `oc-bitbucket-mcp` plugin is installed, use the generic REST passthrough tools:
- `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_get` with `{ "endpoint": "<path>" }` for GET requests.
- `mcp__plugin_oc-bitbucket-mcp_bitbucket__bb_post` with `{ "endpoint": "<path>", "body": <json> }` for POST requests (comments, approve, request-changes).

**Option 2 — curl fallback.** If MCP is not available but `BITBUCKET_ACCESS_TOKEN` is set:

```bash
# GET (e.g. PR diff)
curl -s -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff"

# POST a comment
curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments" \
  -d '{ "content": { "raw": "[REVIEW-MARKDOWN]" } }'

# Approve / request changes
curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/approve"
curl -s -X POST -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/request-changes"
```

Credentials come from `BITBUCKET_EMAIL` and `BITBUCKET_ACCESS_TOKEN` (Bitbucket App Password with `pullrequest:write`, `repository:read`).

**Option 3 — manual fallback.** If neither MCP nor a token is available, run the review (Mode LOCAL still works fully) and, for PR modes, print the review plus the PR URL so the user can post and approve/decline manually.

---

## Examples

```bash
# Review current uncommitted changes
/reviewBackend

# Review pull request #15042 and (after confirmation) approve or request changes
/reviewBackend 15042

# List open PRs, pick one, then review it
/reviewBackend list
```

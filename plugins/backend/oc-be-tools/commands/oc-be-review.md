---
description: Evaluate Opencell backend code changes against the project guidelines using the oc-be-pr-reviewer agent, augmented with a SonarQube quality-gate summary. Reviews uncommitted changes, a specific Bitbucket PR, or lets you pick from open PRs, and tags the JIRA ticket ai_code_review_back.
argument-hint: "[PR-number | list]"
---

# Review Backend Changes

You evaluate Opencell backend code changes against the project guidelines and produce a review with an approval decision. The actual review is performed by the `oc-be-tools:oc-be-pr-reviewer` agent, which reads the guideline files in `${CLAUDE_PLUGIN_ROOT}/guidelines/` (the same guidelines used to generate the code).

## Argument Parsing

Parse `$ARGUMENTS` to select the mode:

- **No arguments** → **Mode LOCAL**: review the current uncommitted working-tree changes.
- **A number** (e.g. `15042`) → **Mode PR**: review that pull request.
- **`list`** (also accept `pr` or `prs`) → **Mode LIST**: list open pull requests and let the user choose one, then continue as Mode PR.

> Distinguishing "no PR number" cases: a bare `/oc-be-tools:oc-be-review` always means *local uncommitted review*. To browse pull requests instead, the user must pass the `list` keyword. This removes the ambiguity between "review my local changes" and "show me the open PRs".

---

## Mode LOCAL — review uncommitted changes (no arguments)

1. Dispatch the `oc-be-tools:oc-be-pr-reviewer` agent (Task tool, `subagent_type: oc-be-tools:oc-be-pr-reviewer`) with this instruction:
   - "Review the current uncommitted working-tree changes against the Opencell guidelines. Use `git status --short`, `git diff --stat HEAD`, and `git diff HEAD` to obtain the changes. Provide the full review with a score and a final Status."
2. Display the agent's review report to the user.
3. **SonarQube analysis** — run the **SonarQube analysis (opencell-core)** section against the current branch and append `[SONAR-SUMMARY]` to the displayed report (skip gracefully if `oc-sonar-mcp` is unavailable or the branch has not been analysed).
4. **Do not** write anything to Bitbucket in this mode — there is no PR. If there are no uncommitted changes, tell the user and stop.
5. **Tag the JIRA ticket** (a review was run) — resolve the ticket from the current branch name and apply `ai_code_review_back` per **Tag the JIRA ticket** below.

---

## Mode PR — review a specific pull request (`<number>`)

### 1. Resolve the repository

- Run `git remote get-url origin` to get the remote URL.
- Extract `[REPO-OWNER]` and `[REPO-NAME]` (e.g. `opencellsoft` / `opencell-core`).
- If the URL does not contain `bitbucket.org`, inform the user "This command supports Bitbucket repositories only." and stop.
- Store `[PR-ID]` = the number from `$ARGUMENTS`.

### 2. Fetch the PR metadata, diff, and changed files

Use `curl` with the Bearer access token (see **Bitbucket Access** below).

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

Dispatch the `oc-be-tools:oc-be-pr-reviewer` agent (`subagent_type: oc-be-tools:oc-be-pr-reviewer`), passing:
- The full `[PR-DIFF]` content.
- The `[CHANGED-FILES]` list.
- Context: "This is a review of PR #[PR-ID]: [PR-TITLE]. Review the provided diff against the Opencell guidelines. For each issue give the file path and line context, and a concrete fix. End with the final Status line."

Display the agent's full review report. Extract the decision from its `**Status**:` line:
- `APPROVE` → acceptable.
- `CHANGES_REQUESTED` → failed.

### 5. SonarQube analysis

Run the **SonarQube analysis (opencell-core)** section against `[PR-SOURCE-BRANCH]` and display `[SONAR-SUMMARY]` alongside the agent's report. Let it influence the verdict: a failing gate or any BLOCKER/CRITICAL issue on the changed files means the review is **failed** (`CHANGES_REQUESTED`) even if the agent said `APPROVE`. Skip gracefully if `oc-sonar-mcp` is unavailable.

### 6. Update the PR and tag the ticket (confirm first)

Posting to a pull request and tagging JIRA are outward-facing actions. **Show the user what will be posted and set, and ask for confirmation before writing.** Present:
- The review comment body (the report plus `[SONAR-SUMMARY]`, or a concise summary of it).
- The action: APPROVE (acceptable) or REQUEST CHANGES (failed).
- The JIRA tag: `ai_code_review_back` on `customfield_10613` of the ticket in `[PR-TITLE]`.

On confirmation:

1. Post the review as a comment (include `[SONAR-SUMMARY]` in `[REVIEW-MARKDOWN]`):
   - `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments`
   - body: `{ "content": { "raw": "[REVIEW-MARKDOWN]" } }`
2. Set the verdict:
   - If acceptable: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/approve`
   - If failed: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/request-changes`
3. **Tag the JIRA ticket** — resolve the ticket from `[PR-TITLE]` (fallback `[PR-SOURCE-BRANCH]`) and apply `ai_code_review_back` per **Tag the JIRA ticket** below.
4. Confirm to the user:
   - "Posted review and marked PR #[PR-ID] as **[Approved | Changes requested]**, tagged [TICKET] ai_code_review_back — [PR-URL]"

If the user declines confirmation, print the review and the PR URL so they can act manually, and stop without writing (no PR post, no JIRA tag).

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

## Tag the JIRA ticket (`ai_code_review_back`)

Whenever a review runs, record it on the ticket by adding the tag **`ai_code_review_back`** to `customfield_10613` — regardless of the verdict (APPROVE or CHANGES_REQUESTED); the tag means "AI performed a code review on this ticket". This is the same field the `/oc-be-calculate-ai-use` command tags with `ai_Dev_back` / `ai_test_back_dev`.

**Resolve the ticket — reproduce Bitbucket's "Jira work item" link.** Bitbucket's PR REST object does **not** carry the linked Jira issue; the "N Jira work items" panel is derived by Atlassian's Jira↔Bitbucket integration from the PR title, source branch, and commit messages. So resolve the key from the same sources, in order:

- Mode PR / LIST — scan for `[A-Z]+-\d+`, first match wins, checking in this order:
  1. `[PR-TITLE]`
  2. `[PR-SOURCE-BRANCH]`
  3. the PR's commit messages — `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/commits` (fetch only if 1–2 yield nothing).
- Mode LOCAL — the first `[A-Z]+-\d+` match in the current branch name (`git branch --show-current`).
- **Validate & display**: confirm the resolved key with `getJiraIssue` (Atlassian MCP) and show its summary in the confirmation, so the user sees the same ticket the PR's "Jira work item" links to. If the fetch 404s, the key is stale — warn and ask the user for the correct ticket rather than tagging the wrong one.
- If **several distinct keys** appear across the sources (a PR spanning multiple tickets), ask the user which to tag (default: the one in the title).
- If no key can be resolved, skip tagging and tell the user (nothing to tag).

**Apply the tag** using the **Atlassian MCP tools** (site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`; resolve via `getAccessibleAtlassianResources` if unknown). **Do not overwrite existing values; append `ai_code_review_back` only if not already present.**

1. Read the current value (`getJiraIssue` with `fields: ["customfield_10613"]`). If `ai_code_review_back` is already present, **skip the edit** and note it.
2. Otherwise learn the field shape (`getJiraIssueTypeMetaWithFields`: array of `option` vs array of strings vs single `option`) and build the matching `editJiraIssue` payload, merging with existing values:
   - Multi-select (array of options): `{ "fields": { "customfield_10613": [ {"value": "ai_code_review_back"}, <existing...> ] } }`
   - Labels-style (array of strings): `{ "fields": { "customfield_10613": ["ai_code_review_back", <existing...>] } }`
   - Single-select (option): `{ "fields": { "customfield_10613": {"value": "ai_code_review_back"} } }`
3. Call `editJiraIssue` with `cloudId`, `issueIdOrKey = [TICKET]`, and the payload.
   - If rejected because `ai_code_review_back` is not an allowed option, report the error verbatim (the option may need creating in the field config) and do not retry blindly.

> This is the only JIRA write this command makes. In Mode PR/LIST it is confirmed together with the PR update (Step 6); in Mode LOCAL confirm it on its own before writing.

---

## SonarQube analysis (opencell-core)

Augment the guideline review with SonarQube's quality gate and issues for the changed code. This needs the **`oc-sonar-mcp`** plugin; if its tools are unavailable, note "SonarQube not available — skipped" and continue (the review still completes without it). It is read-only — no confirmation needed.

Determine `[SONAR-BRANCH]`: the PR source branch (`[PR-SOURCE-BRANCH]`, Mode PR/LIST) or the current branch (`git branch --show-current`, Mode LOCAL). The SonarQube project key for opencell-core is `opencell-core`.

1. **Quality gate** — `mcp__plugin_oc-sonar-mcp_sonarqube__quality_gate_status` with `project_key: "opencell-core"`, `branch: [SONAR-BRANCH]` → `[SONAR-GATE]` (`OK` / `ERROR`). If the branch is unknown to SonarQube, retry without `branch` for the project-level status and note it is not branch-specific.
2. **Measures** — `mcp__plugin_oc-sonar-mcp_sonarqube__measures_component` with `component: "opencell-core"`, `branch: [SONAR-BRANCH]`, `metric_keys: ["bugs","vulnerabilities","code_smells","coverage","duplicated_lines_density","security_hotspots","sqale_rating","reliability_rating","security_rating"]`.
3. **Issues on changed files** — `mcp__plugin_oc-sonar-mcp_sonarqube__issues` with `project_key: "opencell-core"`, `branch: [SONAR-BRANCH]`, `files:` the changed paths (`[CHANGED-FILES]` in Mode PR, or `git diff --name-only HEAD` in Mode LOCAL), `statuses: ["OPEN","CONFIRMED","REOPENED"]`, `page_size: "50"`. Group by severity (BLOCKER / CRITICAL / MAJOR / MINOR / INFO).

Compile `[SONAR-SUMMARY]`:

```
SonarQube — quality gate: [SONAR-GATE]
  bugs N · vulnerabilities N · code smells N · hotspots N · coverage N% · duplication N%
  ratings — maintainability A–E / reliability A–E / security A–E
  open issues on changed files: TOTAL  (BLOCKER n · CRITICAL n · MAJOR n · MINOR n · INFO n)
```

List any BLOCKER/CRITICAL issues with file path, rule and message. **A failing quality gate or any BLOCKER/CRITICAL issue on the changed files should push the verdict toward `CHANGES_REQUESTED`.** Fold `[SONAR-SUMMARY]` into the displayed review and, in Mode PR, into the PR comment body.

---

## Bitbucket Access

This command talks to Bitbucket over its REST API with `curl`.

**Primary — curl with a Bearer access token.** Requires `BITBUCKET_ACCESS_TOKEN` (a Bitbucket **repository or workspace Access Token**, authenticated as a Bearer token):

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

Create the token at **repo → Settings → Security → Access tokens** (or workspace-level for all repos) with **Pull requests: Write** and **Repositories: Read**. Bitbucket App Passwords are deprecated (removed 2026-07-28) — do not use them. Verify the token works: the first `curl` above should return the diff, not a `401`.

**Fallback — manual.** If `BITBUCKET_ACCESS_TOKEN` is missing or a call fails, run the review (Mode LOCAL still works fully) and, for PR modes, print the review plus the PR URL so the user can post and approve/decline manually.

> The JIRA tag (**Tag the JIRA ticket**) uses the Atlassian MCP and is independent of Bitbucket access — apply it even when the PR update falls back to manual, as long as the ticket resolves and the user confirms.

---

## Examples

```bash
# Review current uncommitted changes
/oc-be-tools:oc-be-review

# Review pull request #15042 and (after confirmation) approve or request changes
/oc-be-tools:oc-be-review 15042

# List open PRs, pick one, then review it
/oc-be-tools:oc-be-review list
```

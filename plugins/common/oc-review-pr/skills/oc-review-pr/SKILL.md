---
name: oc-review-pr
description: Review the pull request linked to a JIRA ticket — frontend (opencell-portal) PRs are reviewed here with oc-fe-reviewer, the report is always posted on the PR, and the PR status follows the score (8-10 left open, 6-7 drafted, 1-5 declined); backend (opencell-core) PRs are delegated to the /oc-be-review command.
argument-hint: <TICKET-ID> (e.g., INTRD-36922)
---

## Purpose

Review the pull request associated with a JIRA ticket. This command resolves the ticket → its PR, then routes by repository:

- **opencell-portal (frontend)** → reviewed **here** with the `oc-fe-reviewer:oc-fe-reviewer` agent. The report is **always posted as a comment on the PR** and the ticket is always tagged `ai_code_review_Front`. The **PR status then follows the score**: 8-10 left open, 6-7 marked Draft, 1-5 declined. All of it automatic, without asking.
- **opencell-core (backend)** → **not reviewed here.** This command hands off to the **`/oc-be-tools:oc-be-review`** command, which owns the backend review (the `oc-be-pr-reviewer` agent + guidelines), the confirm-first PR comment and verdict, and the `ai_code_review_back` Jira tag. Keeping a single backend owner avoids two divergent backend-review paths.

When the ticket has **several PRs** (the same change opened against different target branches), exactly **one** is reviewed, commented and has its status changed: the one targeting **`dev`** if it exists. See **Selecting a single PR** in Step 4.

The ticket is always read **live from Jira** — this command does not use the `/oc-cache-jira` cache.

## Context

Parse `$ARGUMENTS` to get:

- `[TICKET-NUMBER]`: JIRA ticket ID from `$ARGUMENTS`.

## Tasks

### 1. Get ticket data from Jira

Fetch the ticket **directly from Jira every time**. This command does **not** use the
`.claude/cache/jira-tickets.json` cache and must **not** call `/oc-cache-jira` — a review has to reflect
the ticket's current state, and Step 9 reads `customfield_10613` live anyway.

- Call `getJiraIssue` (official `atlassian` plugin — see **Access**) with `issueIdOrKey: [TICKET-NUMBER]`
  and `fields: ["summary"]`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`.
- Extract `summary` as `[TICKET-SUMMARY]`.
- If the ticket cannot be fetched (unknown key, no Atlassian MCP connection, permission error), inform
  the user and stop.

> Step 9 re-reads `customfield_10613` on its own, immediately before writing it — do not reuse a value
> read here, since the review takes time and another command may have tagged the ticket meanwhile.

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

1. **Find the PR** for `[TICKET-NUMBER]` (see **Access** below), reproducing Bitbucket's "Jira work item" detection. Collect **all** candidates, then select **exactly one** — a ticket often has one PR per target branch:
   - by title: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~"[TICKET-NUMBER]"&state=OPEN`;
   - if none, by source branch containing the key: `...pullrequests?q=source.branch.name~"[TICKET-NUMBER]"`;
   - prefer OPEN; only if there are none, retry with `state=MERGED`, then `state=DECLINED`.
   - De-duplicate by `id`, then apply the same **Selecting a single PR** rule as the frontend path (Step 4) — **a PR targeting `dev` wins**; if none targets `dev` and there are several, ask the user which to review. Store the selected `id` as `[PR-ID]` and report which PRs were skipped.
2. **Delegate**:
   - If a `[PR-ID]` was found → run **`/oc-be-tools:oc-be-review [PR-ID]`** and stop. That command fetches the diff, runs `oc-be-pr-reviewer`, adds a SonarQube quality-gate summary, and — after your confirmation — posts the review comment, sets the verdict, and tags the ticket `ai_code_review_back` on `customfield_10613`.
   - If no PR was found → tell the user "No pull request found for [TICKET-NUMBER]" and suggest **`/oc-be-tools:oc-be-review list`** to pick one manually (or `/oc-be-tools:oc-be-review` to review local uncommitted changes). Stop.

> This command performs **no** Jira write and **no** Bitbucket write on the backend path — everything outward-facing is done by `/oc-be-review`, under its own confirmation.

---

> The remaining steps (4–10) apply to the **frontend** path (opencell-portal) only.

### 4. Find the pull request for the ticket (frontend)

A ticket often has **several PRs**, one per target branch (e.g. the same fix opened against `dev` and against `18.X`). **Exactly one PR gets reviewed, tagged and commented — never more than one.** See **Selecting a single PR** below for the rule.

**4a. Collect every candidate.** Do not stop at the first match — gather the full list so the selection rule can see all target branches:

```bash
# by title, open PRs
curl -s -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=title~%22[TICKET-NUMBER]%22&state=OPEN&pagelen=50"
# if that returns nothing, by source branch, open PRs
curl -s -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?q=source.branch.name~%22[TICKET-NUMBER]%22&state=OPEN&pagelen=50"
```

- Merge the results of both searches and **de-duplicate by `id`** → `[CANDIDATES]`.
- Prefer **OPEN** PRs. Only if `[CANDIDATES]` is empty, repeat both searches with `state=MERGED`, then `state=DECLINED`.
- If `[CANDIDATES]` is still empty, inform the user "No pull request found for [TICKET-NUMBER]" and stop.

**4b. Select exactly one** using the rule below, then extract from the **selected** PR only: `[PR-ID]` (`id`), `[PR-TITLE]` (`title`), `[PR-URL]` (`links.html.href`), `[PR-SOURCE-BRANCH]` (`source.branch.name`), `[PR-DEST-BRANCH]` (`destination.branch.name`), `[PR-AUTHOR]` (`author.display_name`), `[PR-STATE]` (`state`).

#### Selecting a single PR

Apply in order:

1. **One candidate** → select it.
2. **`dev` is a target branch of any candidate** → select that one. A PR whose `destination.branch.name` is exactly `dev` always wins over any other target (`18.X`, `16.X`, a release branch, …). This is the normal case for a ticket opened against several branches.
3. **Several candidates target `dev`** (unusual) → select the most recently updated (`updated_on`) and say so.
4. **No candidate targets `dev`** → do **not** guess. List the candidates (`#id — title — source → destination — state`) and ask the user which one to review, then continue with their choice.

Once selected, note the skipped ones — they are reported in Step 6 and must receive **no** review, **no** PR comment, and **no** separate Jira tag.

> The Jira tag in Step 9 is applied **once to the ticket**, not once per PR — so it is unaffected by how many PRs exist. The Step 10 PR comment goes only to the selected `[PR-ID]`.

### 5. Fetch the PR diff (frontend)

```bash
# diff
curl -sL -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff"
# changed files
curl -sL -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
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

If the ticket had more than one candidate PR, add a line above `Starting review...` naming the selection and what was skipped, so it is never silent:

```
Selected:  #[PR-ID] (target `dev`) — 1 of [N] PRs for this ticket
Skipped:   #15746 → 18.X   (not reviewed, not commented)
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

### Overall Score: [REVIEW-SCORE]/10  [SCORE-BADGE]

Store the numeric score as `[REVIEW-SCORE]` (an integer 1–10) — **Step 10 uses it to decide the PR's status**, so it must be a definite number, never a range or "N/A".

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

- **Approve**: Score 8-10 → "This PR is ready to merge." (PR left **open**.)
- **Request changes**: Score 6-7 → "Please address the warnings before merging." (PR set to **Draft**.)
- **Decline**: Score 1-5 → "This PR needs rework — declining, please reopen once addressed." (PR **declined**.)

---

*Review generated by Claude Code with [REVIEWER-LABEL]*
*PR: [PR-URL]*
```

### 9. Mark the ticket as reviewed by the frontend AI reviewer

Once the report is generated, **always** add the tag **`ai_code_review_Front`** to the ticket's AI field (`customfield_10613`).

**Do this automatically. Do NOT ask the user for confirmation, do not offer it as an option, and do not skip it because the review found issues** — the tag records that the frontend AI reviewer ran, regardless of the verdict or score. It is part of every frontend review. Step 10 (posting the report and applying the score-based PR status) is likewise automatic — this command asks for no confirmation at all on its write path.

**`customfield_10613` is a multi-value labels field (an array of strings). NEVER overwrite it — always append.** Other commands write their own tags to this same field, so replacing its contents destroys their work.

Hard rules:

- **Always read before writing.** The write must be built from the value you just read, never from scratch.
- **Every existing value must survive.** `[CURRENT-TAGS]` goes into the payload verbatim — never drop, reorder-away, rename, or "clean up" a tag you did not add, including tags you don't recognise.
- **Add exactly one tag**, `ai_code_review_Front`. Nothing else is added or removed.
- **Never send** a bare string (`"ai_code_review_Front"`), a single-select object (`{ "value": … }`), or a one-element array — each of those replaces the whole field.
- **If the read fails, do not write.** Without `[CURRENT-TAGS]` any write would clobber the field. Warn the user, skip the tagging, and continue.

Steps:

1. Read the current value: `getJiraIssue` (official `atlassian` plugin — see **Access**) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]` (treat `null` / missing as `[]`).
2. If `ai_code_review_Front` is already in `[CURRENT-TAGS]`, it is already set — skip the write entirely and note "already tagged".
3. Otherwise call `editJiraIssue` with **every** existing value plus the new one:
   ```json
   { "fields": { "customfield_10613": ["ai_code_review_Front", <...CURRENT-TAGS>] } }
   ```
   (`issueIdOrKey` = `[TICKET-NUMBER]`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`.)

   Expand `<...CURRENT-TAGS>` into the actual strings you read. Example — reading `["ai_Dev_Front", "ai_test_front_dev"]` must produce:
   ```json
   { "fields": { "customfield_10613": ["ai_code_review_Front", "ai_Dev_Front", "ai_test_front_dev"] } }
   ```
4. Verify: the array you send must contain `len([CURRENT-TAGS]) + 1` entries and include all of `[CURRENT-TAGS]`. If it doesn't, do not send it.
5. If the update fails, warn the user but continue.

Report the outcome in one line (`Jira: tagged ai_code_review_Front` / `already tagged` / `tagging failed — <reason>`).

> This is the same field `/oc-be-review` tags with `ai_code_review_back` and `/oc-be-calculate-ai-use` tags with `ai_Dev_back` / `ai_test_back_dev`. Because it is multi-value, all of these coexist — so this step must merge, not replace.

### 10. Post the review to the PR and set its status from the score

Both actions below are **mandatory and automatic** for the selected `[PR-ID]`. Do **not** ask for
confirmation and do **not** offer them as options — publishing the report and flagging the PR as
work-in-progress is the whole point of the command. They apply to the **selected PR only**; the skipped
PRs from Step 4 are never touched.

**10a. Post the review report as a PR comment — always.**

```bash
curl -s -X POST -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments" \
  -d @- <<'JSON'
{ "content": { "raw": "[REVIEW-REPORT-MARKDOWN]" } }
JSON
```

- Post the **full report from Step 8**, not a shortened summary.
- Build the JSON body with a real JSON encoder (or a heredoc as above) — the report contains newlines,
  backticks, quotes and code fences that break naive inline `-d '…'` quoting.
- On success Bitbucket returns the comment object; record its `links.html.href` as `[COMMENT-URL]`.
- If the POST fails, warn the user, print the report so nothing is lost, and continue to 10b.

**10b. Set the PR status from the score.**

The action is decided **solely by `[REVIEW-SCORE]`** from Step 8. The three bands cover 1–10 with no
gaps and no overlap:

| `[REVIEW-SCORE]` | Action on the PR | Effect |
|---|---|---|
| **8, 9, 10** | **Leave open — change nothing** | PR stays mergeable as-is |
| **6, 7** | **Mark as Draft** | merging blocked until *Mark as ready* |
| **1–5** | **Decline** | PR is closed |

Read the boundaries exactly: **8 leaves the PR open** (it is not drafted), and **5 is declined** (it is
not drafted). Only 6 and 7 produce a draft.

Preconditions for any status change:

- **Only open PRs can be mutated.** If `[PR-STATE]` is not `OPEN`, skip 10b entirely and say so.
- The report from 10a must already be posted, so the reason for a draft or decline is visible on the PR.

**Score 8-10 — leave open.** Take no action on the PR status. Do not draft it, do not decline it, do not
approve it. Report `PR status: open (unchanged)`.

**Score 6-7 — mark as Draft.** `PUT` accepts a partial pull request object, but **omitted fields can be
reset — most notably `reviewers`**. Read the PR first and send the existing values back alongside `draft`:

1. `GET …/pullrequests/[PR-ID]` and keep `title` and the `reviewers` array.
2. Send the update, preserving what you read:

   ```bash
   curl -s -X PUT -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
     -H "Content-Type: application/json" \
     "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]" \
     -d '{ "title": "[PR-TITLE]", "draft": true, "reviewers": [ {"uuid":"[REVIEWER-UUID]"}, … ] }'
   ```

3. **Verify it took** — re-`GET` the PR and check `draft` is now `true`.

- Marking as draft is **undocumented in the Bitbucket REST spec** — the `draft` attribute is returned by
  the API but the update endpoint documents only branches and description. If the `PUT` errors, or the
  verification still shows `draft: false`, do **not** retry blindly: tell the user the API refused it and
  that they need to use the PR's action menu (**…** → **Mark as draft**) at `[PR-URL]`.
- Never drop reviewers. If the `GET` in step 1 fails, skip the draft rather than sending a `PUT` that
  could clear them.
- **Draft blocks merging and suppresses reviewer notifications** until someone selects *Mark as ready*.

**Score 1-5 — decline the PR.** Declining **closes** the PR, so do it only after the report is posted:

```bash
curl -s -X POST -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/decline"
```

- The endpoint takes **no body**. The explanation lives in the review comment from 10a — which is why
  10a must succeed first. **If the 10a comment failed to post, do not decline**: warn the user and leave
  the PR open, so a PR is never closed without a stated reason.
- Verify by re-`GET`ting the PR: `state` should be `DECLINED`.
- Declining is **not** deleting — the author can reopen the PR from `[PR-URL]` after addressing the
  review. Say so in the report so the outcome is not mistaken for a dead end.
- If the decline fails, report the PR as still open and leave it alone.

**10c. Report the outcome and offer follow-ups.**

State the score and the resulting status explicitly, so the decision is auditable:

```
Score:          [REVIEW-SCORE]/10
Review posted:  [COMMENT-URL]
PR status:      <one of the three below>
```

- Score 8-10 → `open (unchanged) — ready to merge at [PR-URL]`
- Score 6-7 → `Draft — merging blocked until "Mark as ready"`
- Score 1-5 → `Declined — reopen at [PR-URL] once the review is addressed`

Then:

- If there are critical issues or warnings with suggested fixes:
  - "Would you like me to apply the suggested fixes automatically?" — if yes, use the `oc-fe-reviewer` agent to apply fixes to the local codebase.
- If a status change was skipped (PR not open, API refused the draft, comment failed so the decline was withheld), say which and what the user needs to do manually.

---

## Access

This command talks to two different systems:

| System | How | Credential |
|--------|-----|------------|
| **Jira** (`getJiraIssue`, `editJiraIssue`) | Official Atlassian Rovo MCP — install `atlassian@claude-plugins-official`, sign in via `/mcp` (OAuth) | none |
| **Bitbucket** (find PR, diff, comment) | Bitbucket REST API with `curl` | `BITBUCKET_EMAIL` + `BITBUCKET_ACCESS_TOKEN` |

Jira tool names are written **bare** so they resolve against whichever Atlassian MCP the environment
registers — the official plugin, or the claude.ai Atlassian connector (`mcp__…Atlassian_Rovo__<tool>`).

Bitbucket is **not** reachable over MCP: the Rovo server serves Bitbucket only under API-token auth,
never over the OAuth flow the official plugin uses.

`BITBUCKET_ACCESS_TOKEN` is an **Atlassian API token** (`ATATT…`, created at
https://id.atlassian.com/manage/api-tokens). It authenticates with **Basic** auth as `email:token`, so
`BITBUCKET_EMAIL` is required too — every call below uses
`curl -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}"`. Sending an `ATATT…` token as
`Authorization: Bearer` returns `401`. (A Bitbucket repository/workspace **Access Token** is the other
valid credential type and does use `Bearer` with no email — substitute
`-H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}"` if you use one.) App Passwords were removed
2026-07-28.

Note that `GET …/pullrequests/[PR-ID]/diff` and `…/diffstat` both answer **302** to a signed URL, so
they must be called with `curl -sL` — without `-L` the body comes back empty and the review would run on
nothing. The `pullrequests`, `…/[PR-ID]` and `…/comments` endpoints return `200` directly.

See the **Claude code AI assistant** parent page for how to create and set the credentials. If they are
missing or a call returns `401`, tell the user and stop (frontend path) or fall back to
`/oc-be-review list` (backend path).

## Examples

```bash
# Backend ticket (opencell-core) — delegates to /oc-be-review with the discovered PR
/oc-review-pr INTRD-36922
# → detects opencell-core → finds the PR for the ticket → runs /oc-be-tools:oc-be-review <PR>

# Frontend ticket (opencell-portal) — reviewed here with oc-fe-reviewer
/oc-review-pr INTRD-41200
# → fetches the ticket live from Jira (no cache) → reviews React/TypeScript
# → posts the report on the PR, sets its status from the score, tags the ticket ai_code_review_Front

# Ticket with one PR per target branch — only the `dev` one is reviewed
/oc-review-pr INTRD-45369
# → finds #15747 (→ dev) and #15746 (→ 18.X)
# → selects #15747 because it targets dev; #15746 is reported as skipped
# → reviews #15747, posts the report there, applies the score-based status, tags the ticket once
```

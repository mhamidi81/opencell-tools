---
description: Evaluate opencell-maco-project code changes against the MACO guidelines using the oc-mc-pr-reviewer agent, plus a requirements-conformance check against the JIRA ticket's acceptance criteria. Reviews uncommitted changes, a specific Bitbucket PR, or lets you pick from open PRs, and tags the JIRA ticket ai_code_review_back.
argument-hint: "[PR-number | list]"
---

# Review MACO Changes

You evaluate `opencell-maco-project` code changes and produce a review with an approval decision,
along **two** axes:

1. **Coding-guideline conformance** — performed by the `oc-mc-tools:oc-mc-pr-reviewer` agent, which
   reads the guideline files in `${CLAUDE_PLUGIN_ROOT}/guidelines/` (the same guidelines used to
   generate the code). This is *how* the code is written.
2. **Requirements conformance** — does the code actually implement the ticket's acceptance criteria,
   and is each documented test scenario covered? This is *whether the feature was delivered*.

A guideline-clean change can still be incomplete against its ticket; both axes must pass for an APPROVE.

> **MACO is NOT Opencell Core.** Never let the reviewer flag MACO code for breaking an opencell-core
> rule (`jakarta.*`, AGPL header, Liquibase, `BaseRs`) — those are inverted here.

## Argument Parsing

Parse `$ARGUMENTS`:

- **No argument** → **Mode LOCAL**: review the current uncommitted working-tree changes.
- **A number** (e.g. `821`) → **Mode PR**: review that pull request.
- **`list`** (also accept `pr` or `prs`) → **Mode LIST**: list open pull requests, let the user
  choose one, then continue as Mode PR.

---

## Resolve the ticket (shared, up front)

Both the conformance phase and the JIRA tag need the ticket key `[TICKET]`. Resolve it **once,
early** — reproduce Bitbucket's "Jira work item" derivation (title → branch → commits):

- Mode PR / LIST — first `[A-Z]+-\d+` match, checking in order: `[PR-TITLE]`, then
  `[PR-SOURCE-BRANCH]`, then the PR's commit messages
  (`GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/commits`, fetched only if the
  first two yield nothing).
- Mode LOCAL — first `[A-Z]+-\d+` match in the current branch name (`git branch --show-current`).
  MACO branches follow `{TICKET}_{target}` (e.g. `MACRD-1919_dev`).
- MACO tickets are normally in the **`MACRD`** project. If several distinct keys appear, ask which
  to use (default: the one in the title).
- **Validate** with `getJiraIssue`. If it 404s, the key is stale.

**If no valid key can be resolved (or it is stale), ASK THE USER for the ticket number** before
running conformance — do not silently skip it. Only if the user has no ticket to give do you skip
the conformance phase, and say so explicitly.

**Rename the session for this review.** The model cannot rename the session programmatically, so
surface the line and let the **user** run it. Non-blocking — present it once and continue:

```
/rename {TICKET} - review
```

In PR mode with no resolvable ticket, use `/rename PR {PR-ID} - review`.

---

## Requirements Conformance review

With `[TICKET]` resolved, fetch it via `getJiraIssue` with `fields: ["*all"]`. **Opencell stories
keep their content in custom fields — the standard `description` is usually EMPTY.** Read:

- `customfield_10134` → Requirement
- `customfield_10135` → Functional design
- `customfield_10136` → **Acceptance** (Gherkin scenarios) → `[SCENARIOS]`
- `customfield_10137` → Technical design

Collect the requirement/acceptance content verbatim into `[CRITERIA]` (what to build) and
`[SCENARIOS]` (documented test cases). Also read sub-tasks and comments.

- If the ticket resolves but has **no structured criteria**, note *"ticket has no structured
  acceptance criteria — conformance limited to the summary"* and do a best-effort pass.
  **Never fabricate criteria.**
- The reviewer agent has **no Atlassian access** — you (the orchestrator, which holds the MCP
  connection) fetch the ticket and **inject** `[CRITERIA]`/`[SCENARIOS]` into its prompt.

Append this instruction to the reviewer dispatch:

> "In addition to the guideline review, add a **Requirements Conformance** subsection mapping each
> acceptance criterion and documented test scenario to code / tests with `file:line`, status
> PRESENT / PARTIAL / ABSENT and COVERED / PARTIAL / NOT COVERED, and note any gaps."

### Verdict integration

- Any acceptance criterion **ABSENT**, or any documented test scenario **NOT COVERED** → the review
  is **failed** (`CHANGES_REQUESTED`) even if the guideline axis said APPROVE.
- **PARTIAL** items are surfaced as required follow-ups; use judgement on whether they block, and say why.
- Criteria that are purely frontend/GUI and unverifiable in this repo are marked **N/A (frontend)**
  and never block.

---

## Final verdict

The overall Status is the **most severe** of the two axes — either can fail it:

| Axis | Fails the review when |
|------|-----------------------|
| Guideline review (`oc-mc-pr-reviewer`) | its `**Status**:` line is `CHANGES_REQUESTED` |
| Requirements conformance | any acceptance criterion **ABSENT** or any documented test scenario **NOT COVERED** |

Overall = **APPROVE** only if both pass; otherwise **CHANGES_REQUESTED**. When conformance overrides
a guideline APPROVE, state the one-line reason (e.g. *"guideline APPROVE overridden: 2 acceptance
criteria unmet"*). A conformance skip (no ticket) does not fail the review — note it as skipped.

---

## Mode LOCAL — review uncommitted changes (no arguments)

1. If there are no uncommitted changes, tell the user and stop.
2. **Resolve the ticket** per the shared section and fetch `[CRITERIA]`/`[SCENARIOS]`.
3. **Guideline review** — dispatch `oc-mc-tools:oc-mc-pr-reviewer` (Task tool,
   `subagent_type: oc-mc-tools:oc-mc-pr-reviewer`):
   - "Review the current uncommitted working-tree changes against the MACO guidelines. Use
     `git status --short`, `git diff --stat HEAD`, and `git diff HEAD` to obtain the changes.
     Provide the full review with a score and a final Status."
   - Append the conformance instruction with `[CRITERIA]`/`[SCENARIOS]` injected.
4. Display the full combined report.
5. **Do not** write anything to Bitbucket in this mode — there is no PR.
6. **Tag the JIRA ticket** — apply `ai_code_review_back` to `[TICKET]` per **Tag the JIRA ticket**
   below (confirm before writing).

---

## Mode PR — review a specific pull request (`<number>`)

### 1. Resolve the repository

- Run `git remote get-url origin`.
- Extract `[REPO-OWNER]` and `[REPO-NAME]` (e.g. `opencellsoft` / `opencell-maco-project`).
- If the URL does not contain `bitbucket.org`, say "This command supports Bitbucket repositories
  only." and stop.
- Store `[PR-ID]` = the number from `$ARGUMENTS`.

### 2. Fetch the PR metadata, diff, and changed files

Use `curl` with Basic auth (see **Bitbucket Access** below).

- Metadata: `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]`
  - Extract `[PR-TITLE]` (`title`), `[PR-AUTHOR]` (`author.display_name`), `[PR-SOURCE-BRANCH]`
    (`source.branch.name`), `[PR-DEST-BRANCH]` (`destination.branch.name`), `[PR-STATE]` (`state`),
    `[PR-URL]` (`links.html.href`).
  - If the PR is not found, tell the user and stop.
- Diff: `GET …/pullrequests/[PR-ID]/diff` → `[PR-DIFF]`
- Changed files: `GET …/pullrequests/[PR-ID]/diffstat` → `[CHANGED-FILES]`

> **Both diff endpoints answer 302 to a signed URL — call them with `curl -sL`.** Without `-L` the
> body is empty and the reviewer silently reviews nothing.

### 3. Show an overview

```
MACO Pull Request Review
========================
PR:      #[PR-ID] — [PR-TITLE]
Author:  [PR-AUTHOR]
Branch:  [PR-SOURCE-BRANCH] → [PR-DEST-BRANCH]
State:   [PR-STATE]
URL:     [PR-URL]
Files:   [N] files changed

Running review...
```

### 4. Resolve the ticket and its criteria

Per the shared sections, before the review, so the criteria can be injected.

### 5. Run the guideline review

Dispatch `oc-mc-tools:oc-mc-pr-reviewer` (`subagent_type: oc-mc-tools:oc-mc-pr-reviewer`), passing:
- the full `[PR-DIFF]` content,
- the `[CHANGED-FILES]` list,
- context: "This is a review of PR #[PR-ID]: [PR-TITLE]. Review the provided diff against the MACO
  guidelines. For each issue give the file path and line context, and a concrete fix. End with the
  final Status line.",
- the conformance instruction with `[CRITERIA]`/`[SCENARIOS]` injected.

Extract the guideline decision from its `**Status**:` line and the score from its
`## Overall Score: X/10` line.

### 6. Update the PR and tag the ticket (confirm first)

Compute the combined verdict per **Final verdict**. Posting to a pull request and tagging JIRA are
outward-facing actions. **Show the user what will be posted and set, and ask for confirmation before
writing.** Present:
- the review comment body (the report plus the Requirements Conformance section, or a concise summary),
- the action: APPROVE (acceptable) or REQUEST CHANGES (failed), plus the one-line reason if
  conformance overrode a guideline APPROVE,
- the JIRA tag: `ai_code_review_back` on `customfield_10613` of `[TICKET]`.

On confirmation:

1. Post the review as a comment:
   - `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments`
   - body: `{ "content": { "raw": "[REVIEW-MARKDOWN]" } }`
2. Set the verdict:
   - acceptable → `POST …/pullrequests/[PR-ID]/approve`
   - failed → `POST …/pullrequests/[PR-ID]/request-changes`
3. **Tag the JIRA ticket** per the section below.
4. Confirm: "Posted review and marked PR #[PR-ID] as **[Approved | Changes requested]**, tagged
   [TICKET] ai_code_review_back — [PR-URL]"

If the user declines, print the review and the PR URL so they can act manually, and stop without
writing (no PR post, no JIRA tag).

---

## Mode LIST — pick a PR (`list`)

1. Resolve the repository (Step 1 of Mode PR).
2. `GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests?state=OPEN`
3. Present a numbered table:

   ```
   Open Pull Requests — [REPO-OWNER]/[REPO-NAME]
   #   PR ID   Title                                  Author        Branch → Dest
   1   821     MACRD-1919 migre les champs de date     M. Stitane    MACRD-1919_dev → dev
   ```

4. Ask the user to choose a row (or PR ID), then continue with **Mode PR** for that `[PR-ID]`.
5. If there are no open PRs, tell the user and stop.

---

## Tag the JIRA ticket (`ai_code_review_back`)

Whenever a review runs, record it on the ticket by adding **`ai_code_review_back`** to
`customfield_10613` — regardless of the verdict; the tag means "AI performed a code review on this
ticket". **Areas are defined by discipline, not repository**: MACO is Java backend work, so it uses
the ordinary backend tag — do **not** invent a MACO-specific tag.

Use `[TICKET]` already resolved by the shared section. If the user confirmed there is no ticket, skip
tagging and say so.

**`customfield_10613` is a multi-value labels field — never overwrite it.** Several commands tag the
same field and they must coexist.

1. Read the current value (`getJiraIssue` with `fields: ["customfield_10613"]`). If
   `ai_code_review_back` is already present, **skip the edit** and note it.
2. Otherwise `editJiraIssue` with **all existing values plus** `ai_code_review_back` — never a bare
   string, never a single-select `{ "value": … }` object, never a one-element array, all of which
   replace the whole field:
   - Labels-style (the live shape): `{ "fields": { "customfield_10613": ["ai_code_review_back", <existing...>] } }`
3. **If the read fails, skip the write** rather than clobbering the field.
4. If rejected because the value is not an allowed option, report the error verbatim and do not
   retry blindly.

> This is the only JIRA write this command makes. In Mode PR/LIST confirm it together with the PR
> update; in Mode LOCAL confirm it on its own before writing.

---

## Bitbucket Access

This command talks to Bitbucket over its REST API with `curl`.

**Use Basic auth, not Bearer.** `BITBUCKET_ACCESS_TOKEN` holds an **Atlassian API token**
(`ATATT…`), which authenticates as `email:token` over **Basic** auth. Both `BITBUCKET_EMAIL` and
`BITBUCKET_ACCESS_TOKEN` are required:

```bash
# GET the PR diff — note -L, the endpoint answers 302 to a signed URL
curl -sL -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/diff"

# POST a comment
curl -s -X POST -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments" \
  -d '{ "content": { "raw": "[REVIEW-MARKDOWN]" } }'

# Approve / request changes
curl -s -X POST -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/approve"
curl -s -X POST -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/request-changes"
```

`curl -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}"` returns **401** for `ATATT…` tokens.
Create the token at https://id.atlassian.com/manage/api-tokens. App Passwords were removed 2026-07-28.

**Fallback — manual.** If the variables are missing or a call fails, run the review (Mode LOCAL still
works fully) and, for PR modes, print the review plus the PR URL so the user can post and
approve/decline manually.

> The JIRA tag uses the Atlassian MCP and is independent of Bitbucket access — apply it even when the
> PR update falls back to manual, as long as the ticket resolves and the user confirms.

---

## Examples

```bash
# Review current uncommitted changes
/oc-mc-tools:oc-mc-review

# Review pull request #821 and (after confirmation) approve or request changes
/oc-mc-tools:oc-mc-review 821

# List open PRs, pick one, then review it
/oc-mc-tools:oc-mc-review list
```

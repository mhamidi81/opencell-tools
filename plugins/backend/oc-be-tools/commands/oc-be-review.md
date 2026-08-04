---
description: Evaluate Opencell backend code changes against the project guidelines using the oc-be-pr-reviewer agent, plus a requirements-conformance check against the JIRA ticket's acceptance criteria and test scenarios, augmented with a SonarQube quality-gate summary. Reviews uncommitted changes, a specific Bitbucket PR, or lets you pick from open PRs, and tags the JIRA ticket ai_code_review_back.
argument-hint: "[PR-number | list] [light]"
---

# Review Backend Changes

You evaluate Opencell backend code changes and produce a review with an approval decision, along **two** axes:

1. **Coding-guideline conformance** — performed by the `oc-be-tools:oc-be-pr-reviewer` agent, which reads the guideline files in `${CLAUDE_PLUGIN_ROOT}/guidelines/` (the same guidelines used to generate the code). This is *how* the code is written.
2. **Requirements conformance** — performed by the `oc-be-tools:oc-be-conformance-reviewer` agent(s): does the code actually implement the ticket's acceptance criteria, and is each documented test scenario covered? This is *whether the feature was delivered*. See **Requirements Conformance review** below. It runs on **every** review.

A guideline-clean change can still be incomplete against its ticket; both axes must pass for an APPROVE.

## Argument Parsing

Parse `$ARGUMENTS` into a **mode token** and an optional **depth modifier**. They can appear together in any order (e.g. `15042 light`, `light`, `list`).

Mode token:
- **No mode token** → **Mode LOCAL**: review the current uncommitted working-tree changes.
- **A number** (e.g. `15042`) → **Mode PR**: review that pull request.
- **`list`** (also accept `pr` or `prs`) → **Mode LIST**: list open pull requests and let the user choose one, then continue as Mode PR.

Depth modifier (controls the **Requirements Conformance** phase only):
- **absent → DEEP (default)**: multi-agent conformance fan-out (thorough).
- **`light`** (also accept `quick`) → **LIGHT**: single-pass conformance folded into the guideline reviewer (cheaper).

> Distinguishing "no PR number" cases: a bare `/oc-be-tools:oc-be-review` always means *local uncommitted review*. To browse pull requests instead, the user must pass the `list` keyword. The `light` modifier never selects a mode by itself — `/oc-be-tools:oc-be-review light` is a *local, light-conformance* review.

---

## Resolve the ticket (shared, up front)

Both the **Requirements Conformance** phase and the **JIRA tag** need the ticket key `[TICKET]`. Resolve it **once, early** — reproduce Bitbucket's "Jira work item" derivation (title → branch → commits):

- Mode PR / LIST — first `[A-Z]+-\d+` match, checking in order: `[PR-TITLE]`, then `[PR-SOURCE-BRANCH]`, then the PR's commit messages (`GET /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/commits`, fetched only if the first two yield nothing).
- Mode LOCAL — first `[A-Z]+-\d+` match in the current branch name (`git branch --show-current`).
- If several distinct keys appear, ask the user which to use (default: the one in the title).
- **Validate** with `getJiraIssue` (Atlassian MCP, site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`; resolve via `getAccessibleAtlassianResources` if unknown). If it 404s, the key is stale.

**If no valid key can be resolved from any source (or it is stale), ASK THE USER for the ticket number** before running conformance — do not silently skip it. Only if the user has no ticket to give do you skip the conformance phase, and say so explicitly. The resolved `[TICKET]` is reused by the JIRA-tag step (no second resolution).

**Rename the session for this review.** Once `[TICKET]` (or, in PR mode, `[PR-ID]`) is known, name the session so it is findable later.

> **Mechanism note:** the model cannot rename the session programmatically — `/rename` is a user-only slash command (the model cannot invoke it), there is no `claude` CLI subcommand for it, and hooks cannot do it either. So the command surfaces the exact line and the **user** runs it.

Show the user this line and ask them to run it (append `- review` to the ticket, or the PR number when no ticket resolves):

```
/rename {TICKET} - review
```

For example `/rename INTRD-45279 - review`; in PR mode with no resolvable ticket, use `/rename PR {PR-ID} - review`. This step is **non-blocking** — present the line once and continue the review regardless of whether the user runs it.

---

## Requirements Conformance review (ticket acceptance criteria)

The guideline review checks *how* the code is written; this phase checks *whether it does what the ticket asked* — the difference between "conventions followed" and "feature delivered". It runs on **every** review. Depth is DEEP by default, LIGHT with the `light` modifier.

### Fetch the ticket's criteria

With `[TICKET]` from **Resolve the ticket**, fetch it via Atlassian MCP: `getJiraIssue` with `fields: ["summary","description"]`. From the description, extract the structured requirement sections when present — headings such as *Acceptance Criteria*, *Test Scenarios*, *Behaviour & Flow*, *Deliverables*, *Messages & Errors*, *Data & Model Impact*, *API Surface*. Collect them verbatim into `[CRITERIA]` (what to build) and `[SCENARIOS]` (documented test cases).

- If the ticket resolves but has **no structured criteria** (a terse ticket), note *"ticket has no structured acceptance criteria — conformance limited to the summary"* and do a best-effort pass against the summary. **Never fabricate criteria.**
- The conformance agents have **no Atlassian access** — you (the orchestrator, which holds the MCP connection) fetch the ticket and **inject** `[CRITERIA]`/`[SCENARIOS]` into their prompts.

### DEEP mode (default)

Dispatch `oc-be-tools:oc-be-conformance-reviewer` agents **in parallel** (Task tool, `subagent_type: oc-be-tools:oc-be-conformance-reviewer`), splitting the work so each stays focused. Default split:

1. **Implementation conformance** — does the code implement each item in `[CRITERIA]` (rules, modes, data model, API surface, messages)? Each mapped to `file:line`, status PRESENT / PARTIAL / ABSENT.
2. **Test-scenario coverage** — is each item in `[SCENARIOS]` covered by a test (unit `method @ file:line` and/or Postman request)? Status COVERED / PARTIAL / NOT COVERED.

If `[CRITERIA]` is large (roughly > 10 discrete items), split axis 1 across two agents by criterion cluster. Pass each agent: its scope hint, the relevant `[CRITERIA]`/`[SCENARIOS]` subset (injected verbatim), and the diff source — the full `[PR-DIFF]` in Mode PR, or "review the working tree via `git diff HEAD`" in Mode LOCAL. Merge the agents' tables into one **Requirements Conformance** section and read each agent's `**Conformance**:` line.

### LIGHT mode (`light` modifier)

Skip the fan-out. Inject `[CRITERIA]` and `[SCENARIOS]` into the single `oc-be-pr-reviewer` run (see each mode's review step) as an extra instruction: *"In addition to the guideline review, add a Requirements Conformance subsection mapping each acceptance criterion and documented test scenario to code / tests with `file:line`, status PRESENT/ABSENT and COVERED/NOT COVERED, and note any gaps."* One agent, one pass.

### Verdict integration

Fold conformance into the final decision at the same weight as a blocking Sonar issue:
- Any acceptance criterion **ABSENT**, or any documented test scenario **NOT COVERED**, → the review is **failed** (`CHANGES_REQUESTED`) even if the guideline reviewer said APPROVE.
- **PARTIAL** items are surfaced as required follow-ups; use judgement on whether they block, and say why.
- Criteria that are purely frontend/GUI and unverifiable in the backend repo are marked **N/A (frontend)** and never block.

---

## Final verdict

The review's overall Status is the **most severe** of the three axes — any one can fail it:

| Axis | Fails the review when |
|------|-----------------------|
| Guideline review (`oc-be-pr-reviewer`) | its `**Status**:` line is `CHANGES_REQUESTED` |
| Requirements conformance | any acceptance criterion **ABSENT** or any documented test scenario **NOT COVERED** (any conformance agent `NONCONFORMANT`) |
| SonarQube | failing quality gate, or any BLOCKER/CRITICAL issue on the changed files |

Overall = **APPROVE** only if all three pass; otherwise **CHANGES_REQUESTED**. When a non-guideline axis overrides a guideline APPROVE, state the one-line reason (e.g. *"guideline APPROVE overridden: 2 acceptance criteria unmet"*). Sonar and conformance skips (unavailable MCP, no ticket) do not fail the review — note them as skipped.

---

## Mode LOCAL — review uncommitted changes (no arguments)

1. If there are no uncommitted changes, tell the user and stop.
2. **Resolve the ticket** per the shared section (branch name; ask the user if unresolved), and fetch `[CRITERIA]`/`[SCENARIOS]` per **Requirements Conformance review**.
3. **Guideline review** — dispatch the `oc-be-tools:oc-be-pr-reviewer` agent (Task tool, `subagent_type: oc-be-tools:oc-be-pr-reviewer`):
   - "Review the current uncommitted working-tree changes against the Opencell guidelines. Use `git status --short`, `git diff --stat HEAD`, and `git diff HEAD` to obtain the changes. Provide the full review with a score and a final Status."
   - **LIGHT mode only**: append the LIGHT-mode conformance instruction (inject `[CRITERIA]`/`[SCENARIOS]`) so this single agent also produces the conformance subsection.
4. **Requirements conformance** — **DEEP mode**: run the DEEP fan-out (conformance agents told to "review the working tree via `git diff HEAD`"), merge their tables, read each `**Conformance**:` line. **LIGHT mode**: already produced in step 3.
5. **SonarQube analysis** — run the **SonarQube analysis (opencell-core)** section against the current branch and append `[SONAR-SUMMARY]` to the report (skip gracefully if `oc-sonar-mcp` is unavailable or the branch has not been analysed).
6. **Combine the verdict** per the **Final verdict** section (guideline Status + conformance + Sonar) and display the full combined report (guideline review + Requirements Conformance section + `[SONAR-SUMMARY]`).
7. **Do not** write anything to Bitbucket in this mode — there is no PR.
8. **Tag the JIRA ticket** (a review was run) — apply `ai_code_review_back` to the already-resolved `[TICKET]` per **Tag the JIRA ticket** below.

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

### 4. Resolve the ticket and its criteria

**Resolve the ticket** per the shared section (title → branch → commits; ask the user if unresolved), and fetch `[CRITERIA]`/`[SCENARIOS]` per **Requirements Conformance review**. Do this before the review so the criteria can be injected.

### 5. Run the guideline review

Dispatch the `oc-be-tools:oc-be-pr-reviewer` agent (`subagent_type: oc-be-tools:oc-be-pr-reviewer`), passing:
- The full `[PR-DIFF]` content.
- The `[CHANGED-FILES]` list.
- Context: "This is a review of PR #[PR-ID]: [PR-TITLE]. Review the provided diff against the Opencell guidelines. For each issue give the file path and line context, and a concrete fix. End with the final Status line."
- **LIGHT mode only**: append the LIGHT-mode conformance instruction (inject `[CRITERIA]`/`[SCENARIOS]`) so this agent also produces the conformance subsection.

Extract the guideline decision from its `**Status**:` line (`APPROVE` / `CHANGES_REQUESTED`).

### 6. Requirements conformance

**DEEP mode**: run the DEEP fan-out per **Requirements Conformance review**, passing each conformance agent the `[PR-DIFF]` as the diff source; merge their tables and read each `**Conformance**:` line. **LIGHT mode**: already produced in step 5.

### 7. SonarQube analysis

Run the **SonarQube analysis (opencell-core)** section against `[PR-SOURCE-BRANCH]` and display `[SONAR-SUMMARY]` alongside the report. Skip gracefully if `oc-sonar-mcp` is unavailable.

### 8. Update the PR and tag the ticket (confirm first)

Compute the combined verdict per the **Final verdict** section (guideline Status + conformance + Sonar). Posting to a pull request and tagging JIRA are outward-facing actions. **Show the user what will be posted and set, and ask for confirmation before writing.** Present:
- The review comment body (the guideline report **plus the Requirements Conformance section** plus `[SONAR-SUMMARY]`, or a concise summary of each).
- The action: APPROVE (acceptable) or REQUEST CHANGES (failed), and the one-line reason if conformance or Sonar overrode a guideline APPROVE.
- The JIRA tag: `ai_code_review_back` on `customfield_10613` of `[TICKET]`.

On confirmation:

1. Post the review as a comment (include the Requirements Conformance section and `[SONAR-SUMMARY]` in `[REVIEW-MARKDOWN]`):
   - `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/comments`
   - body: `{ "content": { "raw": "[REVIEW-MARKDOWN]" } }`
2. Set the verdict:
   - If acceptable: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/approve`
   - If failed: `POST /repositories/[REPO-OWNER]/[REPO-NAME]/pullrequests/[PR-ID]/request-changes`
3. **Tag the JIRA ticket** — apply `ai_code_review_back` to the already-resolved `[TICKET]` per **Tag the JIRA ticket** below.
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

**Ticket.** Use `[TICKET]` already resolved by the shared **Resolve the ticket** section (title → branch → commits, validated with `getJiraIssue`, reproducing Bitbucket's "Jira work item" derivation) and its summary. That section already asks the user when the key cannot be resolved, so by this point `[TICKET]` is either a validated key or the user has confirmed there is none — in the latter case, skip tagging and say so (nothing to tag).

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
# Review current uncommitted changes — DEEP conformance by default
/oc-be-tools:oc-be-review

# Same, but LIGHT conformance (single-pass, cheaper)
/oc-be-tools:oc-be-review light

# Review pull request #15042 (DEEP) and (after confirmation) approve or request changes
/oc-be-tools:oc-be-review 15042

# Review pull request #15042 with LIGHT conformance
/oc-be-tools:oc-be-review 15042 light

# List open PRs, pick one, then review it
/oc-be-tools:oc-be-review list
```

> Every review runs both axes — coding-guideline conformance **and** requirements conformance against the ticket's acceptance criteria / test scenarios. Conformance is DEEP (multi-agent) by default; add `light` for a single-pass conformance check. If the ticket cannot be resolved from the PR/branch, the command asks you for the ticket number.

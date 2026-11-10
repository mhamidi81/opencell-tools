---
description: Review Opencell backend changes in an isolated, reproducible run — fresh headless Claude processes with no conversation, no user memory and no personal settings, pinned to one model and effort, judging a frozen input bundle (diff, ticket acceptance items split by script, agreed scope, guideline rule catalogue, deterministic mechanical checks) with the verdict computed by script — plus a SonarQube quality-gate summary. Reviews uncommitted changes, a commit range, a specific Bitbucket PR, or lets you pick from open PRs; records the reviewed code state for the commit hold and /oc-be-calculate-ai-use, and tags the JIRA ticket ai_code_review_back.
argument-hint: "[PR-number | list | range <A>..<B>]"
---

# Review Backend Changes

You evaluate Opencell backend code changes and produce a review with an approval decision, along **two** axes:

1. **Coding-guideline conformance** — every rule of a fixed catalogue (the `oc-be-tools:oc-be-pr-reviewer` criteria, read against the guideline files in `${CLAUDE_PLUGIN_ROOT}/guidelines/`) gets PASS / FAIL / N/A. This is *how* the code is written.
2. **Requirements conformance** — every acceptance item of the ticket (and of the agreed scope) gets PRESENT / PARTIAL / ABSENT, every test scenario COVERED / PARTIAL / NOT COVERED (the `oc-be-tools:oc-be-conformance-reviewer` method). This is *whether the feature was delivered*.

A guideline-clean change can still be incomplete against its ticket; both axes must pass for an APPROVE.

> **Why the review runs isolated.** A review run inside the developer's session sees the conversation that produced the code and the developer's personal memory, and an unconstrained reviewer builds its own checklist each time — so the developer, a re-run and the dev lead got different reports. The review is therefore **not** done in this conversation. You (the orchestrator) only resolve the ticket, freeze the inputs and present the result; `${CLAUDE_PLUGIN_ROOT}/scripts/isolated_review.py` does the rest:
> - **Same input:** the diff, the ticket's acceptance items (split from the Jira fields *by script* into a numbered list), the agreed scope, the rule catalogue and deterministic mechanical checks (javax, `var`, AGPL header, Liquibase current/rebuild pairing, `{{$timestamp}}`) go into a bundle; the same code gives a byte-identical bundle.
> - **Same reviewer:** each axis runs as a fresh headless `claude -p` process — no conversation, no user `CLAUDE.md`, no auto-memory, no `settings.local.json`, no plugin hooks — pinned to **opus, effort high**, read-only tools, answering in a JSON schema that demands a status for *every* rule and item.
> - **Same rules for the verdict:** the score and APPROVE / CHANGES_REQUESTED are computed by the script from those statuses; the model never picks the verdict.
> - **Fresh every time:** a report is never reused; every run reviews anew. The script only records *that* a code state was reviewed (and the verdict), for the commit hold and `/oc-be-calculate-ai-use`.
>
> Do not add your own review findings, re-judge items, or soften the verdict: present the script's report as is. You may explain a finding when asked.

## Argument Parsing

Parse `$ARGUMENTS` into a **mode token**:
- **No mode token** → **Mode LOCAL**: review the current uncommitted changes (tracked changes vs `HEAD` plus new untracked source files).
- **A number** (e.g. `15042`) → **Mode PR**: review that pull request.
- **`list`** (also accept `pr` or `prs`) → **Mode LIST**: list open pull requests and let the user choose one, then continue as Mode PR.
- **`range <A>..<B>`** → **Mode RANGE**: review committed changes (e.g. `range HEAD~1..HEAD`), as Mode LOCAL but on that diff. `/oc-be-calculate-ai-use` uses it for work committed without a review.

> A bare `/oc-be-tools:oc-be-review` always means *local uncommitted review*. To browse pull requests, pass `list`. The former `light` modifier is accepted and ignored: the isolated review always runs the same passes, which is what makes repeated runs comparable.

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

## The isolated review (shared by every mode)

### 1. Ticket fields

The review script needs the ticket's requirement fields: `summary`, `description`, `comment`, and the story custom fields `customfield_10134` Requirement, `customfield_10135` Functional design, `customfield_10136` Acceptance (test-case table or Gherkin), `customfield_10137` Technical design (valid for `opencellsoft.atlassian.net`). **Opencell stories keep their requirements in these custom fields; the `description` is usually empty.**
- **Preferred:** pass `--fetch-jira` to `prepare` — the script reads them over Jira REST with `JIRA_EMAIL` + `JIRA_API_TOKEN` (the same credentials the report plugins use).
- **Fallback** (those variables are not set): `getJiraIssue` (Atlassian MCP, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`) with `fields` = the list above and `responseContentFormat: "adf"`, save the JSON response to a file, and pass it with `--ticket-json <file>`.

The script splits the fields into numbered items **deterministically**: test scenarios from the Acceptance field's test-case table rows (else Gherkin `Scenario` blocks, else bullets; a "Dataset" list is test data, never an item); criteria from the Functional design (else the Requirement); the "Expected" section of a bug's description; and the agreed scope. **Agreed scope:** bugs and enablers are specified in conversation; the `_planning.json` checkpoints in `.claude/cache/ai-stats/[TICKET]-*/` (written by `/oc-be-implement` after plan approval, or by the edit hook before the first ad-hoc code change) contribute their `acceptance[]` as criteria and their *required* `deliverables` as scenarios — read automatically from the repository. When nothing structured exists, the ticket summary is the single item, and the report says so. **Never add, merge or reword items yourself.**

### 2. Prepare, run, verdict

```bash
R="${CLAUDE_PLUGIN_ROOT}/scripts/isolated_review.py"
python "$R" prepare --repo . --ticket [TICKET] --fetch-jira            # Mode LOCAL
#   Mode RANGE: add --range <A>..<B>     Mode PR: add --diff-file <file holding [PR-DIFF]>
#   no Jira credentials: replace --fetch-jira with --ticket-json <file>
python "$R" run --bundle "<bundle printed by prepare>"                   # 3 isolated runs in parallel, minutes
python "$R" verdict --bundle "<bundle>" --record                          # report.md on stdout; --record only in LOCAL/RANGE
```

- `prepare` prints the bundle directory (under `~/.claude/oc-be-tools/reviews/`), the number of files, criteria, scenarios and mechanical findings, and the input hash. If it reports an empty diff, tell the user there is nothing to review and stop.
- `run` takes several minutes on a real change (three opus/high runs). Run it **in the background** (`run_in_background`) and wait for its completion notice; do not poll. Tell the user it is running and roughly how long.
- `verdict` prints `report.md`: score, APPROVE / CHANGES_REQUESTED, the failed rules with `file:line` and fix, the acceptance-criteria and test-scenario tables, and suggestions. A run that did not complete (e.g. not logged in, timeout) makes the verdict CHANGES_REQUESTED and is listed at the top — report it; never fill the gap yourself.

### 3. Final verdict

The overall Status is the **most severe** of the three axes:

| Axis | Fails the review when |
|------|-----------------------|
| Guidelines (script) | any **critical** or **major** rule FAIL (mechanical findings always FAIL their rule), or a rule not evaluated |
| Requirements (script) | any criterion **ABSENT** or any scenario **NOT COVERED**, or an item not evaluated |
| SonarQube | failing quality gate, or any BLOCKER/CRITICAL issue on the changed files |

The first two are already folded into the script's verdict; you add only Sonar: a Sonar failure turns an APPROVE into CHANGES_REQUESTED, with the one-line reason. A Sonar skip (MCP unavailable, branch not analysed) does not fail the review — note it as skipped. PARTIAL items are listed as follow-ups; frontend/GUI items are N/A and never block.

---

## Mode LOCAL — review uncommitted changes (no arguments)

1. If there are no uncommitted changes (`git status --short`, ignoring untracked non-source files), tell the user and stop.
2. **Resolve the ticket** per the shared section (branch name; ask the user if unresolved).
3. **Isolated review** — `prepare` (default diff), `run` in the background, `verdict --record`.
4. **SonarQube analysis** — run the **SonarQube analysis (opencell-core)** section against the current branch and append `[SONAR-SUMMARY]` (skip gracefully if `oc-sonar-mcp` is unavailable or the branch has not been analysed).
5. **Show the report** (`report.md` + `[SONAR-SUMMARY]` + the overall Status per the **Final verdict**). `--record` has stored the reviewed code state: the commit hold lets Claude's commit of exactly this change set through, and `/oc-be-calculate-ai-use` sees it as reviewed. Any further code change needs a new review.
6. **Do not** write anything to Bitbucket in this mode — there is no PR.
7. **Tag the JIRA ticket** (a review was run) — apply `ai_code_review_back` to the already-resolved `[TICKET]` per **Tag the JIRA ticket** below.

## Mode RANGE — review committed changes (`range <A>..<B>`)

As Mode LOCAL, with `prepare --range <A>..<B>`. `--record` stores "reviewed at commit `<B>`", which `/oc-be-calculate-ai-use` accepts for that commit. The conformance runs judge the code as it stands in the working tree, so run it with `<B>` (or a descendant) checked out.

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

### 4. Resolve the ticket

**Resolve the ticket** per the shared section (title → branch → commits; ask the user if unresolved).

### 5. Isolated review

Write `[PR-DIFF]` to a file and run the isolated review with `prepare --diff-file <file>` (plus `--fetch-jira` or `--ticket-json`), `run` in the background, then `verdict` **without** `--record` (a PR is not the local working tree). The conformance runs then judge from the diff only, because the local checkout is not necessarily the PR branch. When the PR's source branch is checked out locally, Mode RANGE on `<destination>..<source>` gives the conformance runs the full code to read.

### 6. Verdict

Take the script's verdict and report; Sonar is added in step 7 per the **Final verdict**.

### 7. SonarQube analysis

Run the **SonarQube analysis (opencell-core)** section against `[PR-SOURCE-BRANCH]` and display `[SONAR-SUMMARY]` alongside the report. Skip gracefully if `oc-sonar-mcp` is unavailable.

### 8. Update the PR and tag the ticket (confirm first)

Compute the combined verdict per the **Final verdict** section (guideline Status + conformance + Sonar). Posting to a pull request and tagging JIRA are outward-facing actions. **Show the user what will be posted and set, and ask for confirmation before writing.** Present:
- The review comment body: the script's `report.md` plus `[SONAR-SUMMARY]` (shorten only the tables if the comment would be too long — never the findings or the verdict).
- The action: APPROVE (acceptable) or REQUEST CHANGES (failed), and the one-line reason if conformance or Sonar overrode a guideline APPROVE.
- The JIRA tag: `ai_code_review_back` on `customfield_10613` of `[TICKET]`.

On confirmation:

1. Post the review as a comment (`report.md` and `[SONAR-SUMMARY]` in `[REVIEW-MARKDOWN]`):
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
# Review the current uncommitted changes (isolated runs; records the reviewed state for the commit hold)
/oc-be-tools:oc-be-review

# Review committed changes, e.g. the last commit
/oc-be-tools:oc-be-review range HEAD~1..HEAD

# Review pull request #15042 and (after confirmation) approve or request changes
/oc-be-tools:oc-be-review 15042

# List open PRs, pick one, then review it
/oc-be-tools:oc-be-review list
```

> Every review runs both axes — coding-guideline conformance **and** requirements conformance against the ticket's acceptance items, test scenarios and agreed scope — in isolated headless runs, so the developer, a re-run and the dev lead review with the same model, the same inputs and the same verdict rules. Expect a few minutes and a few dollars per review of a real change. If the ticket cannot be resolved from the PR/branch, the command asks you for the ticket number.

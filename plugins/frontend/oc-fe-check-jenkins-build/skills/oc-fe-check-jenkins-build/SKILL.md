---
name: oc-fe-check-jenkins-build
description: Check the latest Jenkins build of a branch (default dev) at https://jenkins.opencell.eu/job/<branch>/. If it failed in the frontend stages (Checkout Front / Build Front), read the stage log, find the cause, fix opencell-portal under ticket INTRD-22890 (a local build must pass first), open and merge the PR on Bitbucket, then re-run the Jenkins job with the failed build's parameters and watch the frontend stages. Fully automatic, one fix attempt per run. Jenkins via REST (JENKINS_USER + JENKINS_API_TOKEN), Bitbucket via REST (BITBUCKET_ACCESS_TOKEN).
argument-hint: "[BRANCH]"
---

# /oc-fe-check-jenkins-build

Keeps a branch's Jenkins pipeline green when the **portal** breaks it. The job at
`https://jenkins.opencell.eu/job/[BRANCH]/` builds core and portal together and deploys
the result; this skill only ever acts on its **frontend stages**.

`[BRANCH]` is the first argument, default `dev`.

## Constants

| Name | Value |
|---|---|
| Ticket | `INTRD-22890` |
| Jenkins job | `https://jenkins.opencell.eu/job/[BRANCH]/` |
| Frontend stages | `Checkout Front`, `Build Front` |
| Repository | `opencellsoft/opencell-portal` |
| Fix branch | `fix/INTRD-22890-build-[N]` (`[N]` = failed build number) |
| Commit / PR title | `INTRD-22890: fix Jenkins build #[N] – [CAUSE]` |

## Rules — non-negotiable

1. **Fully automatic.** Never ask for confirmation. In exchange every step **fails closed**:
   no PR without a passing local build, no merge without a PR, no rebuild after a failed
   merge, nothing after a failed push.
2. **One fix attempt per run.** If the rebuild fails the frontend stages again, report and
   stop — never fix a second time in the same run.
3. **Minimal fix only.** Fix the build error and nothing else. Never add `@ts-ignore`,
   `@ts-expect-error` or `eslint-disable`; never edit `tsconfig*.json`, ESLint or Vite
   config; never delete or skip tests; never change dependencies unless the log proves a
   dependency is the cause.
4. **Infra failures get no code change** — rebuild only.
5. **No AI attribution** in the commit or the PR description (no `Co-Authored`-style trailer).
6. Never print a token.

## Auth

Jenkins auth is handled by the scripts (`JENKINS_USER` + `JENKINS_API_TOKEN`, with a
fallback to the `export` lines of `~/.bashrc`). They exit **2** on an auth problem with the
fix in the message — show it and stop.

Bitbucket: shell state does not persist between Bash calls, so **start every Bitbucket
call with this block**:

```bash
[ -z "$BITBUCKET_ACCESS_TOKEN" ] && eval "$(grep -E '^\s*export\s+BITBUCKET_(EMAIL|ACCESS_TOKEN)=' ~/.bashrc)"
BB_AUTH=(-u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}")
[[ "$BITBUCKET_ACCESS_TOKEN" == ATCTT* ]] && BB_AUTH=(-H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}")
BB=https://api.bitbucket.org/2.0/repositories/opencellsoft/opencell-portal
```

On a `401`, say both schemes: an `ATCTT…` repository/workspace access token is sent as
`Authorization: Bearer`; an `ATATT…` Atlassian API token is sent as Basic
`BITBUCKET_EMAIL:token`. Merging needs `pullrequest:write`.

## Step 1 — Read the build status

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/oc-fe-check-jenkins-build/scripts/jenkins_status.py" --branch "[BRANCH]"
```

Exit `2` → auth (show stderr, stop). Exit `3` → "No Jenkins job at
https://jenkins.opencell.eu/job/[BRANCH]/" (stop). Exit `4` → show stderr, stop.

Keep the JSON as `[STATUS]`; `[N]` = `build`, `[PORTAL_SHA]` = `portal_sha`. Branch on `action`:

| `action` | Do |
|---|---|
| `no_builds` | Report "no build yet", stop |
| `running` | Report "#[N] is still running — [url]", stop |
| `green` | Report "✅ #[N] passed — [url]", stop |
| `not_failed` | Report "#[N] ended `[result]` — not a build break, not acted on", stop |
| `out_of_scope` | If `failed_stage` is set, run Step 3's command for that stage and print `classification` + the first 20 `error_lines`. Report "#[N] failed in `[failed_stage]` — outside the frontend stages, not fixed — [url]", stop |
| `fix` | Continue |

## Step 2 — Already handled?

A previous run may already have produced a fix for build `[N]`:

```bash
# (Bitbucket auth block from "Auth")
curl -s "${BB_AUTH[@]}" -G "$BB/pullrequests" \
  --data-urlencode 'q=source.branch.name="fix/INTRD-22890-build-[N]"' \
  -d state=OPEN -d state=MERGED -d state=DECLINED -d state=SUPERSEDED -w '\n%{http_code}'
```

| Result | Do |
|---|---|
| no PR | Continue to Step 3 |
| `MERGED` | The fix landed but the rebuild did not happen. Go to **Step 8** (no Jira writes) |
| `OPEN` | A previous run stopped at the merge. Report the PR link and stop |
| `DECLINED` / `SUPERSEDED` | A person rejected that fix. Report the PR link and stop |

## Step 3 — Diagnose from the Jenkins log

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/oc-fe-check-jenkins-build/scripts/jenkins_log.py" --branch "[BRANCH]" --build [N] --stage "[failed_stage]" --stage-id [failed_stage_id]
```

Keep the JSON as `[LOG]`. Show `classification` and the `error_lines`.

- `infra` → the failure is network / disk / agent / ssh. **No code change.** Go to **Step 8**
  and label the run "infra — rebuild only" in the report.
- `unknown` **and** `error_lines` empty → stop: print the last 40 lines of `excerpt` and
  "cause not identifiable from the log". Never guess-fix.
- otherwise → write a one-line `[CAUSE]` (e.g. `TS2339 in src/pages/Invoice.tsx: 'total'
  missing on Invoice`) and list the implicated files from the error lines. Continue.

## Step 4 — Prepare the opencell-portal workspace

```bash
git remote get-url origin
git status --porcelain
git rev-parse --abbrev-ref HEAD
```

- The remote must contain `opencell-portal`, else stop: "run this from an opencell-portal checkout".
- `git status --porcelain` must be empty, else stop — never stash or discard a developer's work.
- Keep the current branch as `[ORIG]`.

```bash
git fetch origin "[BRANCH]"
git rev-parse --verify --quiet "refs/heads/fix/INTRD-22890-build-[N]"
```

If that local branch already exists, stop: "a previous run left `fix/INTRD-22890-build-[N]`
locally — inspect or delete it". Otherwise:

```bash
git checkout -b "fix/INTRD-22890-build-[N]" "[PORTAL_SHA]"
git rev-parse "origin/[BRANCH]"
```

If `[PORTAL_SHA]` is null, use `origin/[BRANCH]` and say so. `[MOVED]` = whether
`origin/[BRANCH]` differs from `[PORTAL_SHA]`.

## Step 5 — Reproduce locally

Pick the package manager the way Jenkins does (it checks for `yarn.lock`):

```bash
if [ -f yarn.lock ]; then yarn install --frozen-lockfile && yarn run build; else npm ci && npm run build; fi
```

Run it with a 600000 ms timeout (or `run_in_background` if it needs longer).

- Fails with **the same** error as `[LOG]` (same TS code and file, or the same message) → Step 6.
- **Passes**, or fails with a **different** error → stop: "not reproducible locally" (show
  `node --version` — a Node mismatch with the Jenkins agent is the usual cause). Clean up:
  `git checkout [ORIG] && git branch -D fix/INTRD-22890-build-[N]`. Never commit a speculative change.

## Step 6 — Fix and verify locally

**6a — AI-stats run directory.** `[RUN_ID]` = `INTRD-22890-$(date -u +%Y%m%d-%H%M%S)`;
create `.claude/cache/ai-stats/[RUN_ID]/` (git-ignored) and write
`.claude/cache/ai-stats/[RUN_ID]/_planning.json`:

```json
{
  "run_id": "[RUN_ID]",
  "ticket": "INTRD-22890",
  "kind": "jenkins-build-diagnosis",
  "jenkins_build": "[url]",
  "cause": "[CAUSE]",
  "files": ["<implicated files>"]
}
```

**6b — Dispatch `oc-fe-engineer:oc-fe-engineer`** with:

> Fix the opencell-portal build failure below — **only** this failure.
> Jenkins build: [url]. Cause: [CAUSE]. Implicated files: [files].
> Error lines:
> ```
> [error_lines]
> ```
> Constraints: minimal change; no refactor; no unrelated edits; never add `@ts-ignore`,
> `@ts-expect-error` or `eslint-disable`; never edit `tsconfig*.json`, ESLint or Vite config;
> never delete or skip tests; do not change dependencies unless the error proves one is the cause.
> Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/fix.json` per your manifest
> instructions, then snapshot your first pass to `snapshots/fix.diff`.

After it returns, check `.claude/cache/ai-stats/[RUN_ID]/snapshots/fix.diff` exists; if not,
capture it now from the manifest's file list: `git diff HEAD -- <files> > .claude/cache/ai-stats/[RUN_ID]/snapshots/fix.diff`.

**6c — Guard against shortcuts.** Both commands must print nothing:

```bash
git diff HEAD -U0 | grep -E '^\+.*(@ts-ignore|@ts-expect-error|eslint-disable)'
git diff HEAD --name-only | grep -E '(^|/)(tsconfig[^/]*\.json|\.eslintrc[^/]*|eslint\.config\.[^/]+|vite\.config\.[^/]+)$'
```

**6d — Verify.**

```bash
if [ -f yarn.lock ]; then yarn run build; else npm run build; fi
```

- Passes and 6c is clean → Step 7.
- Otherwise → **one** more round: dispatch `oc-fe-engineer` again with the new error (and the
  6c violation, if any), manifest phase `fix-2`, then repeat 6c and 6d. That is the last round.
- Still failing → stop. Leave `fix/INTRD-22890-build-[N]` local and uncommitted, report the
  remaining error. No PR.

## Step 7 — Commit, open the PR, merge

**7a — Commit** only the files the fix changed (from `git status --porcelain`), never `git add -A`:

```bash
git add <changed files>
git commit -m "INTRD-22890: fix Jenkins build #[N] – [CAUSE]"
```

**7b — Rebase if the branch moved.** If `[MOVED]`:

```bash
git fetch origin "[BRANCH]"
git rebase "origin/[BRANCH]"
```

A conflict → `git rebase --abort`, stop (nothing pushed). If the rebase replayed the commit
onto a new base, re-run 6d's build; a failure → stop.

**7c — Push.** `git push -u origin "fix/INTRD-22890-build-[N]"`. A failure → stop.

**7d — Create the PR.** Write the body with the Write tool to
`${TMPDIR:-/tmp}/oc-fe-check-jenkins-build-pr-[N].json` (resolve the directory with
`echo "${TMPDIR:-/tmp}"` first):

```json
{
  "title": "INTRD-22890: fix Jenkins build #[N] – [CAUSE]",
  "source": {"branch": {"name": "fix/INTRD-22890-build-[N]"}},
  "destination": {"branch": {"name": "[BRANCH]"}},
  "close_source_branch": true,
  "description": "Jenkins build [url] failed in `[failed_stage]`.\n\n**Cause:** [CAUSE]\n\n```\n<first 30 error_lines>\n```\n\n**Local verification:** `<yarn|npm> run build` passes.\n\nOpened automatically by /oc-fe-check-jenkins-build."
}
```

```bash
# (Bitbucket auth block from "Auth")
curl -s "${BB_AUTH[@]}" -X POST -H 'Content-Type: application/json' \
  "$BB/pullrequests" -d @"${TMPDIR:-/tmp}/oc-fe-check-jenkins-build-pr-[N].json" -w '\n%{http_code}'
```

`201` → `[PR_ID]` = `.id`, `[PR_URL]` = `.links.html.href`. Anything else → stop and print
the response.

**7e — Merge.**

```bash
# (Bitbucket auth block from "Auth")
curl -s "${BB_AUTH[@]}" -X POST -H 'Content-Type: application/json' -D - \
  "$BB/pullrequests/[PR_ID]/merge" \
  -d '{"type":"pullrequest","merge_strategy":"squash","close_source_branch":true}'
```

- `200` with `"state": "MERGED"` → merged.
- `202` → the merge runs asynchronously: poll the `Location` header URL every 5 s (max 2 min)
  until its `task_status` is `SUCCESS`.
- Anything else (merge checks, required approvals, conflicts) → **stop**: the PR stays open,
  **no rebuild**, print Bitbucket's error and `[PR_URL]`.

**7f — Jira** (cloudId `opencellsoft.atlassian.net`):

1. `addCommentToJiraIssue` on `INTRD-22890`: "Jenkins build [url] failed in `[failed_stage]`:
   [CAUSE]. Fixed and merged in [PR_URL]; rebuild triggered."
2. Tag the AI field — **append, never overwrite**: `getJiraIssue` with
   `fields: ["customfield_10613"]` → `[CURRENT-TAGS]` (null → `[]`). If `ai_Dev_Front` is
   absent, `editJiraIssue` with `{ "customfield_10613": [<...CURRENT-TAGS>, "ai_Dev_Front"] }`.
   If the read fails, skip the write.

Jira failures are warnings — the fix is already merged, continue to Step 8.

## Step 8 — Re-run the build

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/oc-fe-check-jenkins-build/scripts/jenkins_rebuild.py" --branch "[BRANCH]" --from-build [N] --watch --timeout 2700
```

Run it with `run_in_background: true` and wait for the completion notification — do not poll.
If `[STATUS].timer_extras` is not empty, tell the user those values
(e.g. `ASSETS_URL`, `VITE_APP_BASE_URL`) exist only in the timer trigger and could not be
replayed.

| `front_status` | Do |
|---|---|
| `SUCCESS` | ✅ — Step 9 |
| `FAILED` / `ABORTED` / `UNSTABLE` | Re-run Step 1's status command, then Step 3's log command on the new build, and show the error lines. **Do not fix** — one fix attempt per run. Step 9 |
| `NOT_EXECUTED` | The run ended without building the front (an earlier stage failed, or `build_front` is false). Re-run Step 1's status command to show where. Step 9 |
| `TIMEOUT` | Still running — give the URL. Step 9 |
| `build` null | Still queued — show `queue_why`. Step 9 |

## Step 9 — Report

```
Jenkins [BRANCH] #[N] — failed in [failed_stage]
Cause:    [CAUSE]            (or "infra — rebuild only")
Fix:      [PR_URL] (merged)  (or "none")
Rebuild:  #[new build] [url] — Build Front: [front_status]
Not replayed: [timer_extras keys]   (only if any)
```

Remind the user they can run `/oc-fe-calculate-ai-use` on the merge commit to record the AI
contribution (it reads `.claude/cache/ai-stats/[RUN_ID]/`).

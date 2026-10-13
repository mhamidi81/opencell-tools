---
name: oc-clean-branches
description: Delete stale Bitbucket branches whose last commit is older than a given date, behind five guards - a branch is kept if it is protected or structural (master/main/develop/dev, release/*, version lines such as 19.0.x, any branch restriction), has an open pull request, still has commits not merged into its target (commits?include=<branch>&exclude=<target>), received a recent commit, or is not tied to a Bug / Sub-bug / Task / Sub-task ticket. Always produces a report (Markdown + HTML + CSV in ./docs/) and asks for an explicit confirmation, shown in red, before deleting anything. Bitbucket via direct REST (BITBUCKET_ACCESS_TOKEN), Jira via direct REST (JIRA_API_TOKEN) - no MCP.
argument-hint: "--before YYYY-MM-DD [--repo portal|core|both|SLUG] [--workspace SLUG] [--recent-days N] [--target BRANCH] [--out PATH] [--csv PATH] [--dry-run]"
---

## Purpose

Remove dead branches from Bitbucket without ever touching one that still matters. Every
branch whose **tip commit is strictly before `--before`** is a *candidate*; it is
deleted only if it passes **all five guards**. A candidate is **kept** when:

| Rule | Kept because | How it is checked |
|---|---|---|
| **R1** | protected or structural branch | repository main branch and target branch; `master`, `main`, `develop`, `dev`, `development`, `production`, `staging`, `integration`; `release/*`, `releases/*`, `release-*`, `support/*`; version lines (`19.0.x`, `14.1.0`, `v15`, `…/19.0.x`); **any** branch matching a Bitbucket **branch restriction** (`GET …/branch-restrictions`, glob or branching-model type) |
| **R2** | has an open pull request | `GET …/pullrequests?state=OPEN` — as **source or destination** |
| **R3** | not fully merged into its target | `GET …/commits?include=<tip-hash>&exclude=<target>` returns at least one commit. The target is the destination of the branch's latest **merged** PR if that branch still exists, otherwise the development branch (`--target`, else `develop` → `dev` → branching-model development branch → main branch) |
| **R4** | received a recent commit — even if its ticket is closed | tip commit newer than today − `--recent-days` (default 30) |
| **R5** | not a Bug / Sub-bug / Task / Sub-task branch | first Jira key in the branch name (`fix/INTRD-123-x` → `INTRD-123`); no key, ticket not found, unreadable, or any other type → kept |

Every guard **fails safe**: a check that cannot be evaluated (API error, unreadable
ticket) keeps the branch (`ERR`). If a repository's branch restrictions cannot be read
(typically `403` without repository-admin rights), the **whole repository is skipped**
— R1 cannot be guaranteed without them.

Nothing is deleted until the user has read the report and explicitly confirmed it.

## Access

Both tokens come from the environment, never from the command line.

- **`BITBUCKET_ACCESS_TOKEN`** — the scheme follows the token prefix: an `ATCTT…`
  repository/workspace Access Token is sent as `Authorization: Bearer` (no email); an
  `ATATT…` Atlassian API token is sent as Basic `BITBUCKET_EMAIL:token`. Deletion needs
  **write** permission on the repository; reading branch restrictions needs **admin**.
- **`JIRA_API_TOKEN`** (+ optional `JIRA_EMAIL`) — Atlassian API token from
  https://id.atlassian.com/manage/api-tokens, used for issue-type lookups only.

If either is missing, relay the script's setup message and stop. There is no Bitbucket
MCP; do not look for one.

## Arguments

Parse `$ARGUMENTS`. `--before` is **required** — if it is missing, ask for it and stop.

| Argument | Default | Meaning |
|---|---|---|
| `--before` | *(required)* | `YYYY-MM-DD`. Candidates have their tip commit strictly before 00:00 UTC that day |
| `--repo` | `both` | `portal` → `opencell-portal`; `core` → `opencell-core`; `both`; or explicit slug(s), comma-separated |
| `--workspace` | `opencellsoft` | Bitbucket workspace slug |
| `--recent-days` | `30` | R4 window — a commit within this many days keeps the branch |
| `--target` | `develop`, else `dev` | Override the development branch used by R3 when no merged PR names a target |
| `--out` | `./docs/clean-branches-<TODAY>.html` | HTML report |
| `--csv` | `./docs/clean-branches-<TODAY>.csv` | One row per candidate, `delete` or `keep` with the rule and reason |
| `--dry-run` | off | Produce the report and stop — no confirmation is asked, nothing is deleted |

`<TODAY>` is `date -u +%Y-%m-%d`. **Echo the resolved scope before any work**, e.g.
`Scanning opencell-portal + opencell-core for branches with no commit since 2026-06-01 (R4: nothing committed after 2026-09-02)`.

## Task 1 — Scan (read-only)

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-clean-branches"
RUN="${TMPDIR:-/tmp}/oc-clean-branches/[WORKSPACE]_[REPO]_[BEFORE]"
mkdir -p "$RUN"

python3 "$S/scripts/branch_scan.py" --before [BEFORE] --repo [REPO] \
  --workspace [WORKSPACE] --recent-days [RECENT_DAYS] [--target TARGET] \
  --out "$RUN/plan.json"
```

`--target` is passed only when the user supplied it. The script prints one line per
repository; a `SKIPPED` line on stderr means that repository is out of the plan — say so
and why. Exit code `1` means every repository was skipped: relay the reasons and stop.

**Never edit `plan.json`.** It is the exact list Task 3 deletes.

## Task 2 — Report

```bash
python3 "$S/scripts/branch_report.py" --plan "$RUN/plan.json" --out [OUT] --csv [CSV]
```

**Relay the Markdown it prints verbatim**, then give the HTML and CSV paths. The
Markdown lists at most 60 branches per repository; the HTML and CSV hold every one,
plus every kept branch with its rule and reason.

If the total to delete is **0**, say `No branch to delete` and stop. If `--dry-run` was
given, stop here.

## Task 3 — Confirmation (mandatory, in red)

Show this message **exactly as a fenced `diff` block** — every line starts with `-`,
which the terminal renders **in red**. Fill in the numbers from the report:

```diff
- ⚠️  SUPPRESSION DÉFINITIVE DE BRANCHES BITBUCKET
-
- [TOTAL] branche(s) vont être supprimées de Bitbucket :
-   • [REPO-1] : [N1] branche(s)
-   • [REPO-2] : [N2] branche(s)
-
- Critère : dernier commit avant le [BEFORE], et aucun garde-fou déclenché
- (branche protégée, PR ouverte, commits non mergés, commit récent, type de ticket).
-
- Cette action est IRRÉVERSIBLE depuis Bitbucket. Seule la restauration manuelle
- par hash (journal conservé) reste possible.
-
- Vérifiez le rapport : [OUT]
```

Then ask with `AskUserQuestion` — header `Confirm`, question
`Supprimer définitivement ces [TOTAL] branche(s) de Bitbucket ?`, options in this order:

1. `Non, annuler` — *Rien n'est supprimé.*
2. `Oui, supprimer [TOTAL] branche(s)` — *Suppression immédiate et définitive.*

**Only the explicit "Oui, supprimer …" answer proceeds.** Anything else — "Non", "Other",
a question, a request to change the scope — deletes nothing. A change of scope means
running Task 1 again and confirming a new report; never edit the plan, and never
carry a confirmation over to a different plan.

## Task 4 — Delete

```bash
python3 "$S/scripts/branch_delete.py" --plan "$RUN/plan.json" --confirm [TOTAL] \
  --log "./docs/clean-branches-<TODAY>-deleted.json"
```

`--confirm` must be the total the user just confirmed; if it does not match the plan the
script deletes nothing. Right before each `DELETE` it re-reads the branch tip and the
open PRs, and **skips** a branch whose tip moved or that gained an open PR since the
report. Relay the closing `deleted / skipped / failed` line and every `skipped` or
`failed` row.

Tell the user the log path: it records every deleted branch with its tip hash. Because R3
guaranteed that commit is in the target branch, a branch is restored with
`git push origin <hash>:refs/heads/<name>`.

## Failure behaviour

| Condition | What to do |
|---|---|
| `--before` missing | Ask for the date and stop |
| A token unset | Relay the setup message and stop |
| `HTTP 401` | The Bitbucket token is sent with the wrong scheme or is invalid. Say **both** rules: `ATCTT…` → Bearer, no email; `ATATT…` → Basic `BITBUCKET_EMAIL:token` |
| `HTTP 403` on `branch-restrictions` | The repository is skipped: R1 needs repository-admin read access. Never retry without the restrictions |
| `HTTP 403` on `DELETE` | The token lacks write permission. The row is `failed`; nothing else is affected |
| Total to delete is 0 | Report it and stop — no confirmation |
| User did not answer the explicit "Oui, supprimer …" | Delete nothing. Say so |

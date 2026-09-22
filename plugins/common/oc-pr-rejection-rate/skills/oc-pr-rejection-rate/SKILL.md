---
name: oc-pr-rejection-rate
description: Report the share of rejected pull requests on opencell-portal and opencell-core over a period, defaulting to the last seven days. A PR counts as rejected if it was declined, had changes requested at any point, or was pushed back from ready to draft - read from the Bitbucket activity feed, so a rejection that was later resolved is still counted. Prints a Markdown report and writes a date-stamped HTML + CSV to ./docs/. Read-only. Reads Bitbucket via direct REST with BITBUCKET_EMAIL + BITBUCKET_ACCESS_TOKEN - there is no Bitbucket MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--workspace SLUG] [--out PATH] [--csv PATH]"
---

## Purpose

Answer one question per repository over a period: **how often does our code get sent
back?** Three numbers — total PRs, rejected PRs, rejection rate — plus the breakdown that
lets someone check them.

A PR is **rejected** if any of these holds. It counts **once**, but appears in every
reason column that applies:

1. **Declined** — `state == DECLINED`.
2. **Changes requested** — at any point in its history. Deliberately historical: a
   reviewer who requests changes and later approves clears the flag, but the PR was
   still sent back.
3. **Re-drafted** — the PR moved ready → draft at least once. `/oc-review-pr` does this
   at a review score of 1-7 (it never declines, so this is the only rejection it produces).
   A PR **opened** as a draft is ordinary work in progress and is **not** a rejection.

This command is **read-only**. It writes nothing to Bitbucket and nothing to Jira. It
needs no git checkout and runs from any directory.

## Access

Requires **`BITBUCKET_EMAIL`** and **`BITBUCKET_ACCESS_TOKEN`**, read from the
environment and never passed on the command line. `BITBUCKET_ACCESS_TOKEN` holds an
**Atlassian API token** (`ATATT…`, from https://id.atlassian.com/manage/api-tokens),
which authenticates as `email:token` over **Basic** auth:

```
curl -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" …     # correct
curl -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" …  # 401 for ATATT… tokens
```

If either is unset, tell the user how to create the token and stop. **There is no
Bitbucket MCP** — the Rovo server exposes its Bitbucket tools only under API-token auth,
never over the OAuth flow the official plugin uses. Do not look for one.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-pr-rejection-rate` reports **the last 7
days** on **both** repositories.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 7 days before `--until` | Start of the window, inclusive, on `created_on` |
| `--until` | tomorrow | End of the window, **exclusive** — so today's PRs count |
| `--repo` | `both` | `portal` → `opencell-portal`; `core` → `opencell-core`; `both` |
| `--workspace` | `opencellsoft` | Bitbucket workspace slug |
| `--out` | `./docs/pr-rejection-rate-<TODAY>.html` | HTML report |
| `--csv` | `./docs/pr-rejection-rate-<TODAY>.csv` | One row per PR, one column per rule |

`<TODAY>` is `date -u +%Y-%m-%d`. **Echo the resolved window before doing any work**, e.g.
`Measuring PR rejections on opencell-portal + opencell-core, 2026-09-10 → 2026-09-17`.

## Task 1 — Fetch

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-pr-rejection-rate"
RUN="${TMPDIR:-/tmp}/oc-pr-rejection-rate/[WORKSPACE]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/pr_fetch.py" --since [SINCE] --until [UNTIL] \
  --repo [REPO] --workspace [WORKSPACE] --out "$RUN/prs.json"
```

**Never read `prs.json`.** It holds every PR's full activity feed and exists only for the
next script. Sum the per-repository counts on that line. If the **total** is 0, say
`No pull requests created in [SINCE] → [UNTIL]` and stop — do not write an empty
HTML or CSV. If one repository is 0 and another is not, **continue**: the report
renders `n/a` for the empty one, which is a different fact from `0.0%`.

## Task 2 — Classify

```bash
python3 "$S/scripts/pr_classify.py" --document "$RUN/prs.json" --out "$RUN/model.json"
```

It prints the resolved **draft detection mode**. Note it — Task 3's report states it, and
if it is not `activity` the re-drafted column is qualified rather than exact.

## Task 3 — Report

```bash
python3 "$S/scripts/pr_report.py" --model "$RUN/model.json" \
  --out [OUT] --csv [CSV]
```

It prints the Markdown report to stdout — **relay it**. Then tell the user where the HTML
and CSV landed.

Two things to say every time, because the numbers are misread without them:

- The reason columns **overlap** — a declined PR that also had changes requested appears
  in both, so they can sum past the rejected total.
- If the draft detection mode is **not** `activity`, say so plainly: the re-drafted
  column is approximate (`current-flag`) or was not measurable at all (`unavailable`).
  Never present it as an exact zero.

If any PR's activity feed failed to load, the report ends with a `## Warnings`
section listing them as `<repo> PR <id>: <what failed>`. Relay that section — those
PRs still count in the total, but rules 2 and 3 could not be evaluated for them, so
the rejected count is a floor rather than an exact figure. Note that warnings appear
in the Markdown and HTML only, not in the CSV.

## Failure behaviour

| Condition | What to do |
|---|---|
| `BITBUCKET_EMAIL` or `BITBUCKET_ACCESS_TOKEN` unset | Print the setup instructions from the script and stop. Never report a zero |
| `HTTP 401` | The token is being sent as Bearer, or it is not an `ATATT…` token. Relay the message; it explains the Basic-versus-Bearer rule |
| `HTTP 404` | The workspace or repository slug is wrong. The message names the path that was tried |
| `--since … must be before --until …` | The dates are back to front or equal. Relay it, ask for corrected dates, and stop. Nothing was fetched |
| Zero PRs in the window (total across repositories) | Report it and stop. Do not write an empty HTML or CSV. A single repository at 0 while another has PRs is not this case — continue and let it render `n/a` |
| A `## Warnings` section in the report | Relay it — those PRs' activity feeds failed to load, so rules 2 and 3 are unknown for them and the rejected count is a floor |

---
name: oc-bug-root-causes
description: Reclassify a period's Jira bugs whose Root cause is "Development issue" onto a granular developer-mistake taxonomy (incomplete-change-propagation, null-handling, dto-payload-mapping, update-overwrites-state, persistence-transaction, ...), judged from each bug's summary, description, last comments and the diff of the PR that fixed it. Regression is a separate flag, not a category. Ranks the categories overall and per area (Frontend/Backend) with share, regression rate, PR-vs-Jira evidence split and a one-line cause per example bug. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. Read-only. Jira via direct Cloud REST with a mandatory JIRA_API_TOKEN (no Atlassian MCP); Bitbucket via REST with BITBUCKET_ACCESS_TOKEN (optional - without it the run is Jira-only).
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--project KEY] [--no-pr] [--out PATH] [--csv PATH]"
---

## Purpose

Jira's **`Root cause`** field (`customfield_10111`) says *that* a bug was the developer's
fault — **"Development issue"**, about half of all INTRD bugs — but not *what kind* of
mistake it was. This command answers that: every such bug in the window gets exactly one
category from `references/dev-root-causes.md`, and the report ranks them, so the team can
see which mistakes recur and where review or tests are missing.

Three properties matter before changing anything:

- **The diff is the main evidence.** For each bug the fixing PR is found on Bitbucket and a
  trimmed diff (tests, lockfiles and i18n removed, 4 KB cap) is read with the Jira text.
  A bug without a PR is classified from Jira alone and the report says so per category.
- **Regression is a flag, not a category.** "Regression" says *when*, not *what*; every bug
  carries `regression: true|false` and the report shows the rate per category.
- **Classification is fanned out.** A month of evidence does not fit one context, so you
  never read the classification input yourself: one sub-agent per batch file does.

This command is **read-only**: no Jira writes, no Bitbucket writes. It needs no git
checkout and runs from any directory.

## Access

- **`JIRA_API_TOKEN`** (+ optional `JIRA_EMAIL`), mandatory — an Atlassian API token from
  *id.atlassian.com → Security → API tokens*. If unset, relay the script's setup message
  and stop. **Do not use the Atlassian MCP** — its search force-includes full
  descriptions and cannot page through a month of bugs.
- **`BITBUCKET_ACCESS_TOKEN`** (+ `BITBUCKET_EMAIL` for an `ATATT…` token), optional. An
  `ATCTT…` token is sent as Bearer, an `ATATT…` token as Basic `email:token`. If unset, the
  run continues Jira-only and the report shows `PR evidence 0`.

Tokens are read from the environment only — never pass them on the command line.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-bug-root-causes` analyses the **last 30
days** of **INTRD** bugs across **both** areas.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 30 days before `--until` | Start of the window, inclusive, on `created` |
| `--until` | tomorrow | End of the window, **exclusive** |
| `--repo` | `both` | `portal` (component Frontend), `core` (Backend) or `both` |
| `--project` | `INTRD` | Jira project(s), comma-separated |
| `--no-pr` | off | Skip Bitbucket; Jira-only evidence |
| `--out` | `./docs/bug-root-causes-<TODAY>.html` | HTML report |
| `--csv` | `./docs/bug-root-causes-<TODAY>.csv` | One row per bug |

`<TODAY>` is `date -u +%Y-%m-%d`. **Echo the resolved window before doing any work**, e.g.
`Analysing INTRD "Development issue" bugs, both areas, 2026-08-30 → 2026-09-30`.

## Task 1 — Fetch

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-bug-root-causes"
RUN="${TMPDIR:-/tmp}/oc-bug-root-causes/[PROJECT]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/rc_fetch.py" --since [SINCE] --until [UNTIL] \
  --project [PROJECT] --repo [REPO] --out-bugs "$RUN/bugs.json"
```

Exit code `3` means no "Development issue" bug in the window: say so and stop. Exit `2`
is a missing token or an inverted window: relay the message and stop. **Never read
`bugs.json`.**

## Task 2 — PR evidence

```bash
python3 "$S/scripts/rc_pr.py" --bugs "$RUN/bugs.json" --run "$RUN" \
  --out-classify "$RUN/classify_input.jsonl" [--no-pr]
```

It prints how many bugs got PR evidence, how many lookups failed, and how many batch
files it wrote to `$RUN/batches/`. Relay every `WARNING:` line. A Bitbucket 401 is not
fatal — the run continues Jira-only — but tell the user, since the message names both auth
schemes.

**Exit code `4` means some PR lookups failed** (a network error, or the Bitbucket rate
limit was reached). Do not classify yet: tell the user, and re-run the same command —
found PRs are cached per bug in `$RUN/pr/`, so it only asks for the bugs that are left.
For a rate limit, wait before re-running (the quota is hourly). Proceed on exit `4` only if
the user says so, and then say in the summary that PR evidence is understated.

**Never read `classify_input.jsonl` or the batch files yourself.**

## Task 3 — Classify (fanned out to sub-agents)

Clear the previous run's results first — a stale part file from an earlier run of the
same window makes the report fail:

```bash
rm -rf "$RUN/assignments" && mkdir -p "$RUN/assignments"
```

Then for each `$RUN/batches/classify.NNN.md` dispatch one
`general-purpose` sub-agent with the Agent tool, **at most 4 at a time**, each with this
prompt (fill in the paths):

> You classify "Development issue" bugs by the developer mistake their fix corrects.
> 1. Read the taxonomy `$S/references/dev-root-causes.md`. Its `## <name>` headings are the
>    only categories you may use, apart from the rule in step 4.
> 2. Read `$RUN/batches/classify.NNN.md` **to the end** — if it is too large for one Read,
>    page through it with offset/limit. It starts with the list of keys, then one
>    `## <KEY>` section per bug: evidence type and PR, summary, files changed, the trimmed
>    diff, the description and the last comments.
> 3. For **every** line, decide:
>    - `category` — exactly one. Ask "what did the developer get wrong that the fix
>      corrects?", not "where did the user see it?". When a diff is present, trust it over
>      the prose. A symptom ("error toast", "KO") is never a category.
>    - `confidence` — `high` when the diff or a comment shows the mistake, else `low`.
>    - `regression` — `true` when the bug says so (`[REG]`, "Regression", "since INTRD-…",
>      "no longer") or the diff repairs a recent change; otherwise `false`.
>    - `cause` — one line, at most 120 characters, naming the concrete mistake, e.g.
>      "TaxInvoiceAgregate copy constructor omits accountingCode".
>    Use `insufficient-evidence` only when there is no plausible guess at all; a weak guess
>    is that guess with `low` confidence.
> 4. If you believe a mistake genuinely fits no category, you may use a new lower-kebab-case
>    name, and list it with its bugs at the end of your reply. It is kept only if at least 5
>    bugs across the whole run carry it.
> 5. Write `$RUN/assignments/NNN.json`: one JSON object
>    `{"<KEY>": {"category": "...", "confidence": "high|low", "regression": true|false,
>    "cause": "..."}}` covering every key in your batch. Reply only with the number of bugs
>    written and any new category you used.

Wait for every sub-agent. Collect the new categories they report.

## Task 4 — Report

```bash
python3 "$S/scripts/rc_report.py" --bugs "$RUN/bugs.json" \
  --classify "$RUN/classify_input.jsonl" --assignments "$RUN"/assignments/*.json \
  --taxonomy "$S/references/dev-root-causes.md" \
  --out [OUT] --csv [CSV] --model "$RUN/model.json"
```

It prints the Markdown report — relay it, then say where the HTML and CSV landed.

On exit `2` it lists every problem. Fix them and re-run Task 4:

- `no category assigned for: …` — find which batch files hold those keys and re-dispatch
  them (their `assignments/NNN.json` is rewritten).
- `unknown category '…' on N bug(s)` — a sub-agent coined a category too small to keep.
  Re-dispatch the batches holding those bugs, adding to the prompt that this name is not
  allowed.
- `classified differently in two parts` or `assignments for bugs not in this run` — a
  stale part file survived: clear `$RUN/assignments` and re-dispatch every batch.
- `confidence must be…`, `regression must be…`, `category must be lower-kebab-case`,
  `cause must be…` — a malformed part: re-dispatch the batch holding that key.

When presenting, point out the **evidence split**: a category ranked mostly on Jira-only
evidence is a weaker finding than one ranked on diffs. Name any new category the report
kept so `dev-root-causes.md` can be updated.

## Failure behaviour

| Condition | What to do |
|---|---|
| `JIRA_API_TOKEN` unset | Relay the setup message and stop. Never fall back to the MCP |
| `must be before` | The dates are inverted or equal. Ask for corrected dates and stop |
| Exit 3 from `rc_fetch.py` | No "Development issue" bug in the window. Report it and stop |
| `BITBUCKET_ACCESS_TOKEN` unset | The run continues Jira-only; say so in the summary |
| Bitbucket 401 warning | Continue; tell the user the credential was rejected and relay the message |
| `WARNING: PR lookup failed for …` | That bug is Jira-only; relay it |
| Exit 4 from `rc_pr.py` | Lookups failed or the rate limit was hit: re-run `rc_pr.py` (later, for a rate limit) before classifying |
| Exit 2 from `rc_report.py` | Fix as described in Task 4 and re-run it |

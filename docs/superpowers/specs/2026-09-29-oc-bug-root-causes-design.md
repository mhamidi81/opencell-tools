# `/oc-bug-root-causes` — design

**Date:** 2026-09-29 · **Status:** approved in chat, pending spec review · **Plugin:** `plugins/common/oc-bug-root-causes`

## Goal

Jira's `Root cause` field (`customfield_10111`, single select) says *that* a bug was the
developer's fault — **"Development issue"** — but not *what kind* of mistake it was.
On INTRD bugs created since 2026-06-01, 280 of 532 (53%) carry that value, and the
multi-select `Cause` field (`customfield_10167`) is empty on every one of them.

`/oc-bug-root-causes` takes a period's "Development issue" bugs and reclassifies each onto
a granular **developer-mistake taxonomy**, using the bug's Jira text **and the diff of the
PR that fixed it**, so the team can see which kinds of mistake recur and where review or
tests are missing.

**Success:** a report that ranks mistake categories per area, shows the regression rate
per category, states how much of each number rests on PR evidence, and gives a one-line,
checkable cause for every example bug.

**Non-goals.** No Jira or Bitbucket writes of any kind (no Enablers, no labels, no field
updates). No MACO/`MACRD`. No root-cause values other than "Development issue". No
changes to `oc-bug-clusters`.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Taxonomy source | Seeded by us from the real 280 summaries, editable | `Cause` is empty; the team has no list |
| Evidence | Summary + description excerpt + last 3 comments **+ linked PR diff** | Summaries alone are often symptoms ("Fix issues on…") |
| Output | Report only | Categories are still settling; safe to re-run |
| Code reuse | Standalone plugin, own copy of `jira_client.py` | `${CLAUDE_PLUGIN_ROOT}` cannot cross plugins in an install |
| Taxonomy scope | One list shared by both areas | The point is comparing Frontend vs Backend on the same axis |
| Regression | Orthogonal `regression: yes/no` flag, not a category | Regression is *when*, not *what*; a regression can be any category |

## Layout

```
plugins/common/oc-bug-root-causes/
  .claude-plugin/plugin.json
  skills/oc-bug-root-causes/
    SKILL.md
    references/dev-root-causes.md
    scripts/jira_client.py        # byte-identical copy (oc-bug-clusters)
    scripts/bug_fetch.py          # byte-identical copy (oc-bug-clusters): area, ADF, window
    scripts/bitbucket_client.py   # byte-identical copy (oc-pr-rejection-rate): token-prefix auth
    scripts/rc_fetch.py           # Jira fetch + area + comments
    scripts/rc_pr.py              # PR lookup + trimmed diff, cached
    scripts/rc_report.py          # validate assignments, aggregate, render
  tests/                          # pytest, fixtures, no network
```

Plus: an entry in `.claude-plugin/marketplace.json` and a `CLAUDE.md` section.

## Pipeline

Run directory: `$TMPDIR/oc-bug-root-causes/<PROJECT>_<REPO>_<SINCE>_<UNTIL>/`.

### 1. Fetch — `rc_fetch.py` (deterministic)

- JQL: `project in (<P>) AND issuetype in (Bug, "Sub-bug") AND "Root cause" = "Development issue" AND created >= "<since>" AND created < "<until>" ORDER BY created DESC`.
- Enhanced search `/rest/api/3/search/jql`, paginated by `nextPageToken`, fields limited to
  `summary, description, issuetype, status, resolution, components, labels, created,
  assignee, reporter, customfield_10111`.
- Area resolution is **copied from `oc-bug-clusters`**: component `Frontend`→`portal`,
  `Backend`→`core`, else a *leading* `[front]`/`[back]` summary tag, else `null`. Bugs with
  `null` area are kept and reported, and still classified (area-less bugs still have a cause).
- Comments: `GET /rest/api/3/issue/<key>/comment?orderBy=-created&maxResults=3`, ADF
  flattened, each trimmed to 400 chars. One call per bug.
- Description excerpt: 600 chars (larger than oc-bug-clusters' 300: cause, not subject, is judged).
- Outputs `bugs.json` only (full records; the model never reads it). The model's input,
  `classify_input.jsonl`, is written by stage 2 once PR evidence is attached.
- The Invalid/Declined/Duplicate filter is **not** applied: a bug marked "Development issue"
  has been triaged as a real defect by definition.

### 2. PR evidence — `rc_pr.py` (deterministic, Bitbucket REST)

- Repository from area: `portal`→`opencell-portal`, `core`→`opencell-core`, `null`→ try both.
  Workspace `opencellsoft`.
- Lookup: **one** search per repository, `q=(title ~ "<KEY>" OR source.branch.name ~ "<KEY>")`
  with `state` repeated for MERGED, OPEN, DECLINED, SUPERSEDED. Results are re-filtered on the
  **whole** key, because `~` is a substring match (`INTRD-4516` matches `INTRD-45162`).
- Selection: merged PR targeting `dev` → most recent merged → most recent any state.
- Evidence: `…/diff` only. It answers 302 to a signed URL; the redirect is followed by hand
  and the `Authorization` header is dropped when the host changes. The per-file list
  (`path +added -removed`, capped at 40 files) is **computed from the full diff** instead of a
  separate `…/diffstat` call: with one search per repository that keeps a 280-bug window
  near 600 requests, inside Bitbucket's hourly rate limit. 429/503 are retried with backoff.
- Diff trimming: drop files matching tests (`*.test.*`, `*.spec.*`, `src/test/`), lockfiles,
  i18n JSON (`**/i18n/**`, `**/locales/**`), generated/minified files; keep hunks in file
  order until a **4 KB** cap; the per-file list always covers every file, tests included.
- Auth: `ATCTT…` → `Authorization: Bearer`; otherwise Basic `BITBUCKET_EMAIL:token`. Keyed
  off the token prefix, never off whether an email is set.
- Per-bug cache `pr/<KEY>.json` in the run directory, for bugs **with** PR evidence only; a
  Jira-only fallback is not cached, so a later run with a working token looks again.
- Output: `classify_input.jsonl`, one line per bug: `key, area, summary, excerpt, comments[],
  evidence ("pr"|"jira"), pr_url, pr_title, files[], diff`; plus the same bugs rendered as
  readable Markdown in `batches/classify.NNN.md`, 30 bugs each (stale batch files removed
  first): evidence before prose, the diff un-escaped, no line over 1000 characters — a JSON
  row is one long line that the Read tool truncates before the diff.
- Exit `4` when any lookup failed (network error, or the rate limit exhausted — which also
  stops further lookups); the orchestrator re-runs the stage before classifying.
- Selection first keeps the PRs *about* the key (branch carries it, or the title leads
  with it); a later PR that merely mentions it ("fix regression from INTRD-X") loses.
- `--no-pr` skips this stage and writes the same file with `evidence: "jira"`.

### 3. Classify — the only LLM step (SKILL.md)

- **Fanned out to sub-agents, one per batch file.** A month's evidence (~1.5k tokens per bug
  with its diff) does not fit one context, so the orchestrating session never reads
  `classify_input.jsonl`: it dispatches one sub-agent per `batches/classify.NNN.md` (up to 4
  in parallel), each reading `references/dev-root-causes.md` and writing
  `assignments/NNN.json`: `{"<KEY>": {"category", "confidence": "high"|"low",
  "regression": true|false, "cause": "<≤ 120 chars>"}}` covering every key of its batch.
- A new category needs ≥ 5 bugs **across the run**, which no single sub-agent can see: a
  sub-agent may *propose* one, and the report stage decides (below 5 → rejected, and the
  orchestrator re-dispatches those bugs with the proposal removed).
- Rules: exactly one category; ask "what mistake does the fix correct?"; prefer the diff over
  the prose when they disagree; `regression` is true when the bug says it (`[REG]`,
  "Regression …", "since INTRD-…") or the diff reverts/repairs a recent change;
  `insufficient-evidence` is allowed and honest, never a dumping ground for `low` cases that
  do have a best guess; a new category only if ≥ 5 bugs fit none of the seeded ones, and it
  is reported to the user.

### 4. Report — `rc_report.py` (no network)

- Merges the `assignments/*.json` parts (a key assigned differently in two parts → exit 2).
- Validates: every key present (else exit 2 listing keys), no key outside the run, every
  category seeded or carried by ≥ 5 bugs (else exit 2), confidence/regression/cause well-typed.
  The cause line is truncated to 120 characters rather than rejected.
- Model: per category → count, % of total, per-area counts (portal/core/none), regression
  count and rate, evidence split (pr/jira), low-confidence count, up to 5 examples (newest
  first, `pr` evidence preferred).
- Markdown to stdout; `./docs/bug-root-causes-<TODAY>.html` and `.csv` (overridable with
  `--out` / `--csv`).
- Report sections: header (window, project, totals, evidence split, insufficient count) →
  ranking table → one section per category (definition, examples with cause line and PR
  link) → `insufficient-evidence` bugs in full → bugs with no area.
- CSV columns: `key, area, category, confidence, regression, evidence, pr_url, cause, status,
  created, assignee, summary, url`.
- HTML reuses oc-bug-clusters' CSS (light/dark), with Frontend / Backend / All tabs.

## Arguments

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 30 days before `--until` | Inclusive, on `created` |
| `--until` | tomorrow | Exclusive |
| `--repo` | `both` | `portal`, `core` or `both` |
| `--project` | `INTRD` | Jira project(s), comma-separated |
| `--no-pr` | off | Jira-only evidence |
| `--out` / `--csv` | `./docs/bug-root-causes-<TODAY>.{html,csv}` | Report paths |

## Taxonomy (`references/dev-root-causes.md`)

`incomplete-change-propagation`, `null-handling`, `edge-case-boundary`,
`dto-payload-mapping`, `update-overwrites-state`, `persistence-transaction`,
`query-construction`, `api-contract`, `frontend-state-effects`, `missing-wiring`,
`business-rule-logic`, `numeric-date-precision`, `concurrency-lifecycle`, `ui-cosmetic`,
`insufficient-evidence` — each with a definition and real INTRD examples, as agreed in chat.
Adding a category is safe; renaming one breaks period-over-period comparison.

## Failure behaviour

| Condition | Behaviour |
|---|---|
| `JIRA_API_TOKEN` unset | Print setup, stop; never fall back to the MCP |
| `BITBUCKET_ACCESS_TOKEN` unset | Warn once, continue as `--no-pr` |
| Bitbucket 401 | Stop the PR stage, message names **both** schemes; continue Jira-only |
| Other Bitbucket error on one bug | That bug becomes `evidence: jira`; warn, continue |
| Inverted window | Relay `must be before`, stop |
| Zero "Development issue" bugs | Report and stop |
| Missing keys / unknown category in assignments | Exit 2 naming them; re-dispatch those batches |

## Testing

`python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`, no network (fake openers):
JQL includes the Root-cause clause and exclusive `until`; area resolution; comment
flattening/trimming; PR selection order; diff trimming (filters + 4 KB cap, redirect
followed without credentials on host change, 429 retried); whole-key PR matching; batch
files; auth scheme by token prefix; cache hit avoids calls; assignment-part merging; assignment validation;
aggregation maths (percentages, regression rate, evidence split); Markdown/CSV/HTML
rendering; the three copied scripts byte-identical to their originals; packaging (marketplace
entry, plugin.json name, SKILL.md frontmatter).

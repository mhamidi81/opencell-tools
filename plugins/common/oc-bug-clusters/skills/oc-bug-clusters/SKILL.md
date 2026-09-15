---
name: oc-bug-clusters
description: Analyse the bugs created over a period, classify each onto a seeded subject taxonomy, and group any subject carrying at least 5 bugs into a cluster. Area (portal/core) comes from the Jira component with a [front]/[back] summary-tag fallback and is fully deterministic; the subject is the only LLM judgement. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. With --create-enabler it creates one Enabler per area (Frontend assigned to Mohamed Hamidi, Backend to Adil El Jaouhari) holding one Sub-task per cluster with the cluster's bugs linked - confirmed before writing, idempotent via a marker label, and resumable. Fetches Jira via direct Cloud REST with a mandatory JIRA_API_TOKEN - no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--create-enabler] [--min-cluster N] [--project KEY] [--assignee-portal ID] [--assignee-core ID] [--out PATH] [--csv PATH] [--force]"
---

## Purpose

Turn a period of Jira bugs into a small number of **subject clusters**, and — on
request — into scheduled work: one **Enabler per area**, each holding one **Sub-task
per cluster**, with the cluster's bugs linked to it.

A cluster is **at least `--min-cluster` (default 5) bugs on the same subject**.

Two properties are worth knowing before changing anything here:

- **Area is deterministic, subject is not.** The portal/core split is computed in
  Python from the Jira component (falling back to a leading `[front]`/`[back]` tag), so
  it never moves between two runs. Only the subject is an LLM judgement.
- **The marker label is what makes re-runs safe.** Every Enabler carries
  `bug-clusters-<area>-<since>-<until>`, and that label is searched before any write.

This command is read-only unless `--create-enabler` is passed. It needs no git
checkout and no Bitbucket token, and runs from any directory.

## Access

Requires **`JIRA_API_TOKEN`** (+ optional `JIRA_EMAIL`) — an Atlassian API token from
*id.atlassian.com → Security → API tokens*, read from the environment and **never
passed on the command line**. If it is unset, tell the user how to create one and stop.

**Do not use the Atlassian MCP for the fetch.** `searchJiraIssuesUsingJql` force-includes
each issue's full description and caps at ~5 issues per call with no cursor — a 50-issue
probe already overflows the tool-result limit. All Jira access here is direct Cloud REST.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-bug-clusters` analyses the **last 30
days** of **portal** bugs in **INTRD** and only reports.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 30 days before `--until` | Start of the window, inclusive, on `created` |
| `--until` | tomorrow | End of the window, **exclusive** — so today's bugs count, and `--since 2026-08-01 --until 2026-09-01` is exactly August |
| `--repo` | `portal` | `portal` → component `Frontend`; `core` → `Backend`; `both` → each area clustered separately, one Enabler each |
| `--create-enabler` | off | Create the Jira Enabler(s). Off means report only |
| `--min-cluster` | `5` | Bugs on one subject before it counts as a cluster |
| `--project` | `INTRD` | Portal *and* core both live in INTRD. `MACRD` is MACO — a different codebase, out of scope here |
| `--assignee-portal` | `5ef5c13914f60e0ac1c9b049` | Frontend Enabler assignee (Mohamed Hamidi). Accepts an accountId or an email |
| `--assignee-core` | `63369fa788ed2ebef97cddfb` | Backend Enabler assignee (Adil El Jaouhari). Same forms |
| `--out` | `./docs/bug-clusters-<TODAY>.html` | HTML report |
| `--csv` | `./docs/bug-clusters-<TODAY>.csv` | One row per bug |
| `--force` | off | Create a second Enabler for a window that already has one |

`<TODAY>` is `date -u +%Y-%m-%d`. Compute missing dates with
`date -u -d '30 days ago' +%Y-%m-%d`.

**Echo the resolved window before doing any work**, e.g.
`Analysing INTRD bugs, portal, 2026-08-16 → 2026-09-16`.

## Task 1 — Fetch and area-tag

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-bug-clusters"
RUN="${TMPDIR:-/tmp}/oc-bug-clusters/[PROJECT]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/bug_fetch.py" --since [SINCE] --until [UNTIL] \
  --project [PROJECT] --repo [REPO] \
  --out-bugs "$RUN/bugs.json" --out-classify "$RUN/classify_input.jsonl"
```

The run directory is keyed by the window so a later `--create-enabler` run resumes
rather than duplicating.

**Never read `bugs.json`.** It holds every bug's full record and exists only for the
next script. If it reports 0 bugs, say
`No bugs created in [SINCE] → [UNTIL] for [PROJECT]` and stop.

## Task 2 — Classify each bug onto a subject

**This is the only step you perform yourself.**

1. Read `$S/references/subjects.md`. Its `## <name>` headings are the vocabulary.
2. Read `$RUN/classify_input.jsonl` — one bug per line: `key`, `summary`, `excerpt`,
   `component`, `labels`. Process it in batches of **at most 60 lines**.
3. Write `$RUN/assignments.json`: a flat object `{"INTRD-47162": "rating", …}` covering
   **every key in the file**. A missing key stops the next step with an error.

Rules:

- **Exactly one subject per bug.** No multi-label, no ties, no empty values.
- **Prefer a subject that already exists** in `subjects.md`.
- You may coin a **new** subject only when **at least `--min-cluster` bugs in the same
  area** fit none of the seeded ones — the same threshold that makes a cluster, so a
  coined subject can never be too small to be one. Report any new subject to the user
  at the end so `subjects.md` can be updated.
- Names are **lower-kebab-case**.
- Classify by what the bug is **about** — the product area it lives in — **never by its
  symptom**. `quoting`, not `blank-screen`. A crash in the quote screen is `quoting`;
  a crash caused by a slow query that times out everywhere is `performance`.
- **Do not trust the reporter's tag.** `[NEW UI]` and `[Quote New UI]` are the same
  subject; `[15.X]` is a version, not a subject.

## Task 3 — Cluster and report

```bash
python3 "$S/scripts/bug_cluster.py" --bugs "$RUN/bugs.json" \
  --assignments "$RUN/assignments.json" --subjects "$S/references/subjects.md" \
  --min-cluster [MIN] --out [OUT] --csv [CSV] --model "$RUN/model.json"
```

It prints the Markdown report to stdout — relay it. Then tell the user where the HTML
and CSV landed, and name any **new subject** you coined.

Stop here unless `--create-enabler` was passed.

## Task 4 — Create the Enablers (only with `--create-enabler`)

**Step 1 — show the plan. Write nothing yet.**

```bash
python3 "$S/scripts/bug_enabler.py" --model "$RUN/model.json" --project [PROJECT] \
  --report-path [OUT] --assignee-portal [AP] --assignee-core [AC] \
  --state "$RUN/created.json" --plan
```

If it prints `No cluster reached the threshold`, say so and stop — **never create an
empty Enabler**.

**Step 2 — ask.** Show the printed plan and ask the user to confirm, plainly: how many
Enablers, how many Sub-tasks, how many bug links, and into which project. **Wait for an
explicit yes.** Do not proceed on silence or on an ambiguous reply.

**Step 3 — apply, only after that yes.**

```bash
python3 "$S/scripts/bug_enabler.py" --model "$RUN/model.json" --project [PROJECT] \
  --report-path [OUT] --assignee-portal [AP] --assignee-core [AC] \
  --state "$RUN/created.json" --apply
```

Report every created key. Relay every `WARNING:` line verbatim — a failed bug link is
reported, not fatal, and the user needs to know which ones to add by hand.

If it says an Enabler already carries the marker label, tell the user the existing key
and that `--force` would create a second one. **Do not pass `--force` on your own
initiative** — only when the user asks for it.

## Failure behaviour

| Condition | What to do |
|---|---|
| `JIRA_API_TOKEN` unset | Print the setup instructions from the script and stop. Never fall back to the MCP |
| Zero bugs in the window | Report it and stop |
| Zero clusters | Show the report's near-clusters, create nothing |
| `no subject assigned for: …` | You missed keys in Task 2. Classify exactly those and re-run Task 3 |
| `requires [...], which /oc-bug-clusters does not set` | A Jira screen changed. Report it; nothing was written |
| An `--assignee-*` email matches no user | Stop and ask for an accountId; nothing was written |
| `WARNING: link … failed` | Relay it; the Enabler and Sub-tasks are fine |

# PR Rejection Rate Plugin (`oc-pr-rejection-rate`) — Design

- **Date:** 2026-09-16
- **Jira:** INTRD-47180
- **Repos touched:** `ccode-marketplace` only (new plugin + marketplace wiring + CLAUDE.md)
- **Status:** approved design, pending implementation plan

## 1. Problem

Nobody can currently answer "how often does our code get sent back?" without opening
Bitbucket and reading pull requests one at a time. The signal exists — a PR is declined, a
reviewer requests changes, `/oc-review-pr` pushes a 6-7 scored PR back to Draft — but it is
scattered across per-PR state and per-PR activity feeds, so it is never looked at.

This plugin turns a period of pull requests on **`opencell-portal`** and **`opencell-core`**
into three numbers per repository: **total PRs, rejected PRs, and the rejection rate**.

Three facts about the data constrain the design:

1. **Bitbucket has no usable MCP path here.** Per `CLAUDE.md`, the Atlassian Rovo server
   exposes its Bitbucket tools only under API-token auth, never over the OAuth flow the
   official plugin uses. All Bitbucket access is direct REST, authenticated as
   `email:token` over **Basic** auth with an `ATATT…` Atlassian API token.
2. **Rejection is partly historical, not a current field.** A reviewer who requests changes
   and later approves clears the participant flag; a PR put back to Draft and then fixed
   reads as an ordinary ready PR. Reading only current state silently undercounts every
   rejection that was already resolved — which is most of them. The per-PR **activity feed**
   is the only source that preserves the event.
3. **Draft is ambiguous without its history.** A PR *opened* as a draft is ordinary
   work-in-progress; a PR *pushed back* to draft is a rejection. The two are
   indistinguishable from the current `draft` flag alone.

## 2. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Every rule is computed deterministically in Python**; the LLM makes no judgement | Unlike `oc-bug-clusters`, where the subject is genuinely a semantic call, nothing here needs reading. A percentage people act on must not move between two runs of the same window |
| D2 | **Ship real `.py` files + a pytest suite**, like `oc-bug-clusters`, not Python embedded in `SKILL.md` like `oc-ai-report` / `oc-time-report` | The three rules need tests against recorded fixtures. Embedded Python is retranscribed by the model on every run, and a silent transcription slip in a metric is expensive |
| D3 | The window anchors on **`created_on`** | Gives a stable denominator — "of the PRs opened this week, X% were rejected". `updated_on` would let one PR count in several weeks and would move the total as old PRs collect comments |
| D4 | **Rejection is read from the activity feed**, not from current participant/draft state | See §1.2. Costs one extra call per PR; at ~50-200 PRs/week/repo that is well inside Bitbucket's 1000 req/hour authenticated budget |
| D5 | **R3 counts ready → draft, and excludes PRs opened as a draft** | A developer opening a WIP draft has not been rejected. The initial draft state must be read from the feed, never assumed |
| D6 | A PR counts **once** in the rejected total; reasons are reported as **overlapping** columns | A declined PR that also had changes requested is one rejection. The reason breakdown is diagnostic, so its columns are allowed to sum past the rejected total, and the report says so |
| D7 | **R3 declares its detection mode** in every report | The activity feed's draft representation is unverified (§4). A zero must never be readable as "nobody was re-drafted" when it actually means "we could not tell" |
| D8 | `pr_classify.py` is **pure** — JSON in, JSON out, no network | Puts the three rules behind a boundary that tests can reach with no token |
| D9 | **Read-only.** No Bitbucket writes, no Jira writes | Unlike `oc-bug-clusters --create-enabler`, this command reports and stops. Nothing here is outward-facing |
| D10 | Repo slugs `opencell-portal` / `opencell-core` and workspace `opencellsoft` are **defaults, not constants** | Verified from the local checkouts' remotes, but a report tool should not need a code change to look at a third repo |

**Non-goals.** No per-developer or per-reviewer breakdown — this is a team metric, and
turning it into an individual one is a separate decision with separate consequences. No
time-to-merge, review-latency or approval-count statistics. No MACO / overlay repositories.
No Jira correlation — the plugin never resolves a PR to its ticket. No writes of any kind.

## 3. Plugin shape

```
plugins/common/oc-pr-rejection-rate/
  .claude-plugin/plugin.json                              # name, description, version 1.0.0
  skills/oc-pr-rejection-rate/SKILL.md                    # the whole command
  skills/oc-pr-rejection-rate/scripts/
    bitbucket_client.py                                   # Basic auth, paging, 302-follow, 429 backoff
    pr_fetch.py                                           # window -> prs.json (list + per-PR activity)
    pr_classify.py                                        # pure: the three rules -> model.json
    pr_report.py                                          # Markdown stdout + HTML + CSV
  tests/
    conftest.py
    test_bitbucket_client.py
    test_pr_classify.py
    test_pr_report.py
    test_pr_rejection_rate_packaging.py
```

Plus a `marketplace.json` entry and a `CLAUDE.md` section.

The split is a testing boundary, not decoration: `pr_fetch.py` owns all I/O,
`pr_classify.py` owns all judgement and touches no network, `pr_report.py` owns all
formatting. Only `pr_classify.py` needs to be right for the number to be right, and it can
be exercised entirely offline.

## 4. How Bitbucket represents draft transitions — RESOLVED

This section was written as an open risk: no token was available, so the activity feed's
draft representation could not be confirmed. It has since been **probed against live
Bitbucket** (2026-09-16, `opencellsoft/opencell-portal`), and the answer is recorded in
`tests/fixtures/activity_drafted.json` and its README.

**What the probe found.** Bitbucket uses *both* forms in the same feed —
`update.changes.draft` as `{"old": <bool>, "new": <bool>}` on the entry that flips the
flag, and a plain `update.draft` snapshot boolean on every other update entry — always
real JSON booleans, never strings. Across a 340-entry sample every `update` entry carried
a `date`. Two shape details that were not anticipated: each entry is
`{"<kind>": {...}, "pull_request": {...}}` where the `pull_request` sibling is metadata,
appears *first*, and carries its own `draft` field; and `comment` entries date themselves
with `created_on` rather than `date`.

The fallback chain below is retained — it is what makes a future API change degrade
honestly rather than silently, and mode `activity` is now the one observed in practice:

| Mode | Condition | Meaning |
|---|---|---|
| `activity` | The feed exposes draft state on update entries | Ready → draft transitions counted exactly. The intended mode |
| `current-flag` | No draft data in the feed, but the PR object carries `draft` | Approximate: a currently-draft PR with post-creation activity is counted. Over- and under-counts are both possible |
| `unavailable` | No draft data anywhere | R3 contributes nothing; the report says the criterion could not be measured |

The resolved mode appears in the Markdown, the HTML and the CSV metadata of **every** run.
A report that cannot measure R3 must say so on its face.

## 5. Rejection rules

A PR whose `created_on` falls in the window is **rejected** if any rule holds.

- **R1 — declined.** `state == "DECLINED"`. From the list response; no activity needed.
- **R2 — changes requested.** At least one `changes_requested` entry anywhere in the
  activity feed. Deliberately historical: a later approval does not undo the fact that the
  PR was sent back.
- **R3 — re-drafted.** The PR moved ready → draft at least once, per §4. A PR opened as a
  draft and later made ready is **not** rejected.

`SUPERSEDED` PRs count toward the total and are not rejections. `MERGED` and `OPEN` PRs are
rejected only if R2 or R3 fired.

## 6. Arguments

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 7 days before `--until` | Start of the window, **inclusive**, on `created_on` |
| `--until` | tomorrow (UTC) | End of the window, **exclusive** — so today's PRs count |
| `--repo` | `both` | `portal` \| `core` \| `both` |
| `--workspace` | `opencellsoft` | Bitbucket workspace slug |
| `--out` | `./docs/pr-rejection-rate-<TODAY>.html` | HTML report |
| `--csv` | `./docs/pr-rejection-rate-<TODAY>.csv` | One row per PR |

`<TODAY>` is `date -u +%Y-%m-%d`. A bare `/oc-pr-rejection-rate` reports **the last 7 days
on both repositories**. The resolved window is echoed before any work, matching
`oc-bug-clusters`.

## 7. Output

**Markdown to stdout** — the headline table, then the overlapping reason breakdown, then the
rejected PRs with author, reasons and link:

```
| Repository      | Total PRs | Rejected | Rejection rate |
| opencell-portal |        42 |       11 |          26.2% |
| opencell-core   |        35 |        6 |          17.1% |
| All             |        77 |       17 |          22.1% |
```

**HTML** to `./docs/`, self-contained and styled to match `oc-time-report`.

**CSV** to `./docs/`, one row per PR: repo, id, title, author, `created_on`, state, the
rejected boolean, a boolean per rule, and the URL. The per-rule booleans are what let a
reader audit *why* a PR was flagged rather than trusting the total.

The rejection rate is `rejected / total`, rounded to one decimal place, with an `All` row
across both repositories. A repository with zero PRs in the window reports `n/a`, never
`0.0%` — the two mean different things.

## 8. Failure behaviour

| Condition | What to do |
|---|---|
| `BITBUCKET_EMAIL` or `BITBUCKET_ACCESS_TOKEN` unset | Print how to create an Atlassian API token (id.atlassian.com → Security → API tokens) and stop. Never report a zero |
| `401` | Say explicitly that an `ATATT…` token authenticates as `email:token` over Basic `-u`, and that `Authorization: Bearer` returns 401 for these tokens |
| `404` on a repository | Name the workspace and slug that were tried |
| Inverted or empty window | Stop before fetching anything; relay the dates |
| Zero PRs in the window | Report it and stop — no empty HTML, no empty CSV |
| `429` | Linear backoff inside the client (`2 * (attempt + 1)`s: 2s/4s/6s/8s over five attempts); surface only if it survives the retries |
| Partial activity failure | Report the PR with the rules that could be evaluated, and emit a `WARNING:` line naming the PR. Never drop it from the total silently |

## 9. Testing

`python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`, entirely offline:

- **Rules** — one test per criterion, plus the cases that make the design: a PR opened as a
  draft then readied (not rejected), a declined PR that also had changes requested (counted
  once, two reason columns), a changes-requested later cleared by an approval (still
  rejected), and each of the three R3 detection modes.
- **Client** — paging across `next` cursors, 302 follow, 429 backoff, 401 message, against a
  stubbed opener.
- **Report** — Markdown/CSV snapshots, the `n/a` zero-PR case, and the detection-mode line
  appearing in all three outputs.
- **Packaging** — the `marketplace.json` entry exists, `plugin.json` is valid, and every
  script path referenced by `SKILL.md` is present. `oc-bug-clusters` already does this.

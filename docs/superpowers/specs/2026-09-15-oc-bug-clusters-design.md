# Bug Clustering Plugin (`oc-bug-clusters`) — Design

- **Date:** 2026-09-15
- **Jira:** INTRD-47165
- **Repos touched:** `ccode-marketplace` only (new plugin + marketplace wiring)
- **Status:** approved design, pending implementation plan

## 1. Problem

Bugs accumulate in Jira faster than anyone reads them one by one — **149 Bug/Sub-bug
issues were created in INTRD + MACRD between 2026-08-15 and 2026-09-15**. Nobody can see
from that list that seven of them are the same underlying weakness in the Quote UI, so
the team keeps fixing symptoms and never schedules the work that would stop the class of
defect.

The plugin turns a period of bugs into a small number of **subject clusters** and,
optionally, into scheduled work: one Jira **Enabler per area** holding one **Sub-task per
cluster**, with the cluster's bugs linked to it.

Three facts about the data constrain the design:

1. **Bugs carry no module component.** In a 50-bug sample the only components present were
   `Frontend` (23), `Backend` (20) and none at all (7). The product area a bug belongs to
   exists only in its summary and description prose, so grouping by subject requires
   semantic reading — it cannot be a `GROUP BY` on a Jira field.
2. **Summary tags are free-form.** The same sample carried `[Rating]`, `[Quote New UI]`,
   `[New UI - Quote]`, `[NEW UI ]`, `[BACK]`, `[Front]`, `[Portal]`, `[17.2.0]` — 25
   distinct tag spellings across 34 tagged bugs. They are a usable *fallback* signal for
   area, never a clustering key.
3. **The Atlassian MCP cannot do the fetch.** `searchJiraIssuesUsingJql` force-includes each
   issue's full `description` and caps at ~5 issues per call with no cursor; the 50-issue
   probe used while writing this spec overflowed the tool-result limit at 108 KB. Like
   `/oc-ai-report` and `/oc-time-report`, this plugin reads Jira through **direct Cloud REST**.

## 2. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Area is assigned deterministically in Python**, never by the LLM | The portal/core split decides which Enabler a bug lands under; it must not change between two runs of the same period |
| D2 | **Subject is assigned by Claude**, one label per bug, from a **seeded but extensible** taxonomy in `references/subjects.md` | A fixed vocabulary makes month-over-month counts comparable; allowing a new subject at ≥5 bugs keeps a genuinely new problem area from hiding in `other` |
| D3 | Clusters group on **subject alone**, not subject × defect-type | Single axis, one judgement per bug; a second axis was considered and dropped as unneeded for scheduling the work (YAGNI) |
| D4 | **Skill-only plugin** — no sub-agent; classification runs in the main session in batches of ~60 bugs | Matches every other report plugin here; at observed volume the classification payload is ~30 KB. A sub-agent is the escape hatch if year-long windows are ever needed |
| D5 | Fetch requests `description` (unlike `/oc-ai-report`) but **flattens and truncates it to a separate compact file** | Semantic clustering needs the prose; the fat `bugs.json` must never enter the model context |
| D6 | **One Enabler per area**, one Sub-task per cluster, bugs linked with `Relates` | Backend and frontend clusters are scheduled by different teams; a single mixed Enabler could not be assigned |
| D7 | Jira writes are **opt-in (`--create-enabler`), confirmed, idempotent and resumable** | Tickets are outward-facing and awkward to undo, and this command will be re-run on overlapping windows |
| D8a | The rejection filter checks **status and resolution**, not resolution alone | Verified against live data: `Invalid` is a status here and `Declined` is the rejecting resolution. Checking one field lets every rejected bug into the clusters |
| D8 | **Zero clusters creates nothing** | An empty Enabler is backlog noise that someone has to triage |
| D9 | Enablers carry a **default assignee per area**, pinned by `accountId`, and **Sub-tasks inherit it** | Each area has a standing owner of the cluster work, and the whole tree lands in that person's Jira queue rather than only its root. `accountId` rather than name or email because display names change and `assignee` only accepts an id |

**Non-goals.** No defect-type/root-cause axis. No MACO/`MACRD` support — `--repo` names
*portal* and *core*, and MACO is a third codebase (see `CLAUDE.md`). No Bitbucket access:
the plugin never looks at commits or PRs to decide a bug's repository. No modification to
any existing plugin.

## 3. Plugin shape

```
plugins/common/oc-bug-clusters/
  .claude-plugin/plugin.json                     # name, description, version 1.0.0
  skills/oc-bug-clusters/SKILL.md                # the whole command
  skills/oc-bug-clusters/references/subjects.md  # seeded, editable taxonomy
```

Plus one entry in `.claude-plugin/marketplace.json` with
`"source": "./plugins/common/oc-bug-clusters"`.

The plugin is **common** (no factory abbreviation), so the command is `/oc-bug-clusters`,
matching `/oc-commit`, `/oc-ai-report`, `/oc-time-report`.

Like the other report plugins it is **repo-independent**: it needs no git checkout, no
Bitbucket token, and can run from any directory.

## 4. Command contract

```
/oc-bug-clusters [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                 [--repo portal|core|both] [--create-enabler]
                 [--min-cluster N] [--project KEY[,KEY…]]
                 [--assignee-portal ID|EMAIL] [--assignee-core ID|EMAIL]
                 [--out PATH] [--csv PATH] [--force]
```

| Argument | Default | Meaning |
|----------|---------|---------|
| `--since` | 30 days before `--until` | Start of the window, inclusive, matched on `created` |
| `--until` | tomorrow | End of the window, **exclusive**, so today's bugs are included |
| `--repo` | `portal` | `portal` → component `Frontend`; `core` → component `Backend`; `both` → each area analysed separately |
| `--create-enabler` | off | Create the Jira Enabler(s). Off means report only |
| `--min-cluster` | `5` | Bugs needed on one subject before it is a cluster |
| `--project` | `INTRD` | Portal *and* core both live in INTRD; `MACRD` is MACO and out of scope |
| `--assignee-portal` | Mohamed Hamidi | Assignee of the **Frontend** Enabler. Takes an `accountId` or an email, which is resolved to an id before any write |
| `--assignee-core` | Adil El Jaouhari | Assignee of the **Backend** Enabler, same forms |
| `--out` | `./docs/bug-clusters-<TODAY>.html` | Styled HTML report |
| `--csv` | `./docs/bug-clusters-<TODAY>.csv` | One row per bug: key, area, subject, cluster?, status, created, summary, URL |
| `--force` | off | Create a second Enabler for a window that already has one |

**Default assignees.** Each area has a standing owner, pinned by `accountId` because
`assignee` accepts nothing else and display names drift:

| Area token | Component | Default assignee | `accountId` |
|---|---|---|---|
| `portal` | `Frontend` | Mohamed Hamidi (`mohamed.hamidi@opencellsoft.com`) | `5ef5c13914f60e0ac1c9b049` |
| `core` | `Backend` | Adil El Jaouhari (`adil.eljaouhari@opencellsoft.com`) | `63369fa788ed2ebef97cddfb` |

These ids live in one table at the top of `SKILL.md` so a handover is a one-line edit.
**Sub-tasks inherit their Enabler's assignee**, so an area's whole cluster tree lands in
one person's queue and can be redistributed from there.
An `--assignee-*` value given as an email is resolved via
`GET /rest/api/3/user/search` before the confirmation prompt, so an unresolvable name
stops the run while nothing has been written.

**Vocabulary.** The **area token** is `portal` or `core` — it is what `--repo` takes, what
keys `assignments.json`, and what appears in the marker label. Its **Jira component** is
`Frontend` or `Backend` — that is what is set on the Enabler and what is printed in issue
summaries, because it is the word the team reads in Jira. The two are never mixed.
`<TODAY>` in the default output paths is the run date, `date -u +%Y-%m-%d`.

Missing dates are computed with `date -u -d '30 days ago' +%Y-%m-%d` (Python `datetime`
where `date -d` is unavailable). **The resolved window and area(s) are echoed back before
any work starts**, so the defaults are visible: `Analysing INTRD bugs, portal,
2026-08-16 → 2026-09-16`.

## 5. Access

Requires **`JIRA_API_TOKEN`** (plus `JIRA_EMAIL`), an Atlassian API token, read from the
environment and **never passed on the command line** — identical to `/oc-ai-report`. If it
is unset the command prints setup instructions and stops; it never falls back to the MCP.

Reads: `POST /rest/api/3/search/jql`. Writes: `POST /rest/api/3/issue`,
`POST /rest/api/3/issueLink`, `GET /rest/api/3/issue/createmeta/...`. Basic auth,
`email:token`.

## 6. Pipeline

Five stages, each leaving a file in the scratchpad so a failure is resumable.

### Stage 1 — Fetch (`bug_fetch.py` → `bugs.json`, `classify_input.jsonl`)

JQL:

```
project in (<--project>)            -- default: INTRD
  AND issuetype in (Bug, Sub-bug)
  AND created >= "<since>" AND created < "<until>"
ORDER BY created DESC
```

Fields: `summary, description, issuetype, status, resolution, components, labels,
created, priority, assignee, reporter, parent`. Paginated 100/page via `nextPageToken`,
retrying 429/503.

**Rejection filter.** Bugs the team rejected as non-defects are dropped — they would
pollute a cluster. **Two fields must be checked, not one** (measured against live INTRD
data, 2025-09 → 2026-09):

- `resolution.name` in `Invalid` / `Duplicate` / `Declined`
- **or** `status.name` = `Invalid`

`Invalid` is a **status** in this Jira — 416 bugs carry it over a year — and never
appears as a resolution; the resolution used to reject a bug is **`Declined`** (13 of a
100-bug sample). A resolution-only filter, as this spec originally specified, would have
dropped essentially nothing. Every other status counts, open or closed. The count of
dropped issues is reported.

Not dropped, deliberately: `Cannot Reproduce` and `Won't Do`. Both can sit on a real
defect the team chose not to pursue, and dropping them would hide genuine clusters.

Two outputs:
- `bugs.json` — the full records. Never read into the model context.
- `classify_input.jsonl` — one compact line per bug: `key`, `summary`, `excerpt`
  (description flattened from ADF to plain text, whitespace-collapsed, **truncated to 300
  characters**), `component`, `labels`. This is the only file Claude reads.

If the ADF flatten fails for a bug, its `excerpt` is empty and classification proceeds on
the summary alone.

### Stage 2 — Area assignment (deterministic, in `bug_fetch.py`)

```
component "Frontend" → portal
component "Backend"  → core
else summary matches /^\s*\[\s*(front|back)/i → portal | core
else → unclassified
```

`unclassified` bugs are **listed in the report but never clustered and never linked to an
Enabler**. On the 50-bug sample this is 7 bugs (14%); the report states the count so the
loss is visible rather than silent.

When `--repo` is `portal` or `core`, bugs of the other area are excluded from the report
entirely (they are still counted in the "fetched" total).

### Stage 3 — Subject classification (Claude)

For each area in scope, read `classify_input.jsonl` in batches of ~60 bugs and append to
`assignments.json`:

```json
{"INTRD-47162": "rating", "INTRD-47140": "quoting", "INTRD-47131": "quoting"}
```

Rules given to the model:

1. Exactly **one** subject per bug — no multi-label, no ties.
2. Prefer a subject already in `references/subjects.md`.
3. A **new** subject may be coined only when **≥ `--min-cluster` bugs in the same area**
   fit none of the seeded ones — the same threshold that makes a cluster, so coining a
   subject can never produce a group too small to be one. A new subject is reported
   prominently so `subjects.md` can be updated.
4. Subject names are lower-kebab-case, drawn from the product vocabulary, never from the
   defect's symptom (`quoting`, not `blank-screen`).
5. Judge the subject from what the bug is *about*, not which tag the reporter typed.

Every bug in scope must appear in `assignments.json`; stage 4 fails loudly on a missing
key rather than silently dropping it.

### Stage 4 — Cluster and report (`bug_cluster.py`)

Group by `(area, subject)`. A group of **≥ `--min-cluster`** bugs is a **cluster**; the
rest fall into a **near-clusters** tail so a subject sitting at 4 is visible.

Report sections, per area:

1. **Header** — window, project, area, bugs fetched / kept / unclassified / dropped-invalid.
2. **Clusters** — one row per cluster: subject, bug count, open vs. closed split, most
   frequent labels, span of created dates.
3. **Cluster detail** — per cluster, every bug: key (linked to
   `https://opencellsoft.atlassian.net/browse/<KEY>`), summary, status, created, assignee.
4. **Near-clusters** — subjects below the threshold, with counts.
5. **Unclassified** — bugs with no resolvable area, listed with keys and summaries.

Output: Markdown printed to the terminal, plus a self-contained styled HTML at `--out` and
a CSV at `--csv` (`docs/` created if missing). With `--repo both`, the HTML carries one tab
per area, following the tabbed layout `/oc-ai-report` already uses.

### Stage 5 — Jira write (`bug_enabler.py`, only with `--create-enabler`)

Skipped entirely when no area produced a cluster; the command says so and exits 0.

**Pre-flight.** `GET /rest/api/3/issue/createmeta` for `Enabler` and `Sub-task` in the
target project, verifying every required field is present in the payload. A missing
required field stops the run **before any write**.

**Idempotency.** Each Enabler carries a marker label
`bug-clusters-<area-token>-<since>-<until>` (e.g.
`bug-clusters-portal-2026-08-16-2026-09-16`).
Before creating anything, `labels = "<marker>" AND project = <project>` is searched; an
existing Enabler is reported and skipped unless `--force`.

**Confirmation.** The full plan is printed — every Enabler and Sub-task summary, the bug
counts, the exact number of API calls — and the command **stops for an explicit yes**.
Nothing is posted before that.

**Creation order**, per area with ≥1 cluster:

| Object | Type | Summary | Notes |
|--------|------|---------|-------|
| Enabler | `10076` | `Bug clusters — Frontend — 2026-08-16 → 2026-09-16` | component `Frontend`/`Backend`, **`assignee` = that area's default**, marker label, description = window + filters + cluster overview + local report path |
| Sub-task | `10003` | `<subject> — N bugs` | `parent` = the Enabler, **`assignee` inherited from it**, description = every bug key and summary |
| Link | `Relates` | — | one per bug, bug ↔ its Sub-task |

Descriptions are built as **ADF** — REST v3 rejects a raw string on create.

**Resumability.** `created.json` is appended to as each object is made and re-read on a
retry, so a re-run continues instead of duplicating. **Issue links are best-effort**: a
failed link is collected and reported at the end and never aborts the run, because a
missing link is cosmetic while a half-created Enabler is not.

## 7. Failure behaviour

| Condition | Behaviour |
|-----------|-----------|
| `JIRA_API_TOKEN` unset | Print setup instructions, stop. Never fall back to the Atlassian MCP |
| Zero bugs in the window | `No bugs created in <window> for <project>`, stop |
| Zero clusters | Print the near-clusters tail, create nothing, exit 0 |
| A bug missing from `assignments.json` | Fail loudly, naming the key |
| ADF flatten failure on one bug | Empty excerpt, classify on summary alone |
| `createmeta` shows an unexpected required field | Stop before any write |
| `--assignee-*` email resolves to no user | Stop before any write, naming the value |
| Jira rejects the `assignee` (inactive user, no browse permission) | **Retry the create unassigned**, for the Enabler and for any Sub-task, warning loudly with the id — a clustered Enabler nobody owns still beats no Enabler |
| Sub-task create fails | Enabler kept, `created.json` written, run re-entrant |
| Issue link fails | Collected, reported at the end, run continues |

## 8. Verification

The repository has no test harness — it is entirely Markdown and JSON — so verification is
a pair of real runs, reconciled against figures measured while writing this spec:

1. **Read-only:** `/oc-bug-clusters --since 2026-08-15 --until 2026-09-15 --repo both`.
   The fetched total must reconcile against the raw JQL count of **149** for
   `INTRD + MACRD` (INTRD alone will be lower), and the area split must be roughly
   46% portal / 40% core / 14% unclassified, matching the 50-bug sample.
2. **Write, gated:** one `--create-enabler` run whose printed payloads are reviewed
   object-by-object before approval, then re-run immediately to confirm the marker label
   makes the second run a no-op.
3. **Plugin loads:** `.claude-plugin/marketplace.json` parses, the plugin appears in
   `/plugin`, and `/oc-bug-clusters --help`-style bare invocation echoes the resolved
   defaults.

## 9. Documentation

`CLAUDE.md` gains `oc-bug-clusters` in the **Plugin Types** skill list and a short entry
noting the two non-obvious constraints: **area is deterministic, subject is not**, and
**the marker label is what makes re-runs safe**.

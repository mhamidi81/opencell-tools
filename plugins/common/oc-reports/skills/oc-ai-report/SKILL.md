---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period. AI metrics grouped by developer domain (backend/frontend/QA); per-area Architect estimate (custom fields) and Dev-lead estimate (ticket field / sum of child sub-task estimates); ticket type; bug counts and hours-logged-on-bugs per area; logged hours per user & ticket via the Tempo API (fallback Jira worklogs); time gain without/with bug hours; sections ordered Totals → Summary → Detail. Fetches Jira via direct Cloud REST (enhanced /search/jql, fields-limited, no descriptions, paginated) using a mandatory JIRA_API_TOKEN — no Atlassian MCP; Tempo optional. Prints Markdown and writes a styled HTML file to ./docs/ai-usage-report-<date>-<start>-<end>.html. Totals-by-area shown in days (1 d = 8 h).
argument-hint: "[--since 2026-07-01] [--until <tomorrow>] [--project INTRD,MACRD] [--out PATH]"
---

## Purpose

Aggregate the machine-readable **AI-usage records** that `/oc-be-calculate-ai-use` (and the future frontend / QA equivalents) write to the **"AI metrics"** field (`customfield_10745`), across many tickets over a time window, into one report:

- A **summary table by user** (one row per developer, aggregated), then **details per user by ticket**, then **totals by area** (a plain sum of the detail rows).
- **AI metrics** (contribution / retention / tests / requests) are grouped by each record's **domain** (`backend`/`frontend`/`qa`, per developer). Each detail row also shows the **ticket type** (US / Bug / Sub-bug / Enabler) and **two estimates per area**: **A. Est h** (Architect) from the Story's estimate custom fields — *Architect estimate back* (`customfield_10157`), *front* (`customfield_10158`), *QA estimate* (`customfield_10189`), days ×8, else the ticket's own estimate; and **DL. Est h** (Dev-lead) from the ticket's *estimation field* — for a User Story the sum of that area's child **sub-task** estimates (sub-bug estimates excluded), for a Bug/Enabler the ticket's own estimate. A **Sub-bugs** count and a separate **Sub-bug h** (hours logged on child Bug/Sub-bug sub-issues) are attributed per area; a sub-bug counts **only once time has been logged on it** — a sub-bug with zero logged hours does not exist for the report (matching the time report). **Logged hours** are the record author's own Tempo hours **across the whole User Story** — the parent **plus its non-bug sub-tasks** (a US's dev work is booked on its sub-tasks), falling back to the parent Jira worklog → ticket total only when Tempo has nothing for that author anywhere on the US. A **sub-bug's hours always count against its parent US** (in the US's Sub-bug h and count). If the sub-bug **also** carries its own AI record it is *additionally* shown as its **own row** in *Detail per user* — its Type is **Sub-bug**, tagged **`(part of <US>)`** — and that separate row is **excluded from every aggregate** (Totals / Summary / month / KPI / gain) so its hours are counted once, in the US (Case 2: JSON on the US **and** on a sub-bug). A non-bug **sub-task** with its own record is likewise its own row and excluded from the parent's Logged rollup. Plus a **time-gain %** (Architect estimate vs. logged, shown **with / without** bug hours) — in every **aggregate** row (area, user, month, KPI card) the gain is computed over **only the tickets carrying that estimate**, so an unestimated ticket contributes neither its estimate nor its logged hours. Every **ticket key is a link** to `https://opencellsoft.atlassian.net/browse/<KEY>`. Sections are ordered **Totals by area → Summary by user → Detail per user**, and users are ordered **by area, then name**. A cross-area sub-bug (one whose component area has no AI record on the ticket) is not mixed into another area's numbers — it is shown as an annotation like **`2 (front +1 7.8h)`**.

This command is **read-only** — it only queries Jira. It needs **no** Bitbucket token, **no** git, and **no** repo checkout; it can run from any directory.

## Scripts

The Python scripts and the developer roster ship **with this plugin** as files — do not re-create them. The skill's base directory is printed above as *"Base directory for this skill: …"*; the scripts live two levels up, in the plugin's `scripts/` folder:

```
<SCRIPTS> = <base directory>/../../scripts
```

Run them **in place** from `<SCRIPTS>` (never copy or edit them — the plugin cache is overwritten on update; fixes go into the `ccode-marketplace` source, `plugins/common/oc-reports/scripts/`). Intermediate data files (`issues.json`, `tempo.json`, …) go to `<SCRATCHPAD>`. The scripts are shared by `/oc-reports:oc-time-report`, `/oc-reports:oc-noai-report` and `/oc-reports:oc-ai-report`.

## Access

Requires **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token (*id.atlassian.com → Security → API tokens*). All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `<SCRIPTS>/ai_jira_fetch.py`. The token is **mandatory** and read from the environment (never on the command line); if unset, tell the user to create one and stop. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql`** — it force-includes each issue's full `description` and caps at ~5 issues/call with no cursor. Direct REST honours the `fields` list (excludes `description`), returns 100/page and paginates via `nextPageToken`.

> **Tempo (per-user logged time).** Tempo syncs its worklogs into Jira under the **Tempo app account**, so Jira alone can't attribute logged time per developer. For true per-user hours, set **`TEMPO_API_TOKEN`** (each developer makes their own in *Tempo → Settings → API keys*, worklog **read** scope) and the report calls the Tempo REST API (`api.tempo.io/4`) in Pass C. It is **optional**: without the token the report falls back to the Jira `worklog` / `timespent` fields (ticket total). The token is read from the environment, never passed on the command line.

## Arguments

Parse `$ARGUMENTS` — **all optional**. A bare `/oc-reports:oc-ai-report` reports from **2026-07-01 to tomorrow** for **INTRD and MACRD**, and — because **PRT730 is a Protected project** — **asks the user whether to include PRT730** before running (see the `--project` note below).

- `--since YYYY-MM-DD` — start of the period (inclusive), matched against each record's `at`. **Default: `2026-07-01`.**
- `--until YYYY-MM-DD` — end of the period (exclusive). **Default: tomorrow** (so today's records are included).
- `--project KEY[,KEY…]` — Jira project(s), comma-separated. Backend work
  is raised in `INTRD` (core *and* overlay) and in `MACRD` (MACO R&D / overlay), so both are always in scope.
  Areas are by discipline, not repository — overlay Java/xhtml records arrive as `backend`.
  Pass **`all`** (or `*`) to report **every** Jira project that carries AI records (the fetch drops the `project in (…)` clause); this is an explicit choice, so it includes Protected projects without a prompt.
  **When the user passes `--project` explicitly (including `all`), honour it verbatim and do NOT ask anything.**
  **When `--project` is NOT passed, the base default is `INTRD,MACRD`, and — because `PRT730` (Protected - 730) is a Protected project — you MUST ask the user before report generation whether PRT730 should be included** (e.g. "PRT730 is a Protected project — include it in this report? (yes/no)"). On **yes**, run with `--project INTRD,MACRD,PRT730`; on **no**, run with `--project INTRD,MACRD`. Echo the resolved project list back with the window.
- `--out PATH` — where to write the HTML report. **Default: `./docs/ai-usage-report-<TODAY>-<SINCE>-<UNTIL>.html`** where `<TODAY>` is the run date (`date -u +%Y-%m-%d`) and `<SINCE>`/`<UNTIL>` the window bounds, e.g. `./docs/ai-usage-report-2026-09-17-2026-01-01-2026-09-18.html` (relative to the current directory; the `docs/` folder is created if missing).
- `--csv PATH` — also write the **ticket-detail rows** as CSV (spreadsheet-friendly). **Default: `./docs/ai-usage-report-<TODAY>-<SINCE>-<UNTIL>.csv`** (same folder/name-stamp as the HTML).

Compute any missing date with the shell — `date -u +%Y-%m-%d` (today), `date -u -d 'tomorrow' +%Y-%m-%d`; if `--since` is omitted, default it to **`2026-07-01`** (not a rolling 30-day window). If `date -d` is unavailable, use Python `datetime`. Echo the resolved window back to the user (e.g. "Reporting INTRD, MACRD, 2026-07-01 → 2026-09-24") so the defaults are visible.

## Task 1 — Fetch the tickets (two passes: parents, then sub-issues)

Only Jira dates are JQL-filterable (the record's `at` lives *inside* the text field), so cast a slightly wide net on `updated` and let the aggregator do the precise `at` filtering. Writing the AI record updates the ticket, so `updated >= since` never drops an in-period record.

**Why two passes.** AI metrics are grouped by the record key's **domain** (`backend`/`frontend`/`qa`, per developer). The **Architect estimate (A. Est h)** is on the parent (per-area custom fields). But the **Dev-lead estimate (DL. Est h)** for a User Story is the **sum of its child sub-tasks' estimates** per area, and **bug counts / bug-logged hours** come from its child **Bug / Sub-bug** sub-issues — neither the subtasks' estimates nor their `timespent`/area are in the parent payload, so a second fetch of the children is needed.

**Both passes in one script.** Run `<SCRIPTS>/ai_jira_fetch.py` — it does Pass A and Pass B via the Jira REST enhanced-search endpoint (fields-limited, `description` excluded, 100/page, `nextPageToken` paging) and writes `tickets.json` + `children.json`:

```bash
python "<SCRIPTS>/ai_jira_fetch.py" --since [SINCE] --project [PROJECT] \
  --out-tickets "<SCRATCHPAD>/tickets.json" --out-children "<SCRATCHPAD>/children.json"
```

- **Pass A** runs `project = [PROJECT] AND cf[10745] IS NOT EMPTY AND updated >= "[SINCE]"` with fields `["summary","assignee","issuetype","status","resolutiondate","updated","timeoriginalestimate","timespent","worklog","components","customfield_10157","customfield_10158","customfield_10189","customfield_10745","customfield_10613"]` → `tickets.json`. If it returns 0 tickets, tell the user "No tickets with AI-metrics data found for [PROJECT] since [SINCE]" and stop.
- **Pass B** fetches every child sub-issue of those parents (`parent in (<keys>)`, batched) with `["summary","issuetype","components","timeoriginalestimate","timespent","parent","customfield_10745"]` → `children.json`. Both regular sub-tasks and Bug/Sub-bug sub-tasks are needed: non-bug sub-tasks feed the Dev-lead estimate **and roll their logged hours up into the parent US's record** (a US's dev work is booked on its sub-tasks), while Bug/Sub-bug ones feed the bug count and Sub-bug h. **`customfield_10745` on the child** tells the aggregator whether the sub-issue carries its **own** AI record — if it does, that sub-issue is its own report row and is *excluded* from the parent's rollup (no double-count). **Issue links are deliberately NOT used.**

Notes on the fields:
- `status` drives the **Status** column and the **Final** flag in the *Detail per user* tables: a ticket is *final* when its Jira status (case-insensitive) is terminal for its type — **Bug**: Done/Invalid; **US**: Ready for Sprint review / Need documentation / Ready for release / Released; **any other type**: Done. **AI Contrib below 60% is shown in red** in both the *Summary by user* and *Detail per user* tables.
- The three estimate custom fields (**days**) are the per-area estimates on a User Story: `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate*. The aggregator converts days → hours (×8) and, if none are set (a standalone Bug), falls back to the ticket's own `timeoriginalestimate`. Sub-issue estimates are **never summed**.

**Pass C — per-user logged time from Tempo (optional but preferred):**
5. Tempo Timesheets syncs its worklogs into the Jira `worklog` field **under the Tempo app account**, so Jira alone cannot split logged time per developer. Tempo's own REST API keeps the real `author.accountId`. If the environment variable **`TEMPO_API_TOKEN`** is set (each developer creates their own token in *Tempo → Settings → API keys*, worklog **read** scope), fetch true per-user hours; otherwise skip and the aggregator falls back to Jira worklogs / ticket total.
6. Run `<SCRIPTS>/fetch_tempo.py` with the **numeric issue ids** of the parents (`node.id` from Pass A) **and ALL of their child sub-issues** (from Pass B — both the Bug/Sub-bug sub-issues *and* the non-bug sub-tasks). A User Story's dev work is booked on its **sub-tasks**, so their per-user hours must be fetched for the record's *Logged* to reflect the real work (parent + non-bug sub-tasks); the Bug/Sub-bug ids resolve the per-user *Sub-bug h*:
   ```bash
   python "<SCRIPTS>/fetch_tempo.py" --ids "93179,107118,109478,<all-child-sub-issue-ids…>" --out "<SCRATCHPAD>/tempo.json"
   ```
   It reads `TEMPO_API_TOKEN` from the environment (never pass the token on the command line), calls `GET https://api.tempo.io/4/worklogs/issue/{id}` (paginated via `metadata.next`), and writes `{"<issueId>": {"<accountId>": seconds}}`. On a missing token or a 401 it writes `{}` and the report still runs (logged falls back to Jira worklog / ticket total; Bug h to the bug's `timespent`).



## Task 2 — Run the aggregator

Run `<SCRIPTS>/ai_report.py` (Python 3 is available as `python`):

```bash
python "<SCRIPTS>/ai_report.py" --input "<SCRATCHPAD>/tickets.json" --children "<SCRATCHPAD>/children.json" --tempo "<SCRATCHPAD>/tempo.json" --since [SINCE] --until [UNTIL]
```

(`--children`/`--tempo` are optional; omit if that pass was skipped.) It prints a Markdown report in this order: **Totals by area** (a plain sum of the detail rows), **Summary by user**, then **Detail per user by ticket** (which also shows ticket type). AI metrics group by the record's **domain**; **A. Est h** (Architect) per area from the Story's estimate custom fields; **DL. Est h** (Dev-lead) per area from the ticket estimation field (US → sum of child sub-task estimates, else the ticket estimate); **bug counts** and **Sub-bug h** per area from child Bug/Sub-bug sub-issues; **logged hours** per user & ticket. Display it to the user verbatim.


## Task 3 — Write the HTML report

Also render a **self-contained, styled HTML file** from the same `tickets.json`. Run `<SCRIPTS>/ai_report_html.py`, pointing `--out` at the resolved output path (default `./docs/ai-usage-report-<TODAY>-<SINCE>-<UNTIL>.html`, `<TODAY>` = `date -u +%Y-%m-%d` — the date-stamp keeps successive reports side by side rather than overwriting):

```bash
python "<SCRIPTS>/ai_report_html.py" --input "<SCRATCHPAD>/tickets.json" \
  --children "<SCRATCHPAD>/children.json" --tempo "<SCRATCHPAD>/tempo.json" \
  --since [SINCE] --until [UNTIL] --project [PROJECT] \
  --out "./docs/ai-usage-report-[TODAY]-[SINCE]-[UNTIL].html" --csv "./docs/ai-usage-report-[TODAY]-[SINCE]-[UNTIL].csv"
```

The page is theme-aware (light/dark) and embeds all CSS — no external assets — so it opens straight from disk. **Five tabs (HTML only):** an **All** tab (every ticket, the default), a **User Stories (All)** tab (US only), a **User Stories (Final)** tab (US whose status is terminal, Final = T), a **Bugs (final)** tab (Bug/Sub-bug tickets in a terminal status) and a **Bugs and others** tab (every non-US ticket); each tab holds the full report (KPI cards + the three sections) filtered to that ticket set. There is also a **Project-filter picklist** (the distinct Jira project prefixes present, plus *All*): each project scope has its own fully server-rendered set of the 5 tab panels, and a small vanilla-JS controller shows the one matching the selected project × tab (tabs are JS-driven `<button>`s, not pure CSS). Within each tab, KPI cards lead, then the three sections mirroring the Markdown. **Grouping (HTML only):** *Totals by area* shows the overall table, then an expandable `<details>` block per month (the date is the record's `at`, newest open). *Summary by user* shows the overall one-row-per-user table (each developer's name **links down to their Detail-per-user section** in the same tab), then an expandable `<details>` block **per user**, each holding that developer's month-by-month breakdown (user → month). *Detail per user* groups each developer's tickets into expandable months, and every ticket key is a link to its Jira issue. (Anchor ids are prefixed per tab, so the same developer is uniquely addressable in each tab.) Tell the user the absolute path and that they can open it in a browser (Windows: `start "" "<path>"`).

`--csv` additionally writes the **ticket-detail rows** (one row per ticket × developer, all detail columns, both time-gain values and a trailing **URL** column with the ticket's Jira link) to a spreadsheet-friendly CSV (UTF-8 with BOM so Excel renders accented names). Default `./docs/ai-usage-report-<TODAY>-<SINCE>-<UNTIL>.csv`. Report both file paths to the user.


## Task 4 — Present (and optionally visualise)

- Show the Markdown report and the path to the HTML file.
- Optionally offer a richer **dashboard Artifact** (bar charts: contribution/retention per area & developer, estimate-vs-logged, bug counts) — build it only if the user asks, and see the `dataviz` skill before drawing charts.

## Notes & limitations

- **Two area sources & two estimates.** *AI metrics* group by the record `domain` (per developer — a story worked by backend and frontend keeps both). **A. Est h** (Architect) comes from the Story's **per-area estimate custom fields** — `customfield_10157` (back), `customfield_10158` (front), `customfield_10189` (QA), in **days ×8**; if none are set (a standalone Bug/Enabler) the ticket's own `timeoriginalestimate` is used. **DL. Est h** (Dev-lead) comes from the **ticket estimation field**: for a User Story, the **sum of that area's child sub-task estimates** (sub-bug estimates excluded); for a Bug/Enabler, the ticket's own estimate. *Sub-bugs* (the count) and *Sub-bug h* come from the ticket's **child Bug/Sub-bug** sub-issues (never issue links), attributed by the bug's Component/title, else the parent's area. Ticket **type** (US/Bug/Enabler) is shown per detail row. Only areas that have an AI record show up (the report is record-driven).
- **Totals = sum of the detail rows** (no independent recompute). A ticket's estimate/bugs land under the area(s) with records; if two developers in the same area worked one ticket, their rows both count (rare).
- **Date = the AI record's `at`** (the day the metric was measured/confirmed). The JQL `updated >=` window is only a pre-filter; precise period membership is decided by `at` in the aggregator.
- **Logged hours** (the record author's own hours across the whole US — parent **+ its non-bug sub-tasks**): **Tempo per-user** (`TEMPO_API_TOKEN`, real author), falling back to the parent **Jira worklog** author → **ticket-total** `timespent` only when Tempo has nothing for that author on the US. A sub-task/sub-bug with its **own** AI record is its own row and is excluded from the parent rollup (no double-count). All time figures in the HTML tables and the CSV are shown in **days** (1 d = 8 h). **Time gain** is shown as **two numbers, `with / without` bug hours**, and in the aggregate rows is computed over **only the tickets that have the matching estimate** (a ticket with no Architect estimate is left out of the Arch gain entirely — both its estimate and its logged hours — and likewise for the Dev-lead gain), so an unestimated ticket can no longer drag a whole area or developer negative; the Est h / Logged h columns beside it still show the **full** sums: `(estimate − (logged + Bug h))/estimate` first (with bugs), then `(estimate − logged)/estimate` (without bugs). Positive = under estimate. (When logged falls back to a ticket total rather than Tempo per-user, the estimate is per-area while logged is whole-ticket, so the value can read oddly.)
- **Sub-bugs & Sub-bug h** = the ticket's **own child sub-issues** of type `Bug` or `Sub-bug` — **issue links are not counted** (a "Relates" link would pull in duplicate/related bugs not raised against this ticket's work). Each sub-bug is attributed to an area **by its own Component/title only** — unlike non-bug sub-tasks (which inherit the parent's area for the DL estimate), a sub-bug does **not** inherit the parent's area, so a sub-bug with **no area signal of its own is not counted**. Only a sub-bug **in the area's own component** drives that area's count and **Sub-bug h**. Because this report measures **per-area AI impact** (a different developer per area — one backend, one frontend, one QA on a User Story), a cross-area sub-bug is **not mixed into another area's numbers**: a sub-bug whose component is a different area (and that area has no AI record on the ticket) is surfaced **only as an annotation**, **`2 (front +1 7.8h)`** — 2 own-area sub-bugs, plus a note that 1 frontend sub-bug totalling 7.8h exists (counted under frontend, not here). The base number and **Sub-bug h** are own-area only; the parenthetical lists each cross-area source's count and total hours. **Sub-bug h** is the hours logged on the own-area bugs (Tempo per-user → the bug's `timespent`), shown as a **separate** column from the ticket's Logged h. The CSV keeps the own count in **Sub-bugs** and the cross-area note in a **Sub-bugs (other areas)** column.
- **Read-only** — the command never writes to Jira, Bitbucket, or git; outbound calls are read-only: the Jira REST enhanced-search reads (Passes A/B) and the Tempo worklog fetch (Pass C) when a token is set.
- The AI records are **latest-only per developer×domain**, so the report reflects the most recent measurement per person per ticket, not a full history.

## Examples

```bash
# Monthly report for INTRD
/oc-reports:oc-ai-report --since 2026-07-01 --until 2026-08-01

# A specific sprint window, another project
/oc-reports:oc-ai-report --since 2026-07-14 --until 2026-07-28 --project ABC
```

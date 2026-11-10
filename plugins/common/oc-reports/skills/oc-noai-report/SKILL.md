---
name: oc-noai-report
description: Companion to /oc-reports:oc-time-report that surfaces work reaching test/review/done WITHOUT AI. Same Tempo-worklog data and the same Project + grouped Fix-version filters and five tabs. Scope: tickets whose status is one of In Test / Need sync (after dev) / Ready for Test / Ready for Sprint Review / Done, ticket-date >= a cutoff (default 2026-09-01, since AI use before then was negligible). Sub-tasks roll up into their parent US, but sub-bugs are kept as their OWN rows (not rolled under the US); the unit is one ticket x dev area (backend/frontend/qa; overhead excluded). A unit has AI when it has AI-classified logged time (same rule as the time report: a worklog is AI when its author holds an AI-metrics record on the issue; a US record propagates to its non-bug sub-tasks; a sub-bug uses its own record). Three sections: Totals by area and Totals by month (Area/Month, total tickets, AI tickets, % AI tickets, logged d, AI logged d, % AI logged), and Details listing the no-AI units (Ticket, date, Type, Fix version, title, status, Logged d, area, main developer) grouped by area then month. All times in days (1 d = 8 h). Date-stamped HTML to ./docs/. Jira via direct REST (mandatory JIRA_API_TOKEN) + Tempo per-user (mandatory TEMPO_API_TOKEN); no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD,MACRD] [--out PATH]"
---

## Purpose

A **non-AI adoption** report — the companion to `/oc-reports:oc-time-report`. It answers: *which work reached testing / review / done **without** any AI-logged time?* It is driven by the same **Tempo worklogs** + **AI-metrics records** and shares the time report's **Project** and grouped **Fix-version** filters and the same **five tabs** (All · User Stories (All) · User Stories (Final) · Bugs (Final) · Bugs and Others).

**Scope.** A ticket is in scope when its **status** is one of **In Test · Need sync (after dev) · Ready for Test · Ready for Sprint Review · Done** and its **ticket date** is **>= the cutoff** (`--since`, default **2026-09-01** — before then AI use was negligible, so earlier tickets would distort the % AI). The ticket date is the date it was **first sent to test** — its first status transition into *Ready for Test* or *In Test*, read from the Jira status history (bulk changelog). A ticket that never went to test uses its first move into a post-dev status (*Need sync (after dev)*, *Ready for Sprint Review*, *Done*, …), else its `resolutiondate`, and one still in development uses its **last worklog date**. Jira's `updated` is **never** used — any edit (a comment, a classification field) moves it, which used to drag long-finished tickets into the current month.

**Unit = one ticket × one dev area.** A ticket worked by two areas counts once per area, so "% AI" is a per-area adoption rate. **Sub-tasks roll up into their parent US; sub-bugs are kept as their OWN rows** (not rolled under the US). **Overhead** people (Architect / PO / DevOps / Consultant / management) are **excluded** (not a dev area).

**AI classification** is the time report's rule: a worklog is **AI-assisted** when its author holds an AI-metrics record (`customfield_10745`) on the issue it is booked on; a **US's record propagates to its non-bug sub-tasks**; a **sub-bug** is judged on its **own** record. A unit **has AI** when it has any AI-classified logged time.

**Sections** (inside each tab, recomputing live under the filters):
- **Totals by area** — one row per area (Backend / Frontend / QA) + a Total row: **Area · Tickets · AI tickets · % AI tickets · Logged d · AI logged d · % AI logged**.
- **Totals by month** — same columns, grouped by month instead of area.
- **Details** — only the units with **no** AI logged time, grouped by **area → month**: **Ticket · Date · Type · Fix version · Title · Status · Logged d · Area · Main developer**. Ticket keys link to Jira.

All times are in **days** (1 d = 8 h). Output: a self-contained styled **HTML** file, date-stamped in `./docs/`.

## Scripts

The Python scripts and the developer roster ship **with this plugin** as files — do not re-create them. The skill's base directory is printed above as *"Base directory for this skill: …"*; the scripts live two levels up, in the plugin's `scripts/` folder:

```
<SCRIPTS> = <base directory>/../../scripts
```

Run them **in place** from `<SCRIPTS>` (never copy or edit them — the plugin cache is overwritten on update; fixes go into the `ccode-marketplace` source, `plugins/common/oc-reports/scripts/`). Intermediate data files (`issues.json`, `tempo.json`, …) go to `<SCRATCHPAD>`. The scripts are shared by `/oc-reports:oc-time-report`, `/oc-reports:oc-noai-report` and `/oc-reports:oc-ai-report`.

## Access

Both tokens are **mandatory** and read from the environment (never passed on the command line). If either is missing, tell the user how to create it and **stop**.

- **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token from *id.atlassian.com → Security → API tokens*. All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `<SCRIPTS>/jira_fetch_dates.py`. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql`** — it force-includes each issue's full `description` and caps at ~5 issues/call. Direct REST honours the `fields` list, returns 100/page and paginates via `nextPageToken`.
- **`TEMPO_API_TOKEN`** (each developer's own token, *Tempo → Settings → API keys*, worklog **read** scope) — logged hours are the whole point. Fetched **per-user** (`/worklogs/user/{accountId}`), org-wide visibility.

## Arguments

Parse `$ARGUMENTS` — all optional.

- `--since YYYY-MM-DD` — the **cutoff**: only tickets whose date is on/after this are counted. Default **2026-09-01**. (Passed as `--since` to the Jira fetch and as `--cutoff` to the aggregator.)
- `--until YYYY-MM-DD` — end (exclusive). Default: tomorrow.
- `--project KEY[,KEY...]` — Jira project(s), comma-separated. **When the user passes `--project` explicitly, honour it verbatim and do NOT ask.** **When `--project` is NOT passed, the base default is `INTRD,MACRD`, and — because `PRT730` (Protected - 730) is a Protected project — you MUST ask the user before report generation whether PRT730 should be included** (e.g. "PRT730 is a Protected project — include it? (yes/no)"). On **yes** run with `INTRD,MACRD,PRT730`; on **no** `INTRD,MACRD`. Echo the resolved project list + window back.
- `--out PATH` — HTML output. Default `./docs/noai-report-<TODAY>-<SINCE>-<UNTIL>.html`.

Compute dates with `date -u +%Y-%m-%d` etc.; echo the resolved window back to the user.

## Developer roster

The roster ships with the plugin as **`<SCRIPTS>/devmap.json`** (shared with the time report; accountIds are stable) — pass that path as `--devmap`. Schema `{ "<accountId>": {"name", "area", "role", "active"} }`, **area ∈ `backend` | `frontend` | `qa` | `overhead`**. Overhead roles (ARCHI/PO/DEVOPS/CONSULTANT/NONE) are excluded from this report's areas. If the team changed, re-resolve via `GET /rest/api/3/users/search?startAt=&maxResults=200` and update `plugins/common/oc-reports/scripts/devmap.json` in the marketplace source.

## Task 1 — Select the in-window tickets (Jira, direct REST)

Run `<SCRIPTS>/jira_fetch_dates.py` with `--since` = the cutoff, so it selects tickets dated on/after the cutoff plus their parents and full sub-task lists:

```bash
python "<SCRIPTS>/jira_fetch_dates.py" --since [SINCE] --until [UNTIL] --project [PROJECT]   --out "<SCRATCHPAD>/issues.json"
```

It fetches `customfield_10745` (AI metrics), `fixVersions`, `status`, `resolutiondate`, `parent`, etc., stamps each ticket with its date from the status changelog (`fields.testDate` + `fields.dateSrc`), and writes `{issues:{nodes:[…]}}` keyed by numeric `id` (the aggregator joins Tempo by id). `customfield_10745` records are keyed `domain/accountId/name`; the aggregator extracts the accountIds that authored a record on each issue to classify worklogs AI vs non-AI.

## Task 2 — Fetch Tempo worklogs (per-user, all-time, cached)

Run `<SCRIPTS>/fetch_tempo_users.py` against `devmap.json`. Because a selected ticket's worklogs may pre-date the window, fetch **all-time** (so per-ticket totals match Jira's `aggregatetimespent`); the aggregator windows by ticket date. Use the persistent `--cache` so only the recent ~45 days re-fetch each run.

```bash
python "<SCRIPTS>/fetch_tempo_users.py" --devmap "<SCRIPTS>/devmap.json"   --from 2010-01-01 --to [UNTIL-1day] --cache "$HOME/.claude/oc-time-report/tempo_cache.json"   --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt" --dates-out "<SCRATCHPAD>/wdates.json"
```

(The cache is shared with `/oc-reports:oc-time-report`; `wdates.json` — the last worklog date per issue — is the date fallback for tickets with no test/post-dev transition.) It prints a per-developer worklog count to stderr; if Tempo returns nothing, tell the user and stop.

## Task 3 — Aggregate & render

Run `<SCRIPTS>/noai_report.py` (set `PYTHONIOENCODING=utf-8` on Windows so accented names print cleanly):

```bash
python "<SCRIPTS>/noai_report.py" --issues "<SCRATCHPAD>/issues.json" --tempo "<SCRATCHPAD>/tempo.json"   --devmap "<SCRIPTS>/devmap.json" --dates "<SCRATCHPAD>/wdates.json" --cutoff [SINCE] --project [PROJECT]   --out "./docs/noai-report-[TODAY]-[SINCE]-[UNTIL].html"
```

It prints the unit count and the status distribution to stderr (the five in-scope statuses are marked) — report the HTML path to the user and that they can open it in a browser (Windows: `start "" "<path>"`).

## Notes & limitations

- **Unit = ticket × dev area.** A ticket worked by two areas is counted under each; "% AI" is therefore a per-area adoption rate, and a no-AI ticket appears in Details under each area that worked it with no AI.
- **Sub-bugs are their own rows** (not rolled under the US); **non-bug sub-tasks roll up** into their parent US. **Overhead is excluded.**
- **Cutoff applies to the whole report** (Totals and Details), so the % AI reflects the AI-era only.
- **Shared data with `/oc-reports:oc-time-report`.** Same `jira_fetch_dates.py`, `fetch_tempo_users.py` (and Tempo cache) and roster — only the aggregation differs. If both are run in one session, the `issues.json`/`tempo.json` can be reused (but note the time report fetches from its own `--since`, which may be earlier).
- **Read-only** — never writes to Jira, Tempo or git.

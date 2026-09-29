---
name: oc-time-report
description: Produce an estimation-vs-logged-hours report over a period, independent of the AI-usage JSON. Tempo-worklog driven and TICKET-based with PER-AREA columns: tickets are selected by their date (resolutiondate, else updated) in the window, and every worklog on a selected ticket counts (all-time, so per-ticket totals match Jira's aggregatetimespent). One row per ticket, a column group per area (Backend/Frontend/QA) giving that area's main developer, Architect & Dev-lead estimates, logged & sub-bug hours, AI flag, two time gains (with/without sub-bugs) and sub-bug count; a single Arch-gain B/F/Q column (considering bugs) right after the Final flag; and closing Overhead d / Overhead % (its share of the ticket's total logged) / Overhead people / Total log d columns. Overhead people (Architect/PO/DevOps/Consultant/management) never count as an area developer — their hours go to the Overhead bucket, itemised per person with hours. Totals-by-area (shown in days) add a % Logged share column. Also writes a second finished-User-Story per-developer summary. Prints Markdown and writes date-stamped HTML + CSV to ./docs/. Jira via direct REST (mandatory JIRA_API_TOKEN), Tempo per-user (mandatory TEMPO_API_TOKEN) — no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD,MACRD] [--out PATH] [--csv PATH]"
---

## Purpose

A team **estimation-vs-actual** report. Unlike `/oc-ai-report`, this one is **not** tied to the AI-usage JSON field — it is driven by **Tempo worklogs** and is **ticket-based with per-area columns**: one row per ticket, with a **column group for each of the three areas** (Backend / Frontend / QA), comparing each area's estimate to its actual logged time.

**Ticket selection is by DATE, not by worklog.** A ticket is in scope when its **ticket date** — `resolutiondate`, or `updated` when it has no resolution date — falls in `[--since, --until)`. Once a ticket is selected, **every worklog booked on it and its sub-issues counts** (all-time, never clipped to the window), so a ticket's total logged time matches Jira's `aggregatetimespent`.

Fixed columns per row: **Ticket · Date · Type · Fix ver · Title · Status · Final** (**Fix ver** = the ticket's Jira *Fix Version/s*, all shown; a Bug may carry several), then a single **Arch gain B/F/Q** column and a **Logged+bug B/F/Q/OH** column, then **for each area** a group of: **Main dev · A. Est d · DL. Est d · Total dev d · Logged d · Sub-bug d · AI · Arch gain (with · without bugs) · DL gain (with · without bugs) · #Sub-bugs**. Then closing columns: **Overhead d · Overhead % · Overhead people · Total log d** (all times in days; Overhead % is overhead's share of the ticket's total logged).

**Interactive HTML — Project & Fix-version filters.** The page has two picklists: a **Project filter** (distinct Jira ticket prefixes, e.g. INTRD / MACRD, plus *All*) and a **Fix version** filter (every distinct *Fix Version/s* value present, plus *All*; a Bug with several fix versions matches each of them separately). Either one **live-filters** the Totals-by-area tables and the per-ticket rows and **recomputes % Logged, the per-area figures, the Total row and the grand total** in the browser (no reload); they combine (project AND fix-version). The Totals-by-area tables carry a **Project** column (right after Area) showing the active project filter. (The CSV is left unfiltered — filter it in a spreadsheet.)

- **Arch gain B/F/Q · OH%** (right after Final) — one column with each area's **Architect gain considering sub-bugs** = `(A.Est − (Logged + Sub-bug h)) / A.Est`, labelled **B** (backend), **F** (frontend), **Q** (QA); green positive / red negative, `-` when meaningless — plus **OH%**, overhead's share of the ticket's total logged hours.
- **Logged+bug B/F/Q/OH** (right after the Arch-gain column) — the ticket's **total logged hours including sub-bug hours** for each area (B/F/Q) and the **overhead** total (OH).
- **Main dev** (per area) — the area's roster developer with the **most total work on the ticket** = non-bug logged + their own **sub-bug-fixing** hours. So a genuine bug-fixer outranks someone who only did a token review/touch on the parent. (A US worked by all three areas therefore credits three developers.)
- **Date** — the ticket's **resolutiondate** (else **updated**); tickets are **grouped by that month**.
- **Logged d** (per area) — non-bug Tempo hours booked by that area's developers. Hours booked by **overhead** people (Architect / PO / DevOps / Consultant / management — roster area `overhead`) are moved out of the areas into the **Overhead d** bucket instead (so per-area numbers reflect real area development).
- **Sub-bug h / #Sub-bugs** — hours that area's developers logged fixing the ticket's child Bug/Sub-bug sub-issues, and the count of such sub-bugs they worked on (attributed by the **fixer's area**, so nothing is lost when a sub-bug has no component).
- **Total dev d** (per area) = Logged d + Sub-bug d.
- **A. Est d** (Architect) — **strictly** the area's per-area Architect estimate custom field (days ×8): `customfield_10157` (back), `customfield_10158` (front), `customfield_10189` (QA). There is **no** fallback to the ticket's Original Estimate (that field is the DL estimate); a ticket with no per-area Architect estimate contributes 0. A tiny placeholder (below 0.5 h, e.g. a 0.01-day value) is treated as 0. **DL. Est d** (Dev-lead) — the ticket's **Original Estimate** (`timeoriginalestimate`): a US sums that area's child sub-task estimates (sub-bugs excluded), a Bug/Enabler uses the ticket's own estimate.
- **Arch gain / DL gain** (per area group) — `(Est − (Logged+Sub-bug h))/Est` **with** bugs, then `(Est − Logged)/Est` **without** bugs. A gain shows as **`-`** when meaningless (placeholder estimate ≤0.5h, no logged time, magnitude beyond ±1000%); green positive / red negative in the HTML.
- **AI** (per area) — a badge when that area has an AI-metrics record on the ticket (or a same-area sub-task carries the field). Totals show **AI-assisted** = AI-assisted tickets / total tickets per area.
- **Status / Final** — the ticket's Jira status and a **T** flag when terminal for its type (Bug: Done/Invalid; US: Ready for Sprint review / Need documentation / Ready for release / Released; others: Done).
- **Overhead d** — logged hours from overhead people (Architect / PO / DevOps / Consultant / management) on the ticket. **Overhead people** — those contributors named with their individual hours (e.g. `Adil El Jaouhari 12.0h, Stéphane Chambrin 3.0h`). **Total log d** — logged across all groups (areas + Overhead).

**Totals by area** — one row per area (Backend / Frontend / QA), then an **Overhead** row and a **Total** row, in **days** (1 d = 8 h). Column order: **Area · Project · Tickets · A. Est d · DL. Est d · Total dev d · % Logged · Logged d · Sub-bug d · % Sub-bug · Arch gain (all · noAI · AI) · DL gain · Sub-bugs**. **% Logged** (right after Total dev d) is each area's / Overhead's share of the total logged; **% Sub-bug** (right after Sub-bug d) is the sub-bug share of the area's own logged (sub-bug ÷ (logged + sub-bug)). The **Arch gain** cell shows **three with-bug gains** — for **all** tickets, the **no-AI** ones and the **AI** ones — each with its ticket count in ( ); **DL gain** is a single with-bug gain (both drop the "without bugs" variant here). In **every aggregate** (Totals-by-area, the per-month Totals, and the Arch-gain-by-month table) the gain is computed over **only the tickets that carry that estimate** — an unestimated ticket's logged hours are excluded from the gain (though the A.Est/Logged/Sub-bug columns still show the full sums) — which keeps an aggregate gain in the same range as the per-ticket gains. (The Markdown Totals keep a single row per area with the with/without-bug gains.)

**Arch gain by month (HTML).** Immediately after the Totals-by-area table, each tab shows an **Arch gain by month** summary: rows are months, columns are **Backend · Backend AI · Frontend · Frontend AI · QA · QA AI · Overhead**, and each cell is that group's **Architect gain (with sub-bugs)** with the **ticket count in ( )** (an empty group shows –; **Overhead** has no estimate, so it shows its **share of that month's total logged hours** — overhead logged ÷ all logged that month — with its ticket count). It recomputes live under the project filter.

Output: a compact **Markdown** printout (Totals by area overall + by month, then a condensed per-ticket table grouped by month), plus a styled **HTML** file (the full wide per-area matrix, split into **five tabs** — All · User Stories (All) · User Stories (Final) · Bugs (Final) · Bugs and Others — each with Totals-by-area overall + expandable per-month, and the per-ticket matrix grouped by month) and a **CSV** (the full matrix flattened), all date-stamped in `./docs/`. Users/developers are ordered **by area, then name**.

**Second report — finished-US per-developer summary.** The same run also writes `time-report-<TODAY>-<SINCE>-<UNTIL>-us-summary.html` and `…-us-summary.csv` (derived from `--out`/`--csv` by inserting `-us-summary`). It considers **only User Stories in a final status**, credited to **each area's main developer** (up to three per US). The HTML has **two tabs**: **By month** (date → user: overall AI-true / AI-false tables plus an expandable per-month block) and **By developer** (user → date: each developer, ordered by area then name, expands to two month-by-month tables — AI-assisted true / false — of their finished US). Dev-table columns: **Developer · Area · US (final) · Avg sub-bugs / US · Sum A. Est d · Sum logged d · Sum sub-bug d · Sum total d · Gain (with sub-bugs) · Gain (no sub-bugs)** (hour sums in days), each ending with a **Total** row. The CSV carries a leading **Month** and **AI assisted** column.

## Access

Both tokens are **mandatory** and read from the environment (never passed on the command line). If either is missing, tell the user how to create it and **stop**.

- **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token from *id.atlassian.com → Security → API tokens*. All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `jira_fetch_dates.py` below. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql` in this report** — it force-includes each issue's full `description` and caps at ~5 issues/call with no cursor. Direct REST honours the `fields` list (excludes `description`), returns 100/page and paginates via `nextPageToken`.
- **`TEMPO_API_TOKEN`** (each developer's own token, *Tempo → Settings → API keys*, worklog **read** scope) — logged hours are the whole point. Fetched **per-user** (`/worklogs/user/{accountId}`), which has org-wide visibility across all areas.

## Arguments

Parse `$ARGUMENTS` — all optional. Bare `/oc-time-report` = **last 30 days**, projects **INTRD and MACRD** — and, because **PRT730 is a Protected project**, **ask the user whether to include PRT730** before running (see the `--project` note below).

- `--since YYYY-MM-DD` — start (inclusive), matched against each ticket's date (resolutiondate, else updated). Default: 30 days before `--until`.
- `--until YYYY-MM-DD` — end (exclusive). Default: tomorrow.
- `--project KEY[,KEY...]` — Jira project(s), comma-separated. Backend work is raised in `INTRD` (core *and* overlay) and `MACRD` (MACO R&D / overlay), so both are always in scope. **When the user passes `--project` explicitly, honour it verbatim and do NOT ask anything.** **When `--project` is NOT passed, the base default is `INTRD,MACRD`, and — because `PRT730` (Protected - 730) is a Protected project — you MUST ask the user before report generation whether PRT730 should be included** (e.g. "PRT730 is a Protected project — include it in this report? (yes/no)"). On **yes**, run with `--project INTRD,MACRD,PRT730`; on **no**, run with `--project INTRD,MACRD`. Echo the resolved project list back with the window.
- `--out PATH` — HTML output. Default `./docs/time-report-<TODAY>-<SINCE>-<UNTIL>.html` (run date, then window start and end).
- `--csv PATH` — CSV output. Default `./docs/time-report-<TODAY>-<SINCE>-<UNTIL>.csv`.

Compute dates with `date -u +%Y-%m-%d` etc.; echo the resolved window back to the user.

## Developer roster (embedded)

The roster is **embedded** below and keyed by Jira **accountId** — write it verbatim to `<SCRATCHPAD>/devmap.json` (accountIds are stable, so no per-run name resolution is needed). Schema: `{ "<accountId>": {"name", "area", "role", "active"} }`, where **area ∈ `backend` | `frontend` | `qa` | `overhead`** and `role` is the person's function (BACK / FRONT / QA / ARCHI / PO / DEVOPS / CONSULTANT / NONE).

**Overhead rule.** Everyone whose role is **ARCHI, PO, DEVOPS, CONSULTANT** (or NONE — e.g. Vincent Naudion, Jean-Bertrand Rouquette) has **area `overhead`**: their logged hours never land in an area column and never make them an area's main developer — all of it goes to the ticket's **Overhead** bucket (shown per person with hours) and they are absent from the finished-US per-developer summary. Only `backend` / `frontend` / `qa` people are area developers.

**If the roster changes** (someone joins/leaves or is mis-mapped), resolve the person via the **full user directory** — `GET /rest/api/3/users/search?startAt=&maxResults=200` (Basic auth `JIRA_EMAIL:JIRA_API_TOKEN`), which lists **all** users incl. deactivated and exposes their `@opencellsoft.com` emails — then add/update their entry here (match by `firstname.lastname@opencellsoft.com`). Do **not** rely on `/user/search?query=` (it misses deactivated accounts and mis-matches).

```json
{
"5e62049035753d0cdaaaceee": {
"name": "Abdelhadi Nasseh",
"area": "backend",
"role": "BACK",
"active": true
},
"63160f1d3778a7aadf197540": {
"name": "Abdellah Slimani",
"area": "overhead",
"role": "CONSULTANT",
"active": true
},
"5cb069776f37be21fe5cd9d6": {
"name": "Abdellatif Bari",
"area": "backend",
"role": "BACK",
"active": true
},
"5e620492cf54800ce3a05791": {
"name": "Abdelmounaim Akadid",
"area": "backend",
"role": "BACK",
"active": true
},
"63369fa788ed2ebef97cddfb": {
"name": "Adil El Jaouhari",
"area": "overhead",
"role": "ARCHI",
"active": true
},
"63369fa8140ba0bf651c59b2": {
"name": "Aissam BAHARI",
"area": "frontend",
"role": "FRONT",
"active": true
},
"5c35d1059760f569b627c08d": {
"name": "Amine Tazi",
"area": "backend",
"role": "BACK",
"active": true
},
"62b044340c77011bdfdb349e": {
"name": "Anas Rouaguebe",
"area": "backend",
"role": "BACK",
"active": true
},
"5dbb097eb6788b0c37755176": {
"name": "Andrius Karpavičius",
"area": "backend",
"role": "BACK",
"active": true
},
"557058:1c9100d3-2928-4e82-b007-03d9e6b8711e": {
"name": "Antoine Michéa",
"area": "overhead",
"role": "DEVOPS",
"active": true
},
"5f156ae707efc40028457d87": {
"name": "Brahim Aachiq",
"area": "qa",
"role": "QA",
"active": true
},
"61adcdd53618cd006f2e513f": {
"name": "Chamseddine Chrifa",
"area": "overhead",
"role": "DEVOPS",
"active": true
},
"5cb463decef84c118d766129": {
"name": "Elhoussine Znibar",
"area": "overhead",
"role": "ARCHI",
"active": true
},
"6294da839bc7150068ccdbcd": {
"name": "Emmanuel Pierre",
"area": "overhead",
"role": "PO",
"active": false
},
"5e1dc7362538f60cab4be626": {
"name": "Florence Delille",
"area": "overhead",
"role": "CONSULTANT",
"active": true
},
"5c375ec136647b5b9101bcac": {
"name": "Hatim Oudad",
"area": "backend",
"role": "BACK",
"active": true
},
"5f841dd256eec00076581403": {
"name": "Jérôme Ngo",
"area": "overhead",
"role": "CONSULTANT",
"active": true
},
"5f203a95ef11df00258c0743": {
"name": "Mbarek Ait-Yaazza",
"area": "backend",
"role": "BACK",
"active": true
},
"631075e8b433b060db55baba": {
"name": "Mehdi Bourras",
"area": "backend",
"role": "BACK",
"active": true
},
"60d01ea55c64b10071543c4f": {
"name": "Mohamed Amine Houssa",
"area": "frontend",
"role": "FRONT",
"active": true
},
"5c35cef68ee3ae5b8b0746ec": {
"name": "Mohamed Amtiou",
"area": "qa",
"role": "QA",
"active": true
},
"5f1eff30b7a35e002a5063b1": {
"name": "Mohamed El Azouzzi",
"area": "backend",
"role": "BACK",
"active": true
},
"5ef5c13914f60e0ac1c9b049": {
"name": "Mohamed Hamidi",
"area": "frontend",
"role": "FRONT",
"active": true
},
"5fd0b645fee79300751a7487": {
"name": "Mohamed Stitane",
"area": "backend",
"role": "BACK",
"active": true
},
"5f15a83c70b8a90025e140a6": {
"name": "Mounir Boukayoua",
"area": "backend",
"role": "BACK",
"active": true
},
"630f66116856bdd60a9ea766": {
"name": "Olivier MARTIN",
"area": "overhead",
"role": "CONSULTANT",
"active": false
},
"60d01ec9b215610069ee0e6c": {
"name": "Oussama El Idrissi",
"area": "frontend",
"role": "FRONT",
"active": false
},
"5f2032a7f78bea0016478dab": {
"name": "Rachid Aityaazza",
"area": "overhead",
"role": "ARCHI",
"active": true
},
"6360d863fe5ff375235b6511": {
"name": "Raja Halabi",
"area": "qa",
"role": "QA",
"active": true
},
"609bccb59b362f006977d7de": {
"name": "Raynald Bardin",
"area": "overhead",
"role": "CONSULTANT",
"active": true
},
"5bed52e5f9c8c708ecdb4d6f": {
"name": "Stéphane Chambrin",
"area": "overhead",
"role": "PO",
"active": true
},
"5fea087091bb2e0108889a79": {
"name": "Tarik Fakhouri",
"area": "backend",
"role": "BACK",
"active": true
},
"5da44c09f094440c44b9596f": {
"name": "Vladimir Morev",
"area": "frontend",
"role": "FRONT",
"active": true
},
"61d5834ba54af9006978ba16": {
"name": "Yassine Chetoui",
"area": "overhead",
"role": "PO",
"active": true
},
"62f0e931a41ecbd0ba192725": {
"name": "Zakaria El Meliani",
"area": "backend",
"role": "BACK",
"active": false
},
"712020:b5101fc8-7b37-4103-a46a-03aa28677bcc": {
"name": "Coumba Diallo",
"area": "overhead",
"role": "PO",
"active": false
},
"712020:fae05cb2-52a0-48da-af7e-b6b22117e60a": {
"name": "Souhayla Msellek",
"area": "qa",
"role": "QA",
"active": true
},
"712020:1f278e2e-d260-4991-86d3-a5b960db5241": {
"name": "Ghassen Trabelsi",
"area": "overhead",
"role": "CONSULTANT",
"active": true
},
"712020:47d76bfb-8afa-4a2c-9559-f53589466845": {
"name": "thanh.nguyen",
"area": "frontend",
"role": "FRONT",
"active": false
},
"712020:1861da56-f0cd-456b-b39e-e743ce3847ac": {
"name": "trung-anh.tran",
"area": "frontend",
"role": "FRONT",
"active": false
},
"712020:1a5b97a4-782c-4ecc-bb95-785913e1777c": {
"name": "Yasmine Mehidi",
"area": "overhead",
"role": "PO",
"active": false
},
"5d3592e9825be60c3a4e7c6d": {
"name": "Abdelkader Bouazza",
"area": "backend",
"role": "BACK",
"active": false
},
"712020:5503a1fc-031c-4a8a-9847-f26355178b62": {
"name": "cong.phan-huy",
"area": "frontend",
"role": "FRONT",
"active": false
},
"712020:cd53d6f5-8104-430f-8242-b130c01349af": {
"name": "Adem Chrifa",
"area": "overhead",
"role": "DEVOPS",
"active": true
},
"5e26ca98c55f580c9fc945c3": {
"name": "Maria Ait-Brahim",
"area": "qa",
"role": "QA",
"active": false
},
"712020:5d3a425c-2362-4fdc-8fa2-3846904b21b3": {
"name": "Ahmed Bahri",
"area": "backend",
"role": "BACK",
"active": false
},
"712020:d07079fa-1364-43f6-8a71-236e9635e960": {
"name": "Mohamed Moindjie",
"area": "backend",
"role": "BACK",
"active": false
},
"712020:2659f143-12ce-44f7-9b18-310091b6aa6a": {
"name": "Fatima-Ezzahra Toulali",
"area": "qa",
"role": "QA",
"active": false
},
"5efd904574183a0bb3709bd4": {
"name": "Jean-Bertrand Rouquette",
"area": "overhead",
"role": "NONE",
"active": true
},
"5a38e6265a6ecc387ffb966c": {
"name": "Vincent Naudion",
"area": "overhead",
"role": "NONE",
"active": true
},
"712020:8bdf0412-9821-4712-be40-4255b8a9bc93": {
"name": "Nolwenn Nizard",
"area": "overhead",
"role": "PO",
"active": false
},
"712020:f9cbce79-0b38-4e13-8284-a80872729dd5": {
"name": "Ronan Le Borgne",
"area": "backend",
"role": "BACK",
"active": true
},
"712020:56839b2d-fd0e-48e3-92e5-009cb9d1629d": {
"name": "charlotte.thomas",
"area": "overhead",
"role": "PO",
"active": false
},
"5f4cfbecfcaf93003b30bcb8": {
"name": "Zakaria Bariki",
"area": "backend",
"role": "BACK",
"active": true
}
}
```

## Task 1 — Write the roster

Write the embedded `devmap.json` (above) to `<SCRATCHPAD>/devmap.json` verbatim. (Only re-resolve names via the full directory if the team has changed since this was captured.)

## Task 2 — Select the in-window tickets (Jira, direct REST)

Rows are at **parent-ticket** granularity and selected by **ticket date**. Write `jira_fetch_dates.py` (below) to scratchpad and run it — it selects tickets whose `resolutiondate` (else, for unresolved tickets, `updated`) is in `[--since, --until)`, then adds their parents and the parents' full sub-task lists, and writes `issues.json`:

```bash
python "<SCRATCHPAD>/jira_fetch_dates.py" --since [SINCE] --until [UNTIL] --project [PROJECT]   --out "<SCRATCHPAD>/issues.json"
```

It requests fields `["summary","issuetype","status","components","timeoriginalestimate","timespent","parent","resolutiondate","updated","aggregatetimespent","customfield_10157","customfield_10158","customfield_10189","customfield_10745"]` and writes `{issues:{nodes:[…]}}` keyed with the numeric `id` (the aggregator joins Tempo by id).

- `status` drives the **Status** column and the **Final** flag: a ticket is *final* when its Jira status (case-insensitive) is terminal for its type — **Bug**: Done / Invalid; **US**: Ready for Sprint review / Need documentation / Ready for release / Released; **any other type**: Done. The finished-User-Story summary counts only US with Final = true.
- `customfield_10745` is the **"AI metrics"** field: its presence marks an area as **developed with AI assistance** (per-ticket **AI** badge; aggregated as **AI-assisted**); an area is flagged when the ticket carries a record for that domain, or a same-area sub-task carries the field.
- Estimate custom fields are `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate* (days).

## Task 3 — Fetch Tempo worklogs (per-user, all-time, **cached**)

Fetch **per-user** (not the bulk `/worklogs` endpoint — that only surfaces some authors). Write `fetch_tempo_users.py` (below) to scratchpad and run it against `devmap.json`. Because a selected ticket's worklogs may pre-date the window, the report needs **all-time** worklogs (so per-ticket totals match Jira's `aggregatetimespent`); the aggregator does the ticket-date windowing.

**Use the persistent cache** (`--cache`) so this step is fast. Worklogs can't be entered more than ~a month back, so historical Tempo data is **immutable**: the cache stores month-bucketed worklogs, and each run only re-fetches the recent ~45 days (`--refresh-days`, the mutable window) and reuses cached older months. The **first** run (cold cache) does the full all-time pull from `--from 2010-01-01` (minutes); **subsequent** runs finish in seconds.

```bash
python "<SCRATCHPAD>/fetch_tempo_users.py" --devmap "<SCRATCHPAD>/devmap.json"   --from 2010-01-01 --to [UNTIL-1day] --cache "$HOME/.claude/oc-time-report/tempo_cache.json"   --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt" --dates-out "<SCRATCHPAD>/wdates.json"
```

It writes `tempo.json` = `{ "<issueId>": { "<accountId>": seconds } }` and `wdates.json` = `{ "<issueId>": "<latest worklog date>" }` (and a `worklog_ids.txt` that the date-driven flow does not need), and maintains the month-bucketed cache at `--cache` (kept **outside** the session scratchpad — `$HOME/.claude/oc-time-report/tempo_cache.json` — so it persists across runs). It prints a per-developer worklog count to stderr; report which developers had worklogs. If Tempo returns nothing, tell the user and stop. (Most logged time is cross-project; the aggregator keeps only tickets in the requested projects.)

## Task 4 — Aggregate & render

Write `time_report.py` (below) and run it:

```bash
python "<SCRATCHPAD>/time_report.py" --tempo "<SCRATCHPAD>/tempo.json" --issues "<SCRATCHPAD>/issues.json"   --devmap "<SCRATCHPAD>/devmap.json" --dates "<SCRATCHPAD>/wdates.json" --since [SINCE] --until [UNTIL] --project [PROJECT]   --md "<SCRATCHPAD>/report.md" --out "./docs/time-report-[TODAY]-[SINCE]-[UNTIL].html" --csv "./docs/time-report-[TODAY]-[SINCE]-[UNTIL].csv"
```

If the aggregator prints an **UNKNOWN worklog authors** warning to stderr (accountIds with logged hours that are not in `devmap.json`), it also writes `unknown_authors.json`; **ask the user how those hours should be attributed before presenting the report**, then add the resolved people to `devmap.json` and re-run. (Set `PYTHONIOENCODING=utf-8` when running so accented developer names print cleanly on Windows.)

Show the Markdown (`report.md`) to the user and report the HTML + CSV paths, **plus the second report** it also writes — a finished-User-Story per-developer summary at `./docs/time-report-[TODAY]-[SINCE]-[UNTIL]-us-summary.{html,csv}`.

### `jira_fetch_dates.py`

```python
#!/usr/bin/env python3
"""Select report tickets by DATE (resolutiondate, else updated) via Jira Cloud REST enhanced JQL,
then fetch their parents + all sub-issues. Writes issues.json. Auth: JIRA_EMAIL:JIRA_API_TOKEN."""
import os, sys, json, time, base64, argparse, urllib.request, urllib.error
BASE="https://opencellsoft.atlassian.net"
EMAIL=os.environ.get("JIRA_EMAIL") or "andrius.karpavicius@opencellsoft.com"
TOK=os.environ["JIRA_API_TOKEN"]
AUTH=base64.b64encode(f"{EMAIL}:{TOK}".encode()).decode()
FIELDS=["summary","issuetype","status","components","timeoriginalestimate","timespent","parent",
        "resolutiondate","updated","aggregatetimespent","fixVersions",
        "customfield_10157","customfield_10158","customfield_10189","customfield_10745"]

def post(path, body):
    for attempt in range(5):
        req=urllib.request.Request(BASE+path, data=json.dumps(body).encode(),
            headers={"Authorization":f"Basic {AUTH}","Accept":"application/json","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code in (429,503): time.sleep(2*(attempt+1)); continue
            sys.stderr.write(f"HTTP {ex.code}: {ex.read()[:200]}\n"); raise
    raise RuntimeError("retries exhausted")

def fetch_jql(jql):
    out=[]; token=None
    while True:
        body={"jql":jql,"fields":FIELDS,"maxResults":100}
        if token: body["nextPageToken"]=token
        d=post("/rest/api/3/search/jql", body)
        out+=d.get("issues") or []
        if d.get("isLast") or not d.get("nextPageToken"): break
        token=d["nextPageToken"]
    return out

def slim(n):
    f=n.get("fields") or {}; p=f.get("parent") or {}
    return {"id":n["id"],"key":n["key"],"fields":{
        "summary":f.get("summary"),"issuetype":{"name":(f.get("issuetype") or {}).get("name")},
        "status":{"name":(f.get("status") or {}).get("name")},"components":f.get("components") or [],
        "timeoriginalestimate":f.get("timeoriginalestimate"),"timespent":f.get("timespent"),
        "resolutiondate":f.get("resolutiondate"),"updated":f.get("updated"),
        "aggregatetimespent":f.get("aggregatetimespent"),
        "fixVersions":[v.get("name") for v in (f.get("fixVersions") or []) if v.get("name")],
        "parent":{"key":p.get("key")} if p.get("key") else None,
        "customfield_10157":f.get("customfield_10157"),"customfield_10158":f.get("customfield_10158"),
        "customfield_10189":f.get("customfield_10189"),"customfield_10745":f.get("customfield_10745")}}

def batched(seq,n):
    for i in range(0,len(seq),n): yield seq[i:i+n]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--since", required=True); ap.add_argument("--until", required=True)
    ap.add_argument("--project", default="INTRD,MACRD,PRT730"); ap.add_argument("--out", required=True)
    a=ap.parse_args()
    PROJS=[x.strip() for x in a.project.split(",") if x.strip()]; PSTR=", ".join(PROJS)
    def in_scope(k): return any(str(k).startswith(q+"-") for q in PROJS)
    # Pass A: tickets whose ticket-date (resolutiondate, else updated) is in the window
    jqlA=f'project in ({PSTR}) AND resolutiondate >= "{a.since}" AND resolutiondate < "{a.until}"'
    jqlB=f'project in ({PSTR}) AND resolution is EMPTY AND updated >= "{a.since}" AND updated < "{a.until}"'
    by_id={}
    for n in fetch_jql(jqlA)+fetch_jql(jqlB): by_id[str(n["id"])]=slim(n)
    sys.stderr.write(f"Pass A/B (date-selected): {len(by_id)} issues\n")
    by_key={v["key"]:v for v in by_id.values()}
    # Pass C: parents of any selected sub-issue not already present (so a subtask maps to its row)
    pkeys=sorted({(v["fields"].get("parent") or {}).get("key") for v in list(by_id.values())
                  if (v["fields"].get("parent") or {}).get("key") and (v["fields"]["parent"]["key"] not in by_key)})
    for b in batched(pkeys,100):
        for n in fetch_jql("key in ("+",".join(b)+")"):
            s=slim(n); by_id[str(n["id"])]=s; by_key[s["key"]]=s
    sys.stderr.write(f"Pass C (parents): +{len(pkeys)}, total {len(by_id)}\n")
    # Pass D: all sub-issues of the in-scope Story/Enabler parents (DL estimate, sub-bugs, roll-up)
    story_parents=sorted({v["key"] for v in list(by_id.values())
        if in_scope(v["key"]) and (v["fields"]["issuetype"]["name"] or "") in ("Story","Enabler")})
    seen=set(by_id)
    for i,b in enumerate(batched(story_parents,60)):
        for n in fetch_jql("parent in ("+",".join(b)+")"):
            if str(n["id"]) not in seen: s=slim(n); by_id[str(n["id"])]=s
        if i%10==0: sys.stderr.write(f"  subtask batch {i}: total {len(by_id)}\n")
    sys.stderr.write(f"Pass D done: total {len(by_id)} nodes\n")
    json.dump({"issues":{"nodes":list(by_id.values())}}, open(a.out,"w",encoding="utf-8"))
    inp=sum(1 for v in by_id.values() if in_scope(v["key"]))
    sys.stderr.write(f"WROTE {a.out}: {len(by_id)} total, {inp} in {PSTR}\n")

if __name__=="__main__": main()
```

### `fetch_tempo_users.py`

```python
import json, os, sys, urllib.request, urllib.error, urllib.parse, datetime
BASE = "https://api.tempo.io/4"

def fetch_user(acc, tok, frm, to):
    """Return ([(issueId, startDate, seconds), ...], http_status) for one user's worklogs in [frm, to]."""
    out = []
    url = f"{BASE}/worklogs/user/{urllib.parse.quote(acc, safe='')}?from={frm}&to={to}&limit=1000"
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"  {acc}: HTTP {ex.code}\n"); return out, ex.code
        for w in data.get("results") or []:
            iid = str((w.get("issue") or {}).get("id"))
            if iid and iid != "None":
                out.append((iid, w.get("startDate") or "", w.get("timeSpentSeconds") or 0))
        url = (data.get("metadata") or {}).get("next")
    return out, 200

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--devmap", required=True); ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True); ap.add_argument("--out", required=True); ap.add_argument("--ids-out", required=True)
    ap.add_argument("--dates-out")               # optional: {issueId: latest worklog date}
    ap.add_argument("--cache")                    # persistent month-bucketed cache for incremental refresh
    ap.add_argument("--refresh-days", type=int, default=45)  # re-fetch this many days back (must exceed the ~1-month log window)
    a = ap.parse_args()
    tok = os.environ.get("TEMPO_API_TOKEN")
    if not tok: sys.stderr.write("no token\n"); sys.exit(1)
    dev = json.load(open(a.devmap, encoding="utf-8"))

    # Cache: {"buckets": {issueId: {accId: {"YYYY-MM": secs}}}, "lastDate": {issueId: "YYYY-MM-DD"}}.
    # Worklogs older than ~1 month are immutable (they can't be logged/edited that far back), so only the
    # recent months need re-fetching; older months are served straight from the cache.
    cache = {"buckets": {}, "lastDate": {}}
    if a.cache and os.path.exists(a.cache):
        try: cache = json.load(open(a.cache, encoding="utf-8"))
        except Exception: cache = {"buckets": {}, "lastDate": {}}
    buckets = cache.setdefault("buckets", {}); lastDate = cache.setdefault("lastDate", {})

    if a.cache and buckets:   # incremental: refresh only the recent (mutable) months
        cutoff = datetime.date.today() - datetime.timedelta(days=a.refresh_days)
        cutoff_month = cutoff.strftime("%Y-%m")
        eff_from = cutoff.replace(day=1).strftime("%Y-%m-%d")
        for accs in buckets.values():                      # drop recent months so the fresh pull fully replaces them
            for months in accs.values():
                for mk in [m for m in months if m >= cutoff_month]: del months[mk]
        sys.stderr.write(f"cache hit ({len(buckets)} issues): refreshing months >= {cutoff_month} (from {eff_from})\n")
    else:                     # cold cache: full fetch from --from
        eff_from = a.frm
        sys.stderr.write(f"no cache: full fetch from {eff_from}\n")

    for acc, info in dev.items():
        wls, code = fetch_user(acc, tok, eff_from, a.to)
        for iid, sd, sec in wls:
            mk = sd[:7] if sd else "0000-00"
            buckets.setdefault(iid, {}).setdefault(acc, {})
            buckets[iid][acc][mk] = buckets[iid][acc].get(mk, 0) + sec
            if sd and sd > lastDate.get(iid, ""): lastDate[iid] = sd
        sys.stderr.write(f"{info['area']:8} {info['name']:26} {len(wls):5} worklogs\n")

    if a.cache:
        os.makedirs(os.path.dirname(os.path.abspath(a.cache)) or ".", exist_ok=True)
        json.dump(cache, open(a.cache, "w"))
    # flatten month buckets -> tempo {issueId: {accId: secs}} (dropping issues/accounts that netted to 0)
    tempo = {}
    for iid, accs in buckets.items():
        for acc, months in accs.items():
            s = sum(months.values())
            if s: tempo.setdefault(iid, {})[acc] = s
    json.dump(tempo, open(a.out, "w"))
    open(a.ids_out, "w").write(",".join(tempo.keys()))
    if a.dates_out: json.dump(lastDate, open(a.dates_out, "w"))
    sys.stderr.write(f"TOTAL distinct worklogged issues: {len(tempo)}\n")

if __name__ == "__main__": main()
```

### `time_report.py`

```python
#!/usr/bin/env python3
"""Estimation-vs-logged report, TICKET-based with PER-AREA columns. One row per ticket; each
of the three areas (backend / frontend / qa) gets its own column group: main developer,
Architect & Dev-lead estimate, total dev h, logged h, sub-bug h, AI, Arch/DL gains (without /
with sub-bugs) and sub-bug count. Logged hours are attributed by each developer's roster area;
a multi-role developer (Architect / PR-review) whose hours are NOT the main dev of their area on
the ticket go to a separate Architect/PR/mgmt logged-hours column. A Total-across-groups logged
column closes each row. Area sub-bug hours/counts are by the sub-bug's own component."""
import argparse, json, re, html, csv, os
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
AREA_LABEL = {"backend": "Backend", "frontend": "Frontend", "qa": "QA"}
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8
BUG_TYPES = {"bug", "sub-bug"}
SUBTASK_TYPES = {"sub-task", "sub-bug", "sub test execution", "sub-test execution"}
TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Bug", "enabler": "Enabler"}
FINAL_STATUS = {
    "Bug": {"done", "invalid"},
    "US": {"ready for sprint review", "need documentation", "ready for release", "released"},
}
DEFAULT_FINAL = {"done"}
GAIN_CAP = 1000
EST_MIN = 0.5

def nodes(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        if "issues" in data:
            iss = data["issues"]; return (iss.get("nodes", []) if isinstance(iss, dict) else iss) or []
        if "nodes" in data: return data["nodes"] or []
        vals = list(data.values())
        if vals and isinstance(vals[0], dict) and ("fields" in vals[0] or "key" in vals[0]): return vals
    return []

def hours(s): return round((s or 0) / 3600, 1)
def is_bug(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES
def is_subtask(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in SUBTASK_TYPES
def ticket_type(f):
    n = (f.get("issuetype") or {}).get("name") or ""
    return TYPE_MAP.get(n.lower(), n or "?")
def status_of(f): return ((f.get("status") or {}).get("name") or "").strip()
def is_final(ttype, status): return (status or "").strip().lower() in FINAL_STATUS.get(ttype, DEFAULT_FINAL)
def ticket_date(f):
    """The ticket's date for range-filtering & grouping: resolutiondate, else updated. YYYY-MM-DD."""
    d = f.get("resolutiondate") or f.get("updated") or ""
    return d[:10]

def area_of(f):
    for c in f.get("components") or []:
        ar = COMP_AREA.get((c.get("name") or "").strip().lower())
        if ar: return ar
    m = _TAG.search(f.get("summary") or "")
    if m: return {"back": "backend", "front": "frontend", "test": "qa"}[m.group(1).lower()]
    return None

def record_domains(f):
    """Areas that carry an AI-metrics record on this ticket (customfield_10745, opencell.ai-usage JSON)."""
    raw = f.get("customfield_10745"); doms = set()
    if isinstance(raw, dict):
        txt = []
        def w(n):
            if isinstance(n, dict):
                if n.get("type") == "text": txt.append(n.get("text", ""))
                for c in n.get("content") or []: w(c)
            elif isinstance(n, list):
                for c in n: w(c)
        w(raw); raw = "".join(txt)
    if isinstance(raw, str) and raw.strip():
        try: doc = json.loads(raw)
        except json.JSONDecodeError: doc = None
        for rk in ((doc or {}).get("records") or {}):
            p = rk.split("/", 2)
            if p and p[0] in AREAS: doms.add(p[0])
    return doms

# ---- gains ----
def gain_pct(est, logged):
    if not est or est < EST_MIN or not logged or logged <= 0: return None
    return round((est - logged) / est * 100)
def gain_str(g): return "-" if (g is None or abs(g) > GAIN_CAP) else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_two(est, logged, bug):  # WITH / WITHOUT sub-bug hours
    return f"{gain_str(gain_pct(est, logged + bug))} / {gain_str(gain_pct(est, logged))}"
def gain_cls(g): return "" if (g is None or abs(g) > GAIN_CAP) else ("pos" if g >= 0 else "neg")
def gain_span(g):
    c = gain_cls(g); return f'<span class="{c}">{gain_str(g)}</span>' if c else gain_str(g)
def gain_two_html(est, logged, bug):  # WITH / WITHOUT sub-bug hours
    return f"{gain_span(gain_pct(est, logged + bug))} / {gain_span(gain_pct(est, logged))}"
def gain_cell(est, logged):
    g = gain_pct(est, logged); return "-" if (g is None or abs(g) > GAIN_CAP) else g
def e(x): return html.escape(str(x))
def days(h): return round((h or 0) / DAY_HOURS, 1)   # totals shown in days (1 d = 8 h)

def build_ticket_rows(all_nodes, tempo, devmap, project, wdates=None, since=None, until=None):
    """Rows are PARENT tickets whose ticket date (resolutiondate, else updated) is in
    [since, until); every worklog on the ticket + its sub-issues counts (all-time, not
    date-clipped). unknown = accountIds seen in worklogs but absent from devmap."""
    wdates = wdates or {}
    unknown = defaultdict(float)
    by_id = {str(n.get("id")): n for n in all_nodes}
    by_key = {n.get("key"): n for n in all_nodes}
    children = defaultdict(list)
    for n in all_nodes:
        pk = ((n.get("fields") or {}).get("parent") or {}).get("key")
        if pk: children[pk].append(n)

    # roll Tempo up to the parent ticket: per-dev non-bug logged secs, per-sub-bug secs+area,
    # and the ticket's latest worklog date (across its own + rolled-up sub-issue worklogs).
    tk = defaultdict(lambda: {"devLogged": defaultdict(float), "subbugs": {}, "date": ""})
    for iid, per in tempo.items():
        node = by_id.get(str(iid))
        if not node: continue
        nf = node.get("fields") or {}
        pk = (nf.get("parent") or {}).get("key")
        st = is_subtask(nf)
        tkey = pk if (st and pk and pk in by_key) else node.get("key")
        d = wdates.get(str(iid), "")
        if d and d > tk[tkey]["date"]: tk[tkey]["date"] = d
        if st and is_bug(nf):
            b = tk[tkey]["subbugs"].setdefault(str(iid), {"perdev": defaultdict(float)})
            for acc, sec in per.items():
                if acc in devmap: b["perdev"][acc] += sec
                else: unknown[acc] += sec
        else:
            for acc, sec in per.items():
                if acc in devmap: tk[tkey]["devLogged"][acc] += sec
                else: unknown[acc] += sec

    rows = []
    for tkey, agg in tk.items():
        if project and not any(str(tkey).startswith(q.strip() + "-") for q in str(project).split(",") if q.strip()): continue
        tnode = by_key.get(tkey)
        if not tnode: continue
        tf = tnode.get("fields") or {}
        if not agg["devLogged"] and not agg["subbugs"]: continue
        tdate = ticket_date(tf)                       # resolutiondate, else updated
        if since and (not tdate or tdate < since): continue
        if until and (not tdate or tdate >= until): continue
        ttype = ticket_type(tf); status = status_of(tf); final = is_final(ttype, status)
        pa = area_of(tf); rec = record_domains(tf)

        # sub-bugs attributed by the FIXER's roster area (dev-centric, like Logged h): a developer's
        # sub-bug-fixing hours count toward their area's Sub-bug h and toward being that area's main
        # dev; a sub-bug counts once per area that worked on it. (Nothing is dropped for lacking a component.)
        area_sub_h = {ar: 0.0 for ar in AREAS}; area_bug_ct = {ar: 0 for ar in AREAS}
        sub_dev = defaultdict(lambda: defaultdict(float))
        archpr_logged = 0.0; archpr_devs = {}
        for b in agg["subbugs"].values():
            touched = set()
            for acc, sec in b["perdev"].items():
                if devmap[acc]["area"] == "overhead":   # ARCHI/PO/DEVOPS/CONSULTANT -> overhead, not an area
                    archpr_logged += sec; archpr_devs[devmap[acc]["name"]] = archpr_devs.get(devmap[acc]["name"], 0.0) + sec
                    continue
                ar = devmap[acc]["area"]; area_sub_h[ar] += sec; sub_dev[ar][acc] += sec; touched.add(ar)
            for ar in touched: area_bug_ct[ar] += 1

        # main developer per area = the area's roster dev with the most TOTAL work on the ticket
        # (non-bug logged + their own sub-bug-fixing hours) — so a real bug-fixer outranks someone
        # who only did a token review/touch on the parent.
        by_area_dev = defaultdict(dict)
        for acc, sec in agg["devLogged"].items():
            if devmap[acc]["area"] == "overhead": continue   # overhead people are never an area main dev
            by_area_dev[devmap[acc]["area"]][acc] = by_area_dev[devmap[acc]["area"]].get(acc, 0) + sec
        for ar in AREAS:
            for acc, sec in sub_dev.get(ar, {}).items():
                by_area_dev[ar][acc] = by_area_dev[ar].get(acc, 0) + sec
        main = {ar: max(d, key=lambda a: d[a]) for ar, d in by_area_dev.items() if d}

        # attribute each developer's NON-BUG logged hours: own area, except overhead people
        # (ARCHI/PO/DEVOPS/CONSULTANT/blank) whose hours go to the ticket-overhead bucket.
        area_logged = {ar: 0.0 for ar in AREAS}
        for acc, sec in agg["devLogged"].items():
            ar = devmap[acc]["area"]
            if ar == "overhead":
                archpr_logged += sec; archpr_devs[devmap[acc]["name"]] = archpr_devs.get(devmap[acc]["name"], 0.0) + sec
            else:
                area_logged[ar] += sec

        # estimates per area
        # A. Est (Architect) = STRICTLY the per-area architect estimate custom fields (days x8).
        # No fallback to the ticket's Original Estimate — that field is the DL (Dev-lead) estimate.
        # A tiny placeholder (e.g. 0.01 d -> 0.08 h, below EST_MIN) counts as 0 / no estimate.
        vals = {ar: tf.get(AREA_EST_FIELD[ar]) for ar in AREAS}
        area_aest = {ar: 0.0 for ar in AREAS}; area_dlest = {ar: 0.0 for ar in AREAS}
        for ar in AREAS:
            v = vals[ar]; est = round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
            area_aest[ar] = 0.0 if 0 < est < EST_MIN else est
        if ttype == "US":
            for c in children.get(tkey, []):
                cf = c.get("fields") or {}
                if is_bug(cf): continue
                car = area_of(cf) or pa
                if car in AREAS: area_dlest[car] += hours(cf.get("timeoriginalestimate"))
            area_dlest = {ar: round(v, 1) for ar, v in area_dlest.items()}
        elif pa in AREAS:
            area_dlest[pa] = hours(tf.get("timeoriginalestimate"))

        # AI per area (record domain, or a same-area child carrying the AI field)
        ai_area = {ar: (ar in rec) for ar in AREAS}
        for c in children.get(tkey, []):
            cf = c.get("fields") or {}
            if cf.get("customfield_10745"):
                car = area_of(cf) or pa
                if car in AREAS: ai_area[car] = True

        areas_out = {}
        for ar in AREAS:
            log_h = hours(area_logged[ar]); sub_h = hours(area_sub_h[ar])
            areas_out[ar] = {"main": devmap[main[ar]]["name"] if ar in main else "",
                             "aEst": area_aest[ar], "dlEst": area_dlest[ar],
                             "logged": log_h, "subBug": sub_h, "totalDev": round(log_h + sub_h, 1),
                             "bugs": area_bug_ct[ar], "ai": ai_area[ar]}
        archpr_h = hours(archpr_logged)
        total_logged = round(sum(areas_out[ar]["logged"] for ar in AREAS) + archpr_h, 1)
        total_dev = round(sum(areas_out[ar]["totalDev"] for ar in AREAS) + archpr_h, 1)
        date = tdate; month = (date or "")[:7] or "no-date"
        rows.append({"key": tkey, "project": str(tkey).split("-")[0], "fixVersions": tf.get("fixVersions") or [],
                     "ttype": ttype, "title": (tf.get("summary") or "")[:60],
                     "status": status, "final": final, "date": date, "month": month, "areas": areas_out,
                     "archprH": archpr_h,
                     "archprDevs": [(n, hours(archpr_devs[n])) for n in sorted(archpr_devs, key=lambda n: -archpr_devs[n])],
                     "totalLogged": total_logged, "totalDev": total_dev,
                     "aiAny": any(areas_out[ar]["ai"] for ar in AREAS),
                     "bugsTotal": sum(area_bug_ct[ar] for ar in AREAS)})
    rows.sort(key=lambda r: (r["date"], r["totalLogged"]), reverse=True)   # newest ticket-date first
    return rows, unknown

# ---------- per-area totals (across tickets) ----------
def area_totals(rows):
    # aE/aL/aB (Arch) & dE/dL/dB (DL) are the gain basis: summed over only tickets carrying that
    # estimate, so unestimated tickets' logged hours don't inflate the aggregate gain.
    tot = {ar: {"tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "subBug": 0.0, "bugs": 0, "ai": 0,
                "aE": 0.0, "aL": 0.0, "aB": 0.0, "dE": 0.0, "dL": 0.0, "dB": 0.0} for ar in AREAS}
    archpr = 0.0; grand_log = 0.0
    for r in rows:
        for ar in AREAS:
            a = r["areas"][ar]
            if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                g = tot[ar]; g["tickets"] += 1
                for k in ("aEst", "dlEst", "logged", "subBug", "bugs"): g[k] += a[k]
                g["ai"] += int(a["ai"])
                if a["aEst"] >= EST_MIN: g["aE"] += a["aEst"]; g["aL"] += a["logged"]; g["aB"] += a["subBug"]
                if a["dlEst"] >= EST_MIN: g["dE"] += a["dlEst"]; g["dL"] += a["logged"]; g["dB"] += a["subBug"]
        archpr += r["archprH"]; grand_log += r["totalLogged"]
    return tot, round(archpr, 1), round(grand_log, 1)

def months_of(rows):
    return sorted({r["month"] for r in rows}, reverse=True)

# ---------- shared renderers (reused for the overall view and per month) ----------
def md_totals_lines(rows):
    tot, archpr_tot, grand_log = area_totals(rows)   # all values in hours; shown as days below
    def pl(v): return f"{round(v / grand_log * 100)}%" if grand_log else "–"   # % of total logged h
    out = ["| Area | Tickets | A. Est d | DL. Est d | Total dev d | Logged d | Sub-bug d | AI-assisted | % Logged | Arch gain | DL gain | Sub-bugs |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for ar in AREAS:
        g = tot[ar]
        out.append(f"| {AREA_LABEL[ar]} | {g['tickets']} | {days(g['aEst'])} | {days(g['dlEst'])} | "
                   f"{days(g['logged'] + g['subBug'])} | {days(g['logged'])} | {days(g['subBug'])} | {g['ai']}/{g['tickets']} | {pl(g['logged'])} | "
                   f"{gain_two(g['aE'], g['aL'], g['aB'])} | {gain_two(g['dE'], g['dL'], g['dB'])} | {g['bugs']} |")
    out.append(f"| Overhead | – | – | – | {days(archpr_tot)} | {days(archpr_tot)} | – | – | {pl(archpr_tot)} | – | – | – |")
    t_sub_h = sum(tot[ar]["subBug"] for ar in AREAS)
    t_aest = days(sum(tot[ar]["aEst"] for ar in AREAS)); t_dlest = days(sum(tot[ar]["dlEst"] for ar in AREAS))
    t_sub = days(t_sub_h); t_bugs = sum(tot[ar]["bugs"] for ar in AREAS)
    grand_dev = days(grand_log + t_sub_h)   # Total dev = all logged (areas + Overhead) + all sub-bug
    out.append(f"| **Total** | | {t_aest} | {t_dlest} | **{grand_dev}** | **{days(grand_log)}** | {t_sub} | | 100% | | | {t_bugs} |")
    return out

def gspan1(est, lb):   # single with-bug gain, coloured
    g = gain_pct(est, lb); c = gain_cls(g)
    return f'<span class="{c}">{gain_str(g)}</span>' if c else gain_str(g)

def html_totals_table(rows, tab="all", month="all"):
    # One row per area. Arch gain shows THREE with-bug gains — all / no-AI / AI — each with its ticket
    # count in ( ); DL gain is a single with-bug gain. All gains use the estimated-tickets basis
    # (aEst/dlEst >= EST_MIN) so unestimated tickets' logged hours don't inflate them. (JS mirrors this.)
    def z(): return {"tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "subBug": 0.0, "bugs": 0,
                     "aE": 0.0, "aL": 0.0, "aB": 0.0, "dE": 0.0, "dL": 0.0, "dB": 0.0,
                     "n_no": 0, "n_ai": 0, "aE_no": 0.0, "aL_no": 0.0, "aB_no": 0.0, "aE_ai": 0.0, "aL_ai": 0.0, "aB_ai": 0.0}
    tot = {ar: z() for ar in AREAS}
    archpr_tot = 0.0; grand_log = 0.0
    for r in rows:
        for ar in AREAS:
            a = r["areas"][ar]
            if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                g = tot[ar]; g["tickets"] += 1
                for k in ("aEst", "dlEst", "logged", "subBug", "bugs"): g[k] += a[k]
                if a["aEst"] >= EST_MIN: g["aE"] += a["aEst"]; g["aL"] += a["logged"]; g["aB"] += a["subBug"]
                if a["dlEst"] >= EST_MIN: g["dE"] += a["dlEst"]; g["dL"] += a["logged"]; g["dB"] += a["subBug"]
                if a["ai"]:
                    g["n_ai"] += 1
                    if a["aEst"] >= EST_MIN: g["aE_ai"] += a["aEst"]; g["aL_ai"] += a["logged"]; g["aB_ai"] += a["subBug"]
                else:
                    g["n_no"] += 1
                    if a["aEst"] >= EST_MIN: g["aE_no"] += a["aEst"]; g["aL_no"] += a["logged"]; g["aB_no"] += a["subBug"]
        archpr_tot += r["archprH"]; grand_log += r["totalLogged"]
    archpr_tot = round(archpr_tot, 1); grand_log = round(grand_log, 1)
    def pl(v): return f"{round(v / grand_log * 100)}%" if grand_log else "&ndash;"   # % of total logged
    def pctsub(logged, sub):
        den = logged + sub; return f"{round(sub / den * 100)}%" if den else "&ndash;"
    def archcell(g):
        return (f'{gspan1(g["aE"], g["aL"] + g["aB"])} <span class="sm">({g["tickets"]})</span> &middot; '
                f'noAI {gspan1(g["aE_no"], g["aL_no"] + g["aB_no"])} <span class="sm">({g["n_no"]})</span> &middot; '
                f'AI {gspan1(g["aE_ai"], g["aL_ai"] + g["aB_ai"])} <span class="sm">({g["n_ai"]})</span>')
    h = [f"<div class=\"tw\" data-totals data-tab=\"{e(tab)}\" data-month=\"{e(month)}\"><table><thead><tr>"
         "<th>Area</th><th>Project</th><th class='r'>Tickets</th><th class='r'>A. Est d</th><th class='r'>DL. Est d</th>"
         "<th class='r'>Total dev d</th><th class='r'>% Logged</th><th class='r'>Logged d</th><th class='r'>Sub-bug d</th><th class='r'>% Sub-bug</th>"
         "<th class='r'>Arch gain (all &middot; noAI &middot; AI, w/ bugs)</th><th class='r'>DL gain</th><th class='r'>Sub-bugs</th></tr></thead><tbody>"]
    for ar in AREAS:
        g = tot[ar]
        if not g["tickets"]: continue
        h.append(f"<tr><td class='name'>{AREA_LABEL[ar]}</td><td class='proj'>All</td><td class='r'>{g['tickets']}</td>"
                 f"<td class='r'>{days(g['aEst'])}</td><td class='r'>{days(g['dlEst'])}</td>"
                 f"<td class='r'>{days(g['logged']+g['subBug'])}</td><td class='r'>{pl(g['logged'])}</td><td class='r'>{days(g['logged'])}</td>"
                 f"<td class='r'>{days(g['subBug'])}</td><td class='r'>{pctsub(g['logged'], g['subBug'])}</td>"
                 f"<td class='r'>{archcell(g)}</td>"
                 f"<td class='r'>{gspan1(g['dE'], g['dL'] + g['dB'])}</td><td class='r'>{g['bugs']}</td></tr>")
    h.append(f"<tr><td class='name'>Overhead</td><td class='proj'>All</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>{days(archpr_tot)}</td><td class='r'>{pl(archpr_tot)}</td><td class='r'>{days(archpr_tot)}</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td></tr>")
    t_aest = sum(tot[ar]["aEst"] for ar in AREAS); t_dlest = sum(tot[ar]["dlEst"] for ar in AREAS)
    t_sub_h = sum(tot[ar]["subBug"] for ar in AREAS); t_log = sum(tot[ar]["logged"] for ar in AREAS)
    t_bugs = sum(tot[ar]["bugs"] for ar in AREAS)
    grand_dev = days(grand_log + t_sub_h)   # Total dev = all logged (areas + Overhead) + all sub-bug
    h.append(f"<tr class='tot'><td class='name'>Total</td><td class='proj'>All</td><td></td>"
             f"<td class='r'>{days(t_aest)}</td><td class='r'>{days(t_dlest)}</td>"
             f"<td class='r'>{grand_dev}</td><td class='r'>100%</td><td class='r'>{days(grand_log)}</td><td class='r'>{days(t_sub_h)}</td><td class='r'>{pctsub(t_log, t_sub_h)}</td>"
             f"<td></td><td></td><td class='r'>{t_bugs}</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)

MG_COLS = [("backend", False, "Backend"), ("backend", True, "Backend AI"),
           ("frontend", False, "Frontend"), ("frontend", True, "Frontend AI"),
           ("qa", False, "QA"), ("qa", True, "QA AI"), ("overhead", None, "Overhead")]
def html_month_gain_table(rows, tab="all"):
    """Month-by-month Arch gain (with sub-bugs) per area split by AI, plus Overhead; each cell is the
    gain with the group's ticket count in ( ). data-monthgain lets the project filter rebuild it."""
    months = sorted({r["month"] for r in rows}, reverse=True)
    h = [f'<div class="tw" data-monthgain data-tab="{e(tab)}"><table><thead><tr><th>Month</th>'
         + "".join(f'<th class="r">{e(lbl)}</th>' for _, _, lbl in MG_COLS) + "</tr></thead><tbody>"]
    for m in months:
        mr = [r for r in rows if r["month"] == m]
        h.append(f'<tr><td class="name">{e(m)}</td>')
        for ar, aiflag, _ in MG_COLS:
            if ar == "overhead":
                cnt = sum(1 for r in mr if r["archprH"])
                oh = sum(r["archprH"] for r in mr); mtot = sum(r["totalLogged"] for r in mr)
                val = f'{round(oh / mtot * 100)}% <span class="sm">({cnt})</span>' if mtot else "&ndash;"
                h.append(f'<td class="r">{val}</td>'); continue
            est = log = bug = 0.0; cnt = 0
            for r in mr:
                a = r["areas"][ar]
                if (a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]) and bool(a["ai"]) == aiflag:
                    cnt += 1
                    if a["aEst"] >= EST_MIN:   # gain basis: only tickets carrying an Architect estimate
                        est += a["aEst"]; log += a["logged"]; bug += a["subBug"]
            if not cnt:
                h.append('<td class="r">&ndash;</td>'); continue
            g = gain_pct(est, log + bug)
            h.append(f'<td class="r {gain_cls(g)}">{gain_str(g)} <span class="sm">({cnt})</span></td>')
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)

MATRIX_SUB = ["Main dev", "A.Est d", "DL.Est d", "Tot dev d", "Logged d", "Sub-bug d", "AI", "Arch gain", "DL gain", "#SB"]
def html_matrix_head():
    head1 = ['<th rowspan="2">Ticket</th><th rowspan="2">Date</th><th rowspan="2">Type</th><th rowspan="2">Fix ver</th><th rowspan="2">Title</th>'
             '<th rowspan="2">Status</th><th rowspan="2" class="c">F</th>'
             '<th rowspan="2" class="c gaincol">Arch gain B/F/Q &middot; OH%<br><span class="sm">w/ bugs</span></th>'
             '<th rowspan="2" class="c gaincol">Logged+bug B/F/Q/OH<br><span class="sm">days</span></th>']
    for ar in AREAS:
        head1.append(f'<th colspan="{len(MATRIX_SUB)}" class="grp {ar}">{AREA_LABEL[ar]}</th>')
    head1.append('<th rowspan="2" class="r">Overhead d</th><th rowspan="2" class="r">Overhead %</th><th rowspan="2">Overhead people</th><th rowspan="2" class="r">Total log d</th>')
    head2 = []
    for ar in AREAS:
        for i, s in enumerate(MATRIX_SUB):
            cls = "c" if s == "AI" else ("" if s == "Main dev" else "r")
            head2.append(f'<th class="{cls}{" ledge" if i == 0 else ""}">{e(s)}</th>')
    return '<thead><tr>' + "".join(head1) + "</tr><tr>" + "".join(head2) + "</tr></thead>"

def html_matrix_body(rows):
    out = []
    for r in rows:
        fv = r.get("fixVersions") or []
        tds = [f'<td class="key"><a href="https://opencellsoft.atlassian.net/browse/{e(r["key"])}" target="_blank" rel="noopener">{e(r["key"])}</a></td>'
               f'<td class="sm">{e(r["date"] or "–")}</td>'
               f'<td>{e(r["ttype"])}</td><td class="sm">{e(", ".join(fv)) if fv else "&ndash;"}</td><td class="ti">{e(r["title"])}</td><td>{e(r["status"])}</td>'
               f'<td class="c">{"<span class=fin>T</span>" if r["final"] else ""}</td>']
        # single column: back / front / QA Architect gain, considering sub-bugs (est vs logged+sub-bug)
        AG_LBL = {"backend": "B", "frontend": "F", "qa": "Q"}
        ag_parts = []
        for ar in AREAS:
            x = r["areas"][ar]
            ag_parts.append(f'{AG_LBL[ar]}&nbsp;{gain_span(gain_pct(x["aEst"], x["logged"] + x["subBug"]))}')
        oh_pct = round(r["archprH"] / r["totalLogged"] * 100) if r["totalLogged"] else None   # overhead share of ticket's total logged
        ag_parts.append(f'OH&nbsp;{oh_pct}%' if oh_pct is not None else 'OH&nbsp;&ndash;')
        tds.append(f'<td class="c gaincol sm">{" ".join(ag_parts)}</td>')
        # total logged incl. sub-bug, per area + overhead (days)
        lb_parts = [f'{AG_LBL[ar]}&nbsp;{days(r["areas"][ar]["logged"] + r["areas"][ar]["subBug"])}' for ar in AREAS]
        lb_parts.append(f'OH&nbsp;{days(r["archprH"])}')
        tds.append(f'<td class="c gaincol sm">{" ".join(lb_parts)}</td>')
        for ar in AREAS:
            x = r["areas"][ar]; blank = not (x["logged"] or x["subBug"] or x["aEst"] or x["dlEst"] or x["main"])
            if blank:
                tds.append(f'<td class="ledge dim area-{ar}" colspan="{len(MATRIX_SUB)}">&ndash;</td>'); continue
            tds.append(f'<td class="name ledge area-{ar}">{e(x["main"])}</td>'
                       f'<td class="r area-{ar}">{days(x["aEst"])}</td><td class="r area-{ar}">{days(x["dlEst"])}</td>'
                       f'<td class="r area-{ar}">{days(x["totalDev"])}</td><td class="r area-{ar}">{days(x["logged"])}</td><td class="r area-{ar}">{days(x["subBug"])}</td>'
                       f'<td class="c area-{ar}">{"<span class=aibadge>AI</span>" if x["ai"] else ""}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["aEst"], x["logged"], x["subBug"])}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["dlEst"], x["logged"], x["subBug"])}</td><td class="r area-{ar}">{x["bugs"]}</td>')
        people = ", ".join(f'{e(n)} {days(h)}d' for n, h in r["archprDevs"])
        oh_pct = round(r["archprH"] / r["totalLogged"] * 100) if r["totalLogged"] else None   # overhead share of ticket's total logged
        tds.append(f'<td class="r">{days(r["archprH"]) if r["archprH"] else "&ndash;"}</td>'
                   f'<td class="r">{str(oh_pct) + "%" if oh_pct is not None else "&ndash;"}</td>'
                   f'<td class="sm">{people if people else "&ndash;"}</td>'
                   f'<td class="r tot">{days(r["totalLogged"])}</td>')
        out.append(f'<tr data-project="{e(r["project"])}" data-fixv="{e("|".join(fv))}">' + "".join(tds) + "</tr>")
    return "".join(out)

def html_report_body(rs, tab="all"):
    """Full report body (Totals by area overall + by month, then the per-ticket matrix grouped
    by month) for a subset of rows — used inside each tab panel."""
    if not rs:
        return '<p class="dim" style="padding:1rem">No tickets of this type in this window.</p>'
    tot_, _, grand = area_totals(rs)
    _tsub = round(sum(tot_[ar]["subBug"] for ar in AREAS), 1)
    ms = months_of(rs)
    h = []; w = h.append
    w("<h2>Totals by area</h2>")
    w(html_totals_table(rs, tab, "all"))
    w(f'<p class="meta" data-grand data-tab="{e(tab)}"><b>Total across all groups:</b> {days(grand)} d logged + {days(_tsub)} d sub-bug = <b>{days(grand + _tsub)} d</b> total dev <span class="sm">(1 d = {DAY_HOURS} h)</span></p>')
    w('<p class="bm">Arch gain (with sub-bugs) by month &mdash; ticket count in ( )</p>')
    w(html_month_gain_table(rs, tab))
    w('<p class="bm">By month</p>')
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} tickets)</span></summary>{html_totals_table(mr, tab, m)}</details>')
    w("<h2>Per ticket &mdash; per-area columns</h2>")
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} tickets)</span></summary>'
          f'<div class="tw wide"><table class="matrix">{html_matrix_head()}<tbody>{html_matrix_body(mr)}</tbody></table></div></details>')
    return "".join(h)

# ---------- second report: finished-US per-developer summary ----------
US_COLS = [("dev", "Developer"), ("area", "Area"), ("nUS", "US (final)"),
           ("avgSub", "Avg sub-bugs / US"), ("sumAEst", "Sum A. Est d"), ("sumLogged", "Sum logged d"),
           ("sumSub", "Sum sub-bug d"), ("sumTotal", "Sum total d"),
           ("gainBug", "Gain (with sub-bugs)"), ("gainNoBug", "Gain (no sub-bugs)")]
US_NUM = {"nUS", "avgSub", "sumAEst", "sumLogged", "sumSub", "sumTotal", "gainBug", "gainNoBug"}
US_DAYCOLS = {"sumAEst", "sumLogged", "sumSub", "sumTotal"}   # hour sums rendered in days (1 d = 8 h)

def finished_us_records(rows):
    """One record per (finished User Story, area with a main dev): that area's real main developer
    (top by dev-logged + own sub-bug-fixing hours — token reviewers don't win), area, month, AI flag
    and that area's numbers. A US worked across 3 areas yields up to 3 developer records."""
    recs = []
    for r in rows:
        if r["ttype"] != "US" or not r["final"]: continue
        for ar in AREAS:
            x = r["areas"][ar]
            if not x["main"]: continue
            recs.append({"dev": x["main"], "area": ar, "month": r["month"], "ai": bool(x["ai"]),
                         "aEst": x["aEst"], "logged": x["logged"], "subBug": x["subBug"], "bugs": x["bugs"]})
    return recs

def _us_agg(label, area, rs):
    n = len(rs)
    sA = round(sum(x["aEst"] for x in rs), 1); sL = round(sum(x["logged"] for x in rs), 1)
    sB = round(sum(x["subBug"] for x in rs), 1)
    return {"dev": label, "area": area, "month": label, "nUS": n, "aiUS": sum(1 for x in rs if x["ai"]),
            "avgSub": round(sum(x["bugs"] for x in rs) / n, 2) if n else 0,
            "sumAEst": sA, "sumLogged": sL, "sumSub": sB, "sumTotal": round(sL + sB, 1),
            "gainBug": gain_pct(sA, sL + sB), "gainNoBug": gain_pct(sA, sL)}

def _us_dev_rows(recs, ai_flag):
    by_dev = defaultdict(list)
    for x in recs:
        if x["ai"] == ai_flag: by_dev[x["dev"]].append(x)
    dev_order = sorted(by_dev, key=lambda d: (AREAS.index(by_dev[d][0]["area"]), d.lower()))  # by area, then name
    out = [_us_agg(dev, AREA_LABEL[by_dev[dev][0]["area"]], by_dev[dev]) for dev in dev_order]
    total = _us_agg(f"TOTAL ({len(by_dev)} dev)", "", [x for rs in by_dev.values() for x in rs]) if by_dev else None
    return out, total

def _us_cells_html(d):
    out = []
    for k, _ in US_COLS:
        if k in ("gainBug", "gainNoBug"):
            out.append(f'<td class="r {gain_cls(d[k])}">{gain_str(d[k])}</td>')
        elif k in ("dev", "area"):
            out.append(f'<td class="name">{e(d[k])}</td>')
        elif k in US_DAYCOLS:
            out.append(f'<td class="r">{days(d[k])}</td>')
        else:
            out.append(f'<td class="r">{d[k]}</td>')
    return "".join(out)

def _us_tables_html(recs):
    h = []
    for ai_flag, label in ((True, "true"), (False, "false")):
        drows, total = _us_dev_rows(recs, ai_flag)
        h.append(f'<h3>AI-assisted: {label}</h3>')
        if not drows:
            h.append('<p class="dim" style="padding:.6rem">No finished User Stories in this group.</p>'); continue
        h.append('<div class="tw"><table><thead><tr>'
                 + "".join(f'<th class="{ "r" if k in US_NUM else "" }">{e(t)}</th>' for k, t in US_COLS)
                 + '</tr></thead><tbody>')
        for d in drows: h.append('<tr>' + _us_cells_html(d) + '</tr>')
        if total: h.append('<tr class="tot">' + _us_cells_html(total) + '</tr>')
        h.append('</tbody></table></div>')
    return "".join(h)

# by-developer view: per user (area, then name), a month-by-month table of their finished US
UMONTH_COLS = [("month", "Month"), ("nUS", "US (final)"), ("avgSub", "Avg sub-bugs / US"),
               ("sumAEst", "Sum A. Est d"), ("sumLogged", "Sum logged d"), ("sumSub", "Sum sub-bug d"),
               ("sumTotal", "Sum total d"), ("gainBug", "Gain (with sub-bugs)"), ("gainNoBug", "Gain (no sub-bugs)")]
UMONTH_NUM = {"nUS", "avgSub", "sumAEst", "sumLogged", "sumSub", "sumTotal", "gainBug", "gainNoBug"}

def _umonth_cells(d):
    out = []
    for k, _ in UMONTH_COLS:
        if k in ("gainBug", "gainNoBug"):
            out.append(f'<td class="r {gain_cls(d[k])}">{gain_str(d[k])}</td>')
        elif k == "month":
            out.append(f'<td class="name">{e(d[k])}</td>')
        elif k in US_DAYCOLS:
            out.append(f'<td class="r">{days(d[k])}</td>')
        else:
            out.append(f'<td class="r">{d[k]}</td>')
    return "".join(out)

def _umonth_table(recs):
    """One month-by-month table (+ Total) for a set of a developer's finished-US records."""
    if not recs:
        return '<p class="dim" style="padding:.4rem .6rem">None.</p>'
    h = ['<div class="tw"><table><thead><tr>'
         + "".join(f'<th class="{ "r" if k in UMONTH_NUM else "" }">{e(t)}</th>' for k, t in UMONTH_COLS)
         + '</tr></thead><tbody>']
    for m in sorted({x["month"] for x in recs}, reverse=True):
        h.append('<tr>' + _umonth_cells(_us_agg(m, "", [x for x in recs if x["month"] == m])) + '</tr>')
    h.append('<tr class="tot">' + _umonth_cells(_us_agg("Total", "", recs)) + '</tr></tbody></table></div>')
    return "".join(h)

def _us_by_user_html(recs):
    """Per developer (area, then name), expandable month-by-month breakdown of their finished US,
    each split into AI-assisted true / false sub-tables."""
    by_dev = defaultdict(list)
    for x in recs: by_dev[x["dev"]].append(x)
    order = sorted(by_dev, key=lambda d: (AREAS.index(by_dev[d][0]["area"]), d.lower()))
    if not order:
        return '<p class="dim" style="padding:.6rem">No finished User Stories in this window.</p>'
    h = []
    for dev in order:
        drecs = by_dev[dev]; area = AREA_LABEL[drecs[0]["area"]]; tot = _us_agg("Total", "", drecs)
        h.append(f'<details><summary>{e(dev)} <span class="cnt">({e(area)} &middot; {tot["nUS"]} US &middot; '
                 f'{tot["aiUS"]} AI &middot; {days(tot["sumTotal"])}d)</span></summary>')
        for ai_flag, label in ((True, "true"), (False, "false")):
            h.append(f'<h4>AI-assisted: {label}</h4>')
            h.append(_umonth_table([x for x in drecs if x["ai"] == ai_flag]))
        h.append('</details>')
    return "".join(h)

def _summary_path(path, tag):
    base, ext = os.path.splitext(path); return f"{base}-{tag}{ext}"

def write_us_summary(rows, html_path, csv_path, project, since, until):
    recs = finished_us_records(rows)
    mons = sorted({x["month"] for x in recs}, reverse=True)
    # Tab 1 — By month (date -> user): overall AI tables, then a per-month details block.
    bymonth = ["<h2>Overall</h2>", _us_tables_html(recs), '<p class="bm">By month</p>']
    for i, m in enumerate(mons):
        mr = [x for x in recs if x["month"] == m]; op = " open" if i == 0 else ""
        bymonth.append(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} US-area records)</span></summary>{_us_tables_html(mr)}</details>')
    # Tab 2 — By developer (user -> date): per developer, a month-by-month breakdown.
    byuser = ['<p class="bm">Each developer, expandable to their month-by-month finished User Stories</p>', _us_by_user_html(recs)]
    B = [f"<h1>Finished User Stories &mdash; per-developer summary</h1>",
         f'<p class="meta">Project <b>{e(project)}</b> &middot; [{e(since or "…")} … {e(until or "…")}) '
         f'&middot; only <b>User Stories</b> in a final status &middot; per area developer</p>',
         '<div class="tabs">',
         '<input type="radio" name="ustab" id="utab-month" checked>',
         '<input type="radio" name="ustab" id="utab-dev">',
         '<div class="tabbar"><label for="utab-month">By month</label><label for="utab-dev">By developer</label></div>',
         f'<section class="panel panel-month">{"".join(bymonth)}</section>',
         f'<section class="panel panel-dev">{"".join(byuser)}</section>',
         '</div>']
    B.append('<p class="foot">Only <b>User Stories</b> whose status is final are counted, split by AI and credited to each '
             'area\'s <b>main developer</b> &mdash; the area\'s roster dev with the most total work (dev-logged + their own '
             'sub-bug-fixing hours), so a token reviewer never wins and Architect/PR-review time sits in the Arch/PR bucket. '
             'A US worked across areas yields one row per area. <b>Area</b> is that developer\'s area. '
             '<b>Avg sub-bugs / US</b> = child Bug/Sub-bug count per US (the <b>Total</b> row uses total sub-bugs &divide; total US). '
             '<b>Gain</b> = (Sum A. Est &minus; Sum logged)/Sum A. Est, <b>with / without</b> sub-bug hours; a dash marks a meaningless gain. All hour sums are shown in <b>days</b> (1 d = 8 h). '
             'Generated by <code>/oc-time-report</code>.</p>')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finished US summary — {e(project)} {e(since or '')}…{e(until or '')}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --card:#fff; --accent:#2563eb; --pos:#15803d; --neg:#b91c1c; --zebra:#fafbfc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad;
  --line:#242a31; --head:#171b21; --card:#141821; --accent:#6ea8fe; --pos:#4ade80; --neg:#f87171; --zebra:#12161c; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.2rem; margin:1.8rem 0 .5rem; padding-bottom:.3rem; border-bottom:2px solid var(--line); }}
h3 {{ font-size:1rem; margin:1.1rem 0 .4rem; color:var(--muted); }}
h4 {{ font-size:.85rem; margin:.7rem 0 .25rem; color:var(--muted); font-weight:600; }}
.meta {{ color:var(--muted); margin:0 0 1rem; }}
.tw {{ border:1px solid var(--line); border-radius:10px; margin:.3rem 0 1rem; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.45rem .65rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
.r {{ text-align:right; }} .name {{ font-weight:600; }}
.pos {{ color:var(--pos); font-weight:600; }} .neg {{ color:var(--neg); font-weight:600; }}
tr.tot td {{ font-weight:700; border-top:2px solid var(--line); background:var(--head); }}
.dim {{ color:var(--muted); }}
details {{ border:1px solid var(--line); border-radius:10px; margin:.4rem 0; padding:0 .6rem; }}
details[open] {{ padding-bottom:.5rem; }}
summary {{ cursor:pointer; font-weight:600; padding:.5rem .2rem; }}
summary .cnt {{ color:var(--muted); font-weight:400; font-size:.9em; }}
.bm {{ color:var(--muted); font-size:.72rem; margin:.6rem 0 .2rem; text-transform:uppercase; letter-spacing:.05em; }}
.tabs > input {{ position:absolute; opacity:0; width:0; height:0; }}
.tabbar {{ display:flex; flex-wrap:wrap; gap:.25rem; border-bottom:2px solid var(--line); margin:1rem 0 0; }}
.tabbar label {{ padding:.5rem 1rem; cursor:pointer; color:var(--muted); font-weight:600;
  border:1px solid transparent; border-bottom:none; border-radius:8px 8px 0 0; margin-bottom:-2px; }}
#utab-month:checked ~ .tabbar label[for="utab-month"],
#utab-dev:checked ~ .tabbar label[for="utab-dev"] {{ color:var(--fg); background:var(--card);
  border-color:var(--line); border-bottom:2px solid var(--card); }}
.panel {{ display:none; padding-top:.6rem; }}
#utab-month:checked ~ .panel-month {{ display:block; }}
#utab-dev:checked ~ .panel-dev {{ display:block; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
.foot code {{ background:var(--head); padding:.05rem .3rem; border-radius:4px; }}
</style></head><body>
{"".join(B)}
</body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(html_path)) or ".", exist_ok=True)
    open(html_path, "w", encoding="utf-8").write(doc)
    if csv_path:
        def gcell(g): return "-" if (g is None or abs(g) > GAIN_CAP) else g
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Month", "AI assisted"] + [t for _, t in US_COLS])
            for scope, srecs in [("ALL", recs)] + [(m, [x for x in recs if x["month"] == m]) for m in mons]:
                for ai_flag, lab in ((True, "Yes"), (False, "No")):
                    drows, total = _us_dev_rows(srecs, ai_flag)
                    for d in drows + ([total] if total else []):
                        row = [scope, lab]
                        for k, _ in US_COLS:
                            if k in ("gainBug", "gainNoBug"): row.append(gcell(d[k]))
                            elif k in US_DAYCOLS: row.append(days(d[k]))
                            else: row.append(d[k])
                        w.writerow(row)
    return len(recs), mons

PROJECT_FILTER_JS = r"""<script>
(function(){
  var ROWS = JSON.parse(document.getElementById('rowdata').textContent || '[]');
  var DAY = 8, EST_MIN = 0.5, CAP = 1000;
  var AK = {backend:'be', frontend:'fe', qa:'qa'}, LABEL = {backend:'Backend', frontend:'Frontend', qa:'QA'};
  function d(h){ return Math.round((h||0)/DAY*10)/10; }
  function gp(est, log){ if(!est || est<EST_MIN || !log || log<=0) return null; return Math.round((est-log)/est*100); }
  function gs(g){ return (g===null || Math.abs(g)>CAP) ? '-' : (g>=0 ? '+'+g+'%' : g+'%'); }
  function gspan(g){ var c=(g===null||Math.abs(g)>CAP)?'':(g>=0?'pos':'neg'); return c?('<span class="'+c+'">'+gs(g)+'</span>'):gs(g); }
  function g2(est,log,bug){ return gspan(gp(est,log+bug))+' / '+gspan(gp(est,log)); }
  function tabMatch(r,tab){ if(tab==='all')return true; if(tab==='us')return r.t==='US'; if(tab==='usfinal')return r.t==='US'&&r.f;
    if(tab==='bugfinal')return r.t==='Bug'&&r.f; if(tab==='other')return r.t!=='US'; return true; }
  function z(){ return {tickets:0,aEst:0,dlEst:0,logged:0,subBug:0,bugs:0,ai:0,aE:0,aL:0,aB:0,dE:0,dL:0,dB:0,
    n_no:0,n_ai:0,aE_no:0,aL_no:0,aB_no:0,aE_ai:0,aL_ai:0,aB_ai:0}; }
  function g1(est,lb){ return gspan(gp(est,lb)); }   // single with-bug gain, coloured

  function agg(rows){
    var A={backend:z(),frontend:z(),qa:z()}, oh=0, grand=0;
    for(var i=0;i<rows.length;i++){ var r=rows[i];
      for(var ar in AK){ var a=r[AK[ar]]; // [aEst,dlEst,logged,subBug,bugs,ai]
        if(a[2]||a[3]||a[0]||a[1]){ var g=A[ar]; g.tickets++; g.aEst+=a[0]; g.dlEst+=a[1]; g.logged+=a[2]; g.subBug+=a[3]; g.bugs+=a[4]; g.ai+=a[5]?1:0; }
      }
      oh+=r.oh; grand+=r.be[2]+r.fe[2]+r.qa[2]+r.oh;
    }
    return {A:A, oh:oh, grand:grand};
  }
  function pl(v,grand){ return grand ? Math.round(v/grand*100)+'%' : '&ndash;'; }

  function totalsBody(rows, projLabel){
    var A={backend:z(),frontend:z(),qa:z()}, oh=0, grand=0;
    for(var i=0;i<rows.length;i++){ var r=rows[i];
      for(var ar in AK){ var a=r[AK[ar]];
        if(a[2]||a[3]||a[0]||a[1]){ var g=A[ar]; g.tickets++; g.aEst+=a[0]; g.dlEst+=a[1]; g.logged+=a[2]; g.subBug+=a[3]; g.bugs+=a[4];
          if(a[0]>=EST_MIN){ g.aE+=a[0]; g.aL+=a[2]; g.aB+=a[3]; }
          if(a[1]>=EST_MIN){ g.dE+=a[1]; g.dL+=a[2]; g.dB+=a[3]; }
          if(a[5]){ g.n_ai++; if(a[0]>=EST_MIN){ g.aE_ai+=a[0]; g.aL_ai+=a[2]; g.aB_ai+=a[3]; } }
          else { g.n_no++; if(a[0]>=EST_MIN){ g.aE_no+=a[0]; g.aL_no+=a[2]; g.aB_no+=a[3]; } } }
      }
      oh+=r.oh; grand+=r.be[2]+r.fe[2]+r.qa[2]+r.oh;
    }
    function psub(lg,sb){ var den=lg+sb; return den?Math.round(sb/den*100)+'%':'&ndash;'; }
    function arch(g){ return g1(g.aE,g.aL+g.aB)+' <span class="sm">('+g.tickets+')</span> &middot; noAI '+g1(g.aE_no,g.aL_no+g.aB_no)+' <span class="sm">('+g.n_no+')</span> &middot; AI '+g1(g.aE_ai,g.aL_ai+g.aB_ai)+' <span class="sm">('+g.n_ai+')</span>'; }
    var out='';
    ['backend','frontend','qa'].forEach(function(ar){ var g=A[ar]; if(!g.tickets) return;
      out+='<tr><td class="name">'+LABEL[ar]+'</td><td class="proj">'+projLabel+'</td><td class="r">'+g.tickets+'</td>'
        +'<td class="r">'+d(g.aEst)+'</td><td class="r">'+d(g.dlEst)+'</td><td class="r">'+d(g.logged+g.subBug)+'</td>'
        +'<td class="r">'+pl(g.logged,grand)+'</td><td class="r">'+d(g.logged)+'</td><td class="r">'+d(g.subBug)+'</td><td class="r">'+psub(g.logged,g.subBug)+'</td>'
        +'<td class="r">'+arch(g)+'</td><td class="r">'+g1(g.dE,g.dL+g.dB)+'</td><td class="r">'+g.bugs+'</td></tr>';
    });
    out+='<tr><td class="name">Overhead</td><td class="proj">'+projLabel+'</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td>'
      +'<td class="r">'+d(oh)+'</td><td class="r">'+pl(oh,grand)+'</td><td class="r">'+d(oh)+'</td><td class="r">&ndash;</td><td class="r">&ndash;</td>'
      +'<td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td></tr>';
    var tA=0,tD=0,tsub=0,tlog=0,tbugs=0;
    ['backend','frontend','qa'].forEach(function(ar){ var g=A[ar]; tA+=g.aEst; tD+=g.dlEst; tsub+=g.subBug; tlog+=g.logged; tbugs+=g.bugs; });
    out+='<tr class="tot"><td class="name">Total</td><td class="proj">'+projLabel+'</td><td></td><td class="r">'+d(tA)+'</td><td class="r">'+d(tD)+'</td>'
      +'<td class="r">'+d(grand+tsub)+'</td><td class="r">'+(grand?'100%':'&ndash;')+'</td><td class="r">'+d(grand)+'</td><td class="r">'+d(tsub)+'</td><td class="r">'+psub(tlog,tsub)+'</td>'
      +'<td></td><td></td><td class="r">'+tbugs+'</td></tr>';
    return out;
  }

  var MGCOLS=[['backend',0],['backend',1],['frontend',0],['frontend',1],['qa',0],['qa',1],['overhead',null]];
  function monthGainBody(rows){
    var bym={}, order=[];
    for(var i=0;i<rows.length;i++){ var m=rows[i].m; if(!(m in bym)){ bym[m]=[]; order.push(m); } bym[m].push(rows[i]); }
    order.sort(function(a,b){ return a<b?1:(a>b?-1:0); });
    var out='';
    for(var k=0;k<order.length;k++){ var m=order[k], mr=bym[m]; out+='<tr><td class="name">'+m+'</td>';
      for(var ci=0;ci<MGCOLS.length;ci++){ var ar=MGCOLS[ci][0], af=MGCOLS[ci][1];
        if(ar==='overhead'){ var oc=0, oh=0, mtot=0;
          for(var j=0;j<mr.length;j++){ if(mr[j].oh) oc++; oh+=mr[j].oh; mtot+=mr[j].be[2]+mr[j].fe[2]+mr[j].qa[2]+mr[j].oh; }
          out+='<td class="r">'+(mtot?(Math.round(oh/mtot*100)+'% <span class="sm">('+oc+')</span>'):'&ndash;')+'</td>'; continue; }
        var est=0,log=0,bug=0,c=0;
        for(var j=0;j<mr.length;j++){ var a=mr[j][AK[ar]];
          if((a[2]||a[3]||a[0]||a[1]) && (a[5]?1:0)===af){ c++; if(a[0]>=EST_MIN){ est+=a[0]; log+=a[2]; bug+=a[3]; } } }
        if(!c){ out+='<td class="r">&ndash;</td>'; continue; }
        var g=gp(est,log+bug), cls=(g===null||Math.abs(g)>CAP)?'':(g>=0?'pos':'neg');
        out+='<td class="r '+cls+'">'+gs(g)+' <span class="sm">('+c+')</span></td>';
      }
      out+='</tr>';
    }
    return out;
  }
  function fvMatch(r, fx){ return fx==='all' || (r.fv && r.fv.indexOf(fx)>=0); }
  function apply(){
    var proj=(document.getElementById('projfilter')||{}).value||'all';
    var fx=(document.getElementById('fixvfilter')||{}).value||'all';
    var projLabel = proj==='all' ? 'All' : proj;
    function F(r,tab,month){ return tabMatch(r,tab) && (month===undefined||month==='all'||r.m===month) && (proj==='all'||r.p===proj) && fvMatch(r,fx); }
    document.querySelectorAll('[data-totals]').forEach(function(div){
      var tab=div.getAttribute('data-tab'), month=div.getAttribute('data-month');
      var tb=div.querySelector('tbody'); if(tb) tb.innerHTML=totalsBody(ROWS.filter(function(r){ return F(r,tab,month); }), projLabel);
    });
    document.querySelectorAll('[data-monthgain]').forEach(function(div){
      var tab=div.getAttribute('data-tab');
      var tb=div.querySelector('tbody'); if(tb) tb.innerHTML=monthGainBody(ROWS.filter(function(r){ return F(r,tab); }));
    });
    document.querySelectorAll('[data-grand]').forEach(function(p){
      var t=agg(ROWS.filter(function(r){ return F(r,p.getAttribute('data-tab')); })), tsub=t.A.backend.subBug+t.A.frontend.subBug+t.A.qa.subBug;
      p.innerHTML='<b>Total across all groups:</b> '+d(t.grand)+' d logged + '+d(tsub)+' d sub-bug = <b>'+d(t.grand+tsub)+' d</b> total dev <span class="sm">(1 d = '+DAY+' h)</span>';
    });
    document.querySelectorAll('tr[data-project]').forEach(function(tr){
      var okp=(proj==='all'||tr.getAttribute('data-project')===proj);
      var okf=(fx==='all'|| ('|'+(tr.getAttribute('data-fixv')||'')+'|').indexOf('|'+fx+'|')>=0);
      tr.style.display = (okp && okf) ? '' : 'none';
    });
    var TABS={'tab-all':'all','tab-us':'us','tab-usfinal':'usfinal','tab-bugfinal':'bugfinal','tab-other':'other'};
    for(var id in TABS){ var lab=document.querySelector('label[for="'+id+'"] .cnt'); if(!lab) continue;
      lab.textContent='('+ROWS.filter(function(r){ return F(r,TABS[id]); }).length+')';
    }
  }
  var ps=document.getElementById('projfilter'), fs=document.getElementById('fixvfilter');
  if(ps) ps.addEventListener('change', apply);
  if(fs) fs.addEventListener('change', apply);
  apply();
})();
</script>"""

# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tempo", required=True); ap.add_argument("--issues", required=True)
    ap.add_argument("--devmap", required=True); ap.add_argument("--dates")   # {issueId: latest worklog date}
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--project", default="INTRD,MACRD,PRT730")
    ap.add_argument("--keys")   # optional: restrict the report to an explicit ticket-key list (file or comma/space list); date window then ignored
    ap.add_argument("--md"); ap.add_argument("--out", required=True); ap.add_argument("--csv")
    a = ap.parse_args()
    tempo = json.load(open(a.tempo, encoding="utf-8"))
    devmap = json.load(open(a.devmap, encoding="utf-8"))
    wdates = json.load(open(a.dates, encoding="utf-8")) if a.dates and os.path.exists(a.dates) else {}
    ns = nodes(json.load(open(a.issues, encoding="utf-8")))
    rows, unknown = build_ticket_rows(ns, tempo, devmap, a.project, wdates, a.since, a.until)
    if a.keys:   # restrict to an explicit ticket list (its own tickets only; date window ignored)
        raw = open(a.keys, encoding="utf-8").read() if os.path.exists(a.keys) else a.keys
        keyset = {k.strip() for k in raw.replace(",", " ").split() if k.strip()}
        rows = [r for r in rows if r["key"] in keyset]
        import sys as _s; _s.stderr.write(f"--keys: restricted to {len(rows)}/{len(keyset)} requested tickets\n")
    if unknown:
        import sys as _sys
        tot_unk = round(sum(unknown.values())/3600, 1)
        _sys.stderr.write(f"\n*** UNKNOWN worklog authors (not in devmap): {len(unknown)} accountIds, {tot_unk} h total ***\n")
        for acc, sec in sorted(unknown.items(), key=lambda x: -x[1])[:30]:
            _sys.stderr.write(f"    {acc}  {round(sec/3600,1)} h\n")
        json.dump({a: sec for a, sec in unknown.items()}, open(os.path.join(os.path.dirname(a.out) or ".", "unknown_authors.json"), "w"))
    tot_all, _, grand_log = area_totals(rows)
    _tsub = round(sum(tot_all[ar]["subBug"] for ar in AREAS), 1)
    mons = months_of(rows)

    # ---------- Markdown (per-area totals overall + by month; per-ticket grouped by month) ----------
    md = []; P = md.append
    P(f"# Estimation vs logged, per area — {a.project}, [{a.since or '…'} … {a.until or '…'})\n")
    if not rows:
        P("_No logged time for the roster in this window._")
    else:
        P("## Totals by area\n")
        for ln in md_totals_lines(rows): P(ln)
        P(f"\n**Total across all groups:** {days(grand_log)} d logged + {days(_tsub)} d sub-bug = **{days(grand_log + _tsub)} d** total dev  (totals in days, 1 d = {DAY_HOURS} h)\n")
        P("> **AI-assisted** = AI-assisted tickets / total tickets for the area — how many of the area's tickets carry an "
          "AI-metrics record (the ticket, or a same-area sub-task, records AI usage), out of all the area's tickets.\n")
        P("### Totals by area — by month\n")
        for m in mons:
            mr = [r for r in rows if r["month"] == m]
            P(f"\n**{m}** ({len(mr)} tickets)\n")
            for ln in md_totals_lines(mr): P(ln)
        # condensed per-ticket (logged h per area), grouped by month; full matrix in the HTML/CSV
        P("\n## Per ticket, by month (logged h per area — full matrix in the HTML/CSV)\n")
        for m in mons:
            mr = [r for r in rows if r["month"] == m]
            P(f"\n### {m} ({len(mr)} tickets)\n")
            P("| Ticket | Date | Type | Status | F | Back (dev · log d) | Front (dev · log d) | QA (dev · log d) | Overhead d | Overhead people | Total d |")
            P("|---|---|---|---|:-:|---|---|---|--:|---|--:|")
            for r in mr:
                def cell(ar):
                    x = r["areas"][ar]
                    return f"{x['main']} · {days(x['logged'])}" if x["logged"] else "–"
                people = ", ".join(f"{n} {days(h)}d" for n, h in r["archprDevs"]) or "–"
                P(f"| {r['key']} | {r['date']} | {r['ttype']} | {r['status']} | {'T' if r['final'] else ''} | "
                  f"{cell('backend')} | {cell('frontend')} | {cell('qa')} | {days(r['archprH']) or '–'} | {people} | {days(r['totalLogged'])} |")
    md_text = "\n".join(md)
    if a.md: open(a.md, "w", encoding="utf-8").write(md_text)
    print(md_text)

    # ---------- CSV (full per-area matrix, flattened) ----------
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        percol = ["Main dev", "A. Est d", "DL. Est d", "Total dev d", "Logged d", "Sub-bug d", "AI",
                  "Arch gain (w bug)", "Arch gain (no bug)", "DL gain (w bug)", "DL gain (no bug)", "Sub-bugs"]
        header = ["Ticket", "Date", "Month", "Type", "Title", "Status", "Final"]
        for ar in AREAS: header += [f"{AREA_LABEL[ar]} {c}" for c in percol]
        header += ["Overhead logged d", "Overhead %", "Overhead devs", "Total logged d", "Total dev d"]
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh); w.writerow(header)
            for r in rows:
                row = [r["key"], r["date"], r["month"], r["ttype"], r["title"], r["status"], "T" if r["final"] else ""]
                for ar in AREAS:
                    x = r["areas"][ar]
                    row += [x["main"], days(x["aEst"]), days(x["dlEst"]), days(x["totalDev"]), days(x["logged"]), days(x["subBug"]),
                            "Yes" if x["ai"] else "",
                            gain_cell(x["aEst"], x["logged"] + x["subBug"]), gain_cell(x["aEst"], x["logged"]),
                            gain_cell(x["dlEst"], x["logged"] + x["subBug"]), gain_cell(x["dlEst"], x["logged"]),
                            x["bugs"]]
                row += [days(r["archprH"]), (round(r["archprH"] / r["totalLogged"] * 100) if r["totalLogged"] else ""),
                        "; ".join(f"{n} {days(h)}d" for n, h in r["archprDevs"]), days(r["totalLogged"]), days(r["totalDev"])]
                w.writerow(row)

    # ---------- HTML (wide per-area matrix) ----------
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    B = []; W = B.append
    W("<h1>Estimation vs logged — per area <span class='sm'>(all figures in days, 1 d = 8 h)</span></h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; [{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} tickets</p>')
    if not rows:
        W('<p>No logged time for the roster in this window.</p>')
    else:
        us_rows = [r for r in rows if r["ttype"] == "US"]
        us_final = [r for r in us_rows if r["final"]]
        bug_final = [r for r in rows if r["ttype"] == "Bug" and r["final"]]
        other_rows = [r for r in rows if r["ttype"] != "US"]
        projects = sorted({r["project"] for r in rows})
        fixvers = sorted({v for r in rows for v in (r.get("fixVersions") or [])})
        W('<div class="filterbar"><label><b>Project filter:</b> <select id="projfilter">'
          '<option value="all">All projects</option>'
          + "".join(f'<option value="{e(p)}">{e(p)}</option>' for p in projects)
          + '</select></label> &nbsp; <label><b>Fix version:</b> <select id="fixvfilter">'
          '<option value="all">All versions</option>'
          + "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in fixvers)
          + '</select></label> <span class="sm">filter the Totals-by-area and per-ticket rows; a Bug with several fix versions matches each; Totals recompute live.</span></div>')
        W('<div class="tabs">')
        W('<input type="radio" name="trtab" id="tab-all" checked>')
        W('<input type="radio" name="trtab" id="tab-us">')
        W('<input type="radio" name="trtab" id="tab-usfinal">')
        W('<input type="radio" name="trtab" id="tab-bugfinal">')
        W('<input type="radio" name="trtab" id="tab-other">')
        W('<div class="tabbar">'
          f'<label for="tab-all">All <span class="cnt">({len(rows)})</span></label>'
          f'<label for="tab-us">User Stories (All) <span class="cnt">({len(us_rows)})</span></label>'
          f'<label for="tab-usfinal">User Stories (Final) <span class="cnt">({len(us_final)})</span></label>'
          f'<label for="tab-bugfinal">Bugs (Final) <span class="cnt">({len(bug_final)})</span></label>'
          f'<label for="tab-other">Bugs and Others <span class="cnt">({len(other_rows)})</span></label></div>')
        W(f'<section class="panel panel-all">{html_report_body(rows, "all")}</section>')
        W(f'<section class="panel panel-us">{html_report_body(us_rows, "us")}</section>')
        W(f'<section class="panel panel-usfinal">{html_report_body(us_final, "usfinal")}</section>')
        W(f'<section class="panel panel-bugfinal">{html_report_body(bug_final, "bugfinal")}</section>')
        W(f'<section class="panel panel-other">{html_report_body(other_rows, "other")}</section>')
        W('</div>')
        # ---- data + client-side project filter (recomputes Totals-by-area, % Logged, grand total) ----
        import json as _json
        rowdata = [{"k": r["key"], "p": r["project"], "fv": r.get("fixVersions") or [], "m": r["month"], "t": r["ttype"], "f": 1 if r["final"] else 0,
                    "oh": r["archprH"],
                    "be": [r["areas"]["backend"]["aEst"], r["areas"]["backend"]["dlEst"], r["areas"]["backend"]["logged"], r["areas"]["backend"]["subBug"], r["areas"]["backend"]["bugs"], 1 if r["areas"]["backend"]["ai"] else 0],
                    "fe": [r["areas"]["frontend"]["aEst"], r["areas"]["frontend"]["dlEst"], r["areas"]["frontend"]["logged"], r["areas"]["frontend"]["subBug"], r["areas"]["frontend"]["bugs"], 1 if r["areas"]["frontend"]["ai"] else 0],
                    "qa": [r["areas"]["qa"]["aEst"], r["areas"]["qa"]["dlEst"], r["areas"]["qa"]["logged"], r["areas"]["qa"]["subBug"], r["areas"]["qa"]["bugs"], 1 if r["areas"]["qa"]["ai"] else 0]}
                   for r in rows]
        W('<script id="rowdata" type="application/json">' + _json.dumps(rowdata, separators=(",", ":")) + '</script>')
        W(PROJECT_FILTER_JS)
    W('<p class="foot">One row per ticket, with a column group per area (Backend / Frontend / QA). '
      '<b>Date</b> = the ticket\'s date (resolutiondate, else updated); tickets are selected and grouped into that month. '
      '<b>Arch gain B/F/Q &middot; OH%</b> (right after Final) is a single column giving each area\'s Architect gain <i>considering sub-bugs</i> '
      '(A.Est vs Logged + Sub-bug, in days): B = backend, F = frontend, Q = QA; <b>OH%</b> is overhead\'s share of the ticket\'s total logged hours. '
      '<b>Main dev</b> = the roster developer of that area with the most logged hours on the ticket. '
      '<b>Logged d</b> = days booked by that area\'s developers (1 d = 8 h). Time logged by <b>overhead</b> people '
      '(Architect / PO / DevOps / Consultant / management) are moved out of the areas into the <b>Overhead d</b> column, and each '
      'contributing person is named with their hours in the <b>Overhead people</b> column. '
      '<b>Sub-bug d</b> / <b>#SB</b> = days this area\'s developers logged fixing the ticket\'s child Bug/Sub-bug sub-issues, and '
      'the count of such sub-bugs they worked on (attributed by the fixer\'s area, so nothing is lost when a sub-bug has no component). '
      '<b>Total dev d</b> = Logged + Sub-bug d. <b>A.Est</b> (Architect, per-area estimate '
      'field &times;8) and <b>DL.Est</b> (Dev-lead; a US sums that area\'s child sub-task estimates, else the ticket estimate). '
      '<b>Arch/DL gain</b> = (Est&minus;Logged)/Est shown with / without sub-bug hours; green positive, red negative, "-" when meaningless. '
      'The per-ticket <b>AI</b> badge marks an area developed with AI assistance (the ticket carries an AI-metrics record for '
      'that area, or a same-area sub-task does); in the Totals, <b>AI-assisted</b> = AI-assisted tickets / total tickets for that area, and '
      '<b>% Logged</b> = that area\'s (or Overhead\'s) share of the total logged hours. '
      '<b>Total log d</b> = logged across all groups (areas + Overhead). '
      'Generated by <code>/oc-time-report</code>.</p>')
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estimation vs logged (per area) — {e(a.project)} {e(a.since or '')}…{e(a.until or '')}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --card:#fff; --accent:#2563eb; --pos:#15803d; --neg:#b91c1c; --zebra:#fafbfc;
  --back:#e8f0fe; --front:#fdefe8; --qa:#eafaf0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad;
  --line:#242a31; --head:#171b21; --card:#141821; --accent:#6ea8fe; --pos:#4ade80; --neg:#f87171; --zebra:#12161c;
  --back:#12233d; --front:#3a221a; --qa:#12301f; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
.meta {{ color:var(--muted); margin:0 0 1rem; }}
.tw {{ border:1px solid var(--line); border-radius:10px; }}
.tw.wide {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.4rem .55rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
.r {{ text-align:right; }} .c {{ text-align:center; }}
.name {{ font-weight:600; }} .sm {{ color:var(--muted); font-size:.85em; }}
.ti {{ max-width:220px; overflow:hidden; text-overflow:ellipsis; }}
.key a {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--accent); font-weight:600; text-decoration:none; }}
.key a:hover {{ text-decoration:underline; }}
.pos {{ color:var(--pos); font-weight:600; }} .neg {{ color:var(--neg); font-weight:600; }}
.dim {{ color:var(--muted); text-align:center; }}
.aibadge {{ display:inline-block; font-size:.68rem; font-weight:700; color:#fff; background:var(--accent); border-radius:4px; padding:.02rem .3rem; }}
.fin {{ display:inline-block; font-size:.68rem; font-weight:700; color:#fff; background:#16a34a; border-radius:4px; padding:.02rem .32rem; }}
.matrix th.grp {{ text-align:center; border-left:2px solid var(--line); }}
.matrix th.grp.backend {{ background:var(--back); }}
.matrix th.grp.frontend {{ background:var(--front); }}
.matrix th.grp.qa {{ background:var(--qa); }}
.matrix td.ledge, .matrix th.ledge {{ border-left:2px solid var(--line); }}
.matrix td.area-backend {{ background:color-mix(in srgb, var(--back) 30%, transparent); }}
.matrix td.area-frontend {{ background:color-mix(in srgb, var(--front) 30%, transparent); }}
.matrix td.area-qa {{ background:color-mix(in srgb, var(--qa) 30%, transparent); }}
.matrix th.gaincol, .matrix td.gaincol {{ border-left:2px solid var(--line); border-right:2px solid var(--line); white-space:nowrap; }}
.filterbar {{ margin:1rem 0 .25rem; }}
.filterbar select {{ padding:.3rem .55rem; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--fg); font:inherit; }}
td.proj {{ color:var(--muted); }}
tr.tot td {{ font-weight:700; background:var(--head); }}
td.tot {{ font-weight:700; }}
details {{ border:1px solid var(--line); border-radius:10px; margin:.4rem 0; padding:0 .6rem; }}
details[open] {{ padding-bottom:.5rem; }}
summary {{ cursor:pointer; font-weight:600; padding:.5rem .2rem; }}
summary .cnt {{ color:var(--muted); font-weight:400; font-size:.9em; }}
details .tw {{ margin:.35rem 0 .4rem; }}
.bm {{ color:var(--muted); font-size:.72rem; margin:.6rem 0 .2rem; text-transform:uppercase; letter-spacing:.05em; }}
.tabs > input {{ position:absolute; opacity:0; width:0; height:0; }}
.tabbar {{ display:flex; flex-wrap:wrap; gap:.25rem; border-bottom:2px solid var(--line); margin:1rem 0 0; }}
.tabbar label {{ padding:.5rem 1rem; cursor:pointer; color:var(--muted); font-weight:600;
  border:1px solid transparent; border-bottom:none; border-radius:8px 8px 0 0; margin-bottom:-2px; }}
.tabbar label .cnt {{ font-weight:400; }}
#tab-all:checked ~ .tabbar label[for="tab-all"],
#tab-us:checked ~ .tabbar label[for="tab-us"],
#tab-usfinal:checked ~ .tabbar label[for="tab-usfinal"],
#tab-bugfinal:checked ~ .tabbar label[for="tab-bugfinal"],
#tab-other:checked ~ .tabbar label[for="tab-other"] {{ color:var(--fg); background:var(--card);
  border-color:var(--line); border-bottom:2px solid var(--card); }}
.panel {{ display:none; padding-top:.5rem; }}
#tab-all:checked ~ .panel-all {{ display:block; }}
#tab-us:checked ~ .panel-us {{ display:block; }}
#tab-usfinal:checked ~ .panel-usfinal {{ display:block; }}
#tab-bugfinal:checked ~ .panel-bugfinal {{ display:block; }}
#tab-other:checked ~ .panel-other {{ display:block; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
.foot code {{ background:var(--head); padding:.05rem .3rem; border-radius:4px; }}
</style></head><body>
{"".join(B)}
</body></html>"""
    open(a.out, "w", encoding="utf-8").write(doc)
    print(f"\nWrote {a.out}")
    if a.csv: print(f"Wrote {a.csv}")

    # ---------- second report: finished-US per-developer summary ----------
    summ_html = _summary_path(a.out, "us-summary")
    summ_csv = _summary_path(a.csv, "us-summary") if a.csv else None
    n_recs, summ_mons = write_us_summary(rows, summ_html, summ_csv, a.project, a.since, a.until)
    print(f"Wrote {summ_html}" + (f" + {summ_csv}" if summ_csv else "")
          + f"  ({n_recs} finished-US developer-area records across {len(summ_mons)} month(s))")

if __name__ == "__main__":
    main()
```

## Notes & limitations

- **Ticket selection = date, worklogs = all-time.** The window filters **tickets** by `resolutiondate` (else `updated`); for a selected ticket, **all** worklogs (any date) count, so a ticket's logged total matches Jira `aggregatetimespent`. Tempo is therefore fetched all-time per user, and the aggregator applies the date window to the ticket, not to the worklogs.
- **Tempo cache.** `fetch_tempo_users.py --cache` keeps a month-bucketed cache outside the scratchpad; only the recent ~45 days are re-fetched each run (older months are immutable — time can't be logged that far back), so after the first cold build the Tempo step is near-instant. Delete the cache file to force a full rebuild.
- **HTML project filter.** The picklist and per-tab recompute are done in the browser from a JSON blob of the per-ticket rows embedded in the page; it changes only what's displayed, never the underlying data or the CSV.
- **Overhead bucket.** Roster area `overhead` (roles ARCHI / PO / DEVOPS / CONSULTANT / NONE) is never an area developer; all their logged hours go to the **Overhead** column (itemised per person in **Overhead people**) and they are excluded from the finished-US per-developer summary.
- **Tempo token visibility.** On this instance `TEMPO_API_TOKEN` has **organisation-wide** worklog visibility — the per-user endpoint returns worklogs for **every** roster area. A missing area means those developers had no worklogs on in-window tickets, not a permission gap.
- **Unknown authors.** With a complete roster, `tempo.json` only carries known accountIds. If someone logs time who is not in `devmap.json`, add them (resolve via the full directory) so their hours are attributed rather than dropped.
- **Read-only** — the command never writes to Jira, Tempo or git; all calls are read-only.

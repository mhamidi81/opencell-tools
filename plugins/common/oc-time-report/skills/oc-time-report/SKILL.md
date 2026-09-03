---
name: oc-time-report
description: Produce an estimation-vs-logged-hours report over a period, independent of the AI-usage JSON. Tempo-worklog driven, TICKET-based with PER-AREA columns — one row per ticket, a column group for each area (Backend/Frontend/QA) giving that area's main developer, Architect & Dev-lead estimates, logged & sub-bug hours, AI flag, two time gains (with/without sub-bugs) and sub-bug count, plus an Architect/PR/mgmt logged column and a total; each area's main dev is its top contributor by dev+sub-bug hours, and a multi-role reviewer's hours go to the Arch/PR column. Tickets carry a Date (latest worklog date) and are grouped by month; the HTML has five tabs (All, User Stories All/Final, Bugs Final, Bugs and Others). Also writes a second finished-User-Story per-developer summary (per area, split by AI, by month). Prints Markdown and writes date-stamped HTML + CSV to ./docs/. Fetches Jira via direct REST (mandatory JIRA_API_TOKEN) and Tempo per-user (mandatory TEMPO_API_TOKEN) — no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH] [--csv PATH]"
---

## Purpose

A team **estimation-vs-actual** report. Unlike `/oc-ai-report`, this one is **not** tied to the AI-usage JSON field — it is driven by **Tempo worklogs** and is **ticket-based with per-area columns**: one row per ticket, with a **column group for each of the three areas** (Backend / Frontend / QA), comparing each area's estimate to its actual logged time.

Fixed columns per row: **Ticket · Date · Type · Title · Status · Final**. Then, **for each area**, a group of: **Main dev · A. Est h · DL. Est h · Total dev h · Logged h · Sub-bug h · AI · Arch gain (with · without bugs) · DL gain (with · without bugs) · #Sub-bugs**. Then two closing columns: **Arch/PR h** and **Total log h**.

- **Main dev** (per area) — the area's roster developer with the **most total work on the ticket** = non-bug logged + their own **sub-bug-fixing** hours. So a genuine bug-fixer outranks someone who only did a token review/touch on the parent. (A US worked by all three areas therefore credits three developers.)
- **Date** — the ticket's **latest Tempo worklog date** (last activity); tickets are **grouped by that month**. The report window (`--since/--until`) is applied to worklog dates at fetch time.
- **Logged h** (per area) — non-bug Tempo hours booked by that area's developers. A **multi-role Architect/PR-review developer** (`archpr`) who is **not** their area's main dev on the ticket has their non-bug hours moved to the **Arch/PR h** column instead (so per-area numbers reflect real development, not review).
- **Sub-bug h / #Sub-bugs** — hours that area's developers logged fixing the ticket's child Bug/Sub-bug sub-issues, and the count of such sub-bugs they worked on (attributed by the **fixer's area**, so nothing is lost when a sub-bug has no component).
- **Total dev h** (per area) = Logged h + Sub-bug h.
- **A. Est h** (Architect) — the area's per-area estimate custom field (days ×8), else the ticket's own estimate. **DL. Est h** (Dev-lead) — a US sums that area's child sub-task estimates (sub-bugs excluded), else the ticket's estimate.
- **Arch gain / DL gain** — `(Est − (Logged+Sub-bug h))/Est` **with** bugs, then `(Est − Logged)/Est` **without** bugs, per area. A gain shows as **`-`** when meaningless (placeholder estimate ≤0.5h, no logged time, magnitude beyond ±1000%); green positive / red negative in the HTML.
- **AI** (per area) — a badge when that area has an AI-metrics record on the ticket (or a same-area sub-task carries the field). Totals show **AI-assisted** = AI-assisted tickets / total tickets per area.
- **Status / Final** — the ticket's Jira status and a **T** flag when terminal for its type (Bug: Done/Invalid; US: Ready for Sprint review / Need documentation / Ready for release / Released; others: Done).
- **Arch/PR h** — non-bug hours from multi-role (`archpr`) developers reviewing/architecting a ticket they don't own. **Total log h** — logged across all groups (areas + Arch/PR).

Output: a compact **Markdown** printout (Totals by area overall + by month, then a condensed per-ticket table grouped by month), plus a styled **HTML** file (the full wide per-area matrix, with the report split into **five tabs** — All · User Stories (All) · User Stories (Final) · Bugs (Final) · Bugs and Others — each showing Totals-by-area overall + expandable per-month, and the per-ticket matrix grouped by month) and a **CSV** (the full matrix flattened), all date-stamped in `./docs/`. Users/developers are ordered **by area, then name**.

**Second report — finished-US per-developer summary.** The same run also writes `time-report-<TODAY>-us-summary.html` and `…-us-summary.csv` (derived from `--out`/`--csv` by inserting `-us-summary`). It considers **only User Stories in a final status**, credited to **each area's main developer** (up to three per US). The HTML has **two tabs**: **By month** (date → user: overall AI-true / AI-false tables plus an expandable per-month block) and **By developer** (user → date: each developer, ordered by area then name, expands to a month-by-month table of their finished US). Dev-table columns: **Developer · Area · US (final) · Avg sub-bugs / US · Sum A. Est h · Sum logged h · Sum sub-bug h · Sum total h · Gain (with sub-bugs) · Gain (no sub-bugs)**, each ending with a **Total** row (**Avg sub-bugs / US = total sub-bugs ÷ total US**). The CSV carries a leading **Month** and **AI assisted** column.

## Access

Both tokens are **mandatory** and read from the environment (never passed on the command line). If either is missing, tell the user how to create it and **stop**.

- **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token from *id.atlassian.com → Security → API tokens*. All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `jira_fetch.py` below. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql` in this report** — it force-includes each issue's full `description` and caps at ~5 issues/call with no cursor, which cannot fetch the thousands of tickets a real window needs. Direct REST honours the `fields` list (excludes `description`), returns 100/page and paginates via `nextPageToken`, so the whole fetch is one scripted job.
- **`TEMPO_API_TOKEN`** (each developer's own token, *Tempo → Settings → API keys*, worklog **read** scope) — logged hours are the whole point. Fetched **per-user** (`/worklogs/user/{accountId}`), which has org-wide visibility across all areas.

## Arguments

Parse `$ARGUMENTS` — all optional. Bare `/oc-time-report` = **last 30 days**, project **INTRD**.

- `--since YYYY-MM-DD` — start (inclusive). Default: 30 days before `--until`.
- `--until YYYY-MM-DD` — end (exclusive). Default: tomorrow.
- `--project KEY` — Jira project. Default `INTRD`.
- `--out PATH` — HTML output. Default `./docs/time-report-<TODAY>.html`.
- `--csv PATH` — CSV output. Default `./docs/time-report-<TODAY>.csv`.

Compute dates with `date -u +%Y-%m-%d` etc.; echo the resolved window back to the user.

## Developer roster (name → area)

Area is per developer. Resolve each name to a Jira **accountId** via Jira REST user search — `GET https://opencellsoft.atlassian.net/rest/api/3/user/search?query=<name>` (Basic auth `JIRA_EMAIL:JIRA_API_TOKEN`), pick the active `@opencellsoft.com` account whose `displayName` best matches (names below may differ slightly; warn on any you cannot resolve). Write the resolved map to `devmap.json` as `{ "<accountId>": {"name": "<display>", "area": "backend|frontend|qa", "archpr": true|false} }`. Set **`archpr: true`** for the multi-role developers who also do **Architect / PR-review / management** work (see table); everyone else `false`. (If a `devmap.json` from a previous run already covers the roster, reuse it — accountIds are stable.)

| Developer | Area |
|---|---|
| Mohamed Amtiou | qa |
| Rajae Halabi | qa |
| Brahim Aachiq | qa |
| Souhayla Msellek | qa |
| Mohamed Hamidi | frontend + **archpr** (PR review, Architect) |
| Mohamed Houssa | frontend |
| Oussama El Idrissi | frontend |
| Aissam Bahari | frontend |
| Vladimir Morev | frontend |
| Abdelmounaim Akakid | backend |
| Anas Rouaguebe | backend |
| Tarik Fakhouri | backend |
| Z Bariki | backend |
| Adil El Jaouhari | backend + **archpr** (PR review) |
| M Stitane | backend |
| Hatim Oudad | backend |
| Zakaria El Meliani | backend |
| Andrius Karpavicius | backend |
| Mohamed El Azzouzi | backend |
| Rachid Ait Yazza | backend + **archpr** (Architect) |
| E Znibar | backend |
| Amine Tazi | backend |
| Maria Ait Brahim | backend |
| Mounir Boukaya | backend |
| Abdelhadi Nasseh | backend |
| Mbarek Ait Yazza | backend |
| Abdelatif Bari | backend |

## Task 1 — Resolve the roster to accountIds

Resolve each roster name via Jira REST user search (`GET /rest/api/3/user/search?query=<name>`, Basic auth `JIRA_EMAIL:JIRA_API_TOKEN`) and build `devmap.json`; or reuse an existing `devmap.json` (accountIds are stable). Keep only successfully resolved developers and list any unresolved names in the report's Notes. (Tempo is fetched per-user directly from `devmap.json`, so no separate accountId list is needed.)

## Task 2 — Fetch Tempo worklogs for the window (Pass T)

Fetch **per-user** (not the bulk `/worklogs` endpoint — that only surfaces some authors). Write `fetch_tempo_users.py` (below) to scratchpad and run it against `devmap.json`. It iterates each roster accountId, pages `GET https://api.tempo.io/4/worklogs/user/{accountId}?from=<SINCE>&to=<UNTIL-1day>` (Tempo `to` is inclusive; pass the last in-window day, following `metadata.next`), and writes:
- `tempo.json` — `{ "<issueId>": { "<accountId>": seconds } }`
- `worklog_ids.txt` — the distinct worklogged **issue ids**, comma-separated.
- `wdates.json` — `{ "<issueId>": "<latest worklog date>" }` (used for the ticket **Date** column and month grouping).

```bash
python "<SCRATCHPAD>/fetch_tempo_users.py" --devmap "<SCRATCHPAD>/devmap.json" \
  --from [SINCE] --to [UNTIL-1day] --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt" \
  --dates-out "<SCRATCHPAD>/wdates.json"
```

It prints a per-developer worklog/issue count to stderr; report which developers actually had worklogs. If Tempo returns nothing, tell the user and stop. (Most logged time is cross-project — INTRD + SUPS support + others; the aggregator keeps only project-`INTRD` tickets, so the ticket report is a subset of the raw logged hours.)

## Task 3 — Fetch ticket metadata (Jira, direct REST)

The rows are at **parent-ticket** granularity, so we need each worklogged issue plus its parent chain and the parents' full sub-task lists. Write `jira_fetch.py` (below) to scratchpad and run it — it does all three fetch phases against the Jira REST enhanced-search endpoint (fields-limited, `description` excluded, 100/page, `nextPageToken` paging) and writes `issues.json`:

```bash
python "<SCRATCHPAD>/jira_fetch.py" --ids "<SCRATCHPAD>/worklog_ids.txt" --project [PROJECT] \
  --out "<SCRATCHPAD>/issues.json"
```

The script: (1) fetches metadata for every worklogged issue id (`id in (…)`, batched by 100), (2) fetches any `fields.parent.key` not already present (for roll-up), (3) fetches all sub-tasks of the project's Story/Enabler parents (`parent in (…)`) so Dev-lead estimate & bug counts see every sub-task. It requests fields `["summary","issuetype","status","components","timeoriginalestimate","timespent","parent","customfield_10157","customfield_10158","customfield_10189","customfield_10745"]` and writes `{issues:{nodes:[…]}}` keyed with the numeric `id` (the aggregator joins Tempo by id).

- `status` drives the **Status** column and the **Final** flag: a ticket is *final* when its Jira status (case-insensitive) is terminal for its type — **Bug**: Done / Invalid; **US**: Ready for Sprint review / Need documentation / Ready for release / Released; **any other type**: Done. The finished-User-Story summary counts only US with Final = true.
- `customfield_10745` is the **"AI metrics"** field: its presence marks an area as **developed with AI assistance** (per-ticket **AI** badge; aggregated as **AI-assisted** = AI-assisted tickets / total tickets per area); an area is flagged when the ticket carries a record for that domain, or a same-area sub-task carries the field.
- Estimate custom fields are `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate* (days).

## Task 4 — Aggregate & render

Write `time_report.py` (below) and run it:

```bash
python "<SCRATCHPAD>/time_report.py" --tempo "<SCRATCHPAD>/tempo.json" --issues "<SCRATCHPAD>/issues.json" \
  --devmap "<SCRATCHPAD>/devmap.json" --dates "<SCRATCHPAD>/wdates.json" --since [SINCE] --until [UNTIL] --project [PROJECT] \
  --md "<SCRATCHPAD>/report.md" --out "./docs/time-report-[TODAY].html" --csv "./docs/time-report-[TODAY].csv"
```

Show the Markdown (`report.md`) to the user and report the HTML + CSV paths, **plus the second report** it also writes — a finished-User-Story per-developer summary at `./docs/time-report-[TODAY]-us-summary.{html,csv}`.

### `fetch_tempo_users.py`

```python
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
BASE="https://api.tempo.io/4"
def fetch_user(acc, tok, frm, to):
    per_issue={}      # issueId -> seconds
    last_date={}      # issueId -> latest worklog startDate (YYYY-MM-DD)
    url=f"{BASE}/worklogs/user/{urllib.parse.quote(acc,safe='')}?from={frm}&to={to}&limit=1000"
    n=0
    while url:
        req=urllib.request.Request(url, headers={"Authorization":f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: data=json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"  {acc}: HTTP {ex.code}\n"); return per_issue, last_date, n, ex.code
        for w in data.get("results") or []:
            iid=str(((w.get("issue") or {}).get("id")))
            sec=w.get("timeSpentSeconds") or 0
            d=w.get("startDate") or ""
            if iid and iid!="None":
                per_issue[iid]=per_issue.get(iid,0)+sec; n+=1
                if d and d>last_date.get(iid,""): last_date[iid]=d
        url=(data.get("metadata") or {}).get("next")
    return per_issue, last_date, n, 200

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--devmap",required=True); ap.add_argument("--from",dest="frm",required=True)
    ap.add_argument("--to",required=True); ap.add_argument("--out",required=True); ap.add_argument("--ids-out",required=True)
    ap.add_argument("--dates-out")   # optional: {issueId: latest worklog date}
    a=ap.parse_args()
    tok=os.environ.get("TEMPO_API_TOKEN")
    if not tok: sys.stderr.write("no token\n"); sys.exit(1)
    dev=json.load(open(a.devmap,encoding="utf-8"))
    tempo={}   # issueId -> {acc: secs}
    dates={}   # issueId -> latest worklog date
    for acc,info in dev.items():
        per,ld,cnt,code=fetch_user(acc,tok,a.frm,a.to)
        for iid,sec in per.items():
            tempo.setdefault(iid,{})[acc]=tempo.get(iid,{}).get(acc,0)+sec
        for iid,d in ld.items():
            if d>dates.get(iid,""): dates[iid]=d
        sys.stderr.write(f"{info['area']:8} {info['name']:26} {cnt:5} worklogs, {len(per):4} issues\n")
    json.dump(tempo, open(a.out,"w"))
    open(a.ids_out,"w").write(",".join(tempo.keys()))
    if a.dates_out: json.dump(dates, open(a.dates_out,"w"))
    sys.stderr.write(f"TOTAL distinct worklogged issues: {len(tempo)}\n")

if __name__=="__main__": main()
```

### `jira_fetch.py`

```python
#!/usr/bin/env python3
"""Fetch INTRD ticket metadata via direct Jira Cloud REST (enhanced JQL search).
Honours `fields` (excludes description), paginates via nextPageToken. Auth: email:JIRA_API_TOKEN."""
import os, sys, json, time, base64, urllib.request, urllib.error
BASE="https://opencellsoft.atlassian.net"
EMAIL=os.environ.get("JIRA_EMAIL") or "andrius.karpavicius@opencellsoft.com"
TOK=os.environ["JIRA_API_TOKEN"]
AUTH=base64.b64encode(f"{EMAIL}:{TOK}".encode()).decode()
FIELDS=["summary","issuetype","status","components","timeoriginalestimate","timespent","parent",
        "customfield_10157","customfield_10158","customfield_10189","customfield_10745"]

def post(path, body):
    for attempt in range(5):
        req=urllib.request.Request(BASE+path, data=json.dumps(body).encode(),
            headers={"Authorization":f"Basic {AUTH}","Accept":"application/json","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code in (429,503):
                time.sleep(2*(attempt+1)); continue
            sys.stderr.write(f"HTTP {ex.code}: {ex.read()[:200]}\n"); raise
    raise RuntimeError("retries exhausted")

def fetch_jql(jql):
    nodes=[]; token=None
    while True:
        body={"jql":jql,"fields":FIELDS,"maxResults":100}
        if token: body["nextPageToken"]=token
        d=post("/rest/api/3/search/jql", body)
        nodes+= d.get("issues") or []
        if d.get("isLast") or not d.get("nextPageToken"): break
        token=d["nextPageToken"]
    return nodes

def slim(n):
    f=n.get("fields") or {}
    p=f.get("parent") or {}
    return {"id":n["id"],"key":n["key"],"fields":{
        "summary":f.get("summary"),"issuetype":{"name":(f.get("issuetype") or {}).get("name")},
        "status":{"name":(f.get("status") or {}).get("name")},"components":f.get("components") or [],
        "timeoriginalestimate":f.get("timeoriginalestimate"),"timespent":f.get("timespent"),
        "parent":{"key":p.get("key")} if p.get("key") else None,
        "customfield_10157":f.get("customfield_10157"),"customfield_10158":f.get("customfield_10158"),
        "customfield_10189":f.get("customfield_10189"),"customfield_10745":f.get("customfield_10745")}}

def batched(seq,n):
    for i in range(0,len(seq),n): yield seq[i:i+n]

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)      # file: comma-separated worklogged issue ids
    ap.add_argument("--out", required=True)       # issues.json
    ap.add_argument("--project", default="INTRD")
    a=ap.parse_args()
    PROJ=a.project
    wl=[x for x in open(a.ids).read().split(",") if x]
    by_id={}
    # Phase 1: metadata for every worklogged issue (all projects) by id
    for i,b in enumerate(batched(wl,100)):
        for n in fetch_jql("id in ("+",".join(b)+")"):
            by_id[str(n["id"])]=slim(n)
        if i%10==0: sys.stderr.write(f"  worklog batch {i}: {len(by_id)} nodes\n")
    sys.stderr.write(f"Phase1 done: {len(by_id)} worklogged issues\n")
    by_key={v["key"]:v for v in by_id.values()}
    # Phase 2: parents (for roll-up) not already fetched
    pkeys=set()
    for v in by_id.values():
        pk=(v["fields"].get("parent") or {}).get("key")
        if pk and pk not in by_key: pkeys.add(pk)
    pkeys=sorted(pkeys)
    for i,b in enumerate(batched(pkeys,100)):
        for n in fetch_jql("key in ("+",".join(b)+")"):
            s=slim(n); by_id[str(n["id"])]=s; by_key[s["key"]]=s
    sys.stderr.write(f"Phase2 done: +{len(pkeys)} parents, total {len(by_id)}\n")
    # Phase 3: all sub-tasks of PROJECT Story/Enabler parents (for DL est + bug counts)
    story_parents=sorted({v["key"] for v in list(by_id.values())
        if v["key"].startswith(PROJ+"-") and (v["fields"]["issuetype"]["name"] or "") in ("Story","Enabler")})
    seen=set(by_id)
    for i,b in enumerate(batched(story_parents,60)):
        for n in fetch_jql("parent in ("+",".join(b)+")"):
            if str(n["id"]) not in seen:
                s=slim(n); by_id[str(n["id"])]=s
        if i%10==0: sys.stderr.write(f"  subtask batch {i}: total {len(by_id)}\n")
    sys.stderr.write(f"Phase3 done: total {len(by_id)} nodes\n")
    json.dump({"issues":{"nodes":list(by_id.values())}}, open(a.out,"w",encoding="utf-8"))
    inp=sum(1 for v in by_id.values() if v["key"].startswith(PROJ+"-"))
    sys.stderr.write(f"WROTE {a.out}: {len(by_id)} total, {inp} {PROJ}\n")

if __name__=="__main__": main()
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

def build_ticket_rows(all_nodes, tempo, devmap, project, wdates=None):
    wdates = wdates or {}
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
        else:
            for acc, sec in per.items():
                if acc in devmap: tk[tkey]["devLogged"][acc] += sec

    rows = []
    for tkey, agg in tk.items():
        if project and not str(tkey).startswith(project + "-"): continue
        tnode = by_key.get(tkey)
        if not tnode: continue
        tf = tnode.get("fields") or {}
        if not agg["devLogged"] and not agg["subbugs"]: continue
        ttype = ticket_type(tf); status = status_of(tf); final = is_final(ttype, status)
        pa = area_of(tf); rec = record_domains(tf)

        # sub-bugs attributed by the FIXER's roster area (dev-centric, like Logged h): a developer's
        # sub-bug-fixing hours count toward their area's Sub-bug h and toward being that area's main
        # dev; a sub-bug counts once per area that worked on it. (Nothing is dropped for lacking a component.)
        area_sub_h = {ar: 0.0 for ar in AREAS}; area_bug_ct = {ar: 0 for ar in AREAS}
        sub_dev = defaultdict(lambda: defaultdict(float))
        for b in agg["subbugs"].values():
            touched = set()
            for acc, sec in b["perdev"].items():
                ar = devmap[acc]["area"]; area_sub_h[ar] += sec; sub_dev[ar][acc] += sec; touched.add(ar)
            for ar in touched: area_bug_ct[ar] += 1

        # main developer per area = the area's roster dev with the most TOTAL work on the ticket
        # (non-bug logged + their own sub-bug-fixing hours) — so a real bug-fixer outranks someone
        # who only did a token review/touch on the parent.
        by_area_dev = defaultdict(dict)
        for acc, sec in agg["devLogged"].items():
            by_area_dev[devmap[acc]["area"]][acc] = by_area_dev[devmap[acc]["area"]].get(acc, 0) + sec
        for ar in AREAS:
            for acc, sec in sub_dev.get(ar, {}).items():
                by_area_dev[ar][acc] = by_area_dev[ar].get(acc, 0) + sec
        main = {ar: max(d, key=lambda a: d[a]) for ar, d in by_area_dev.items() if d}

        # attribute each developer's NON-BUG logged hours: own area, except a multi-role dev who is
        # NOT their area's main dev on this ticket -> Architect/PR/mgmt bucket.
        area_logged = {ar: 0.0 for ar in AREAS}; archpr_logged = 0.0; archpr_devs = {}
        for acc, sec in agg["devLogged"].items():
            ar = devmap[acc]["area"]
            if devmap[acc].get("archpr") and main.get(ar) != acc:
                archpr_logged += sec; archpr_devs[devmap[acc]["name"]] = archpr_devs.get(devmap[acc]["name"], 0.0) + sec
            else:
                area_logged[ar] += sec

        # estimates per area
        vals = {ar: tf.get(AREA_EST_FIELD[ar]) for ar in AREAS}
        any_area_est = any(isinstance(v, (int, float)) for v in vals.values())
        area_aest = {ar: 0.0 for ar in AREAS}; area_dlest = {ar: 0.0 for ar in AREAS}
        for ar in AREAS:
            if any_area_est:
                v = vals[ar]; est = round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
                area_aest[ar] = 0.0 if 0 < est < EST_MIN else est
            elif ar == pa:
                area_aest[ar] = hours(tf.get("timeoriginalestimate"))
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
        date = agg["date"]; month = (date or "")[:7] or "no-date"
        rows.append({"key": tkey, "ttype": ttype, "title": (tf.get("summary") or "")[:60],
                     "status": status, "final": final, "date": date, "month": month, "areas": areas_out,
                     "archprH": archpr_h, "archprDevs": sorted(archpr_devs, key=lambda n: -archpr_devs[n]),
                     "totalLogged": total_logged, "totalDev": total_dev,
                     "aiAny": any(areas_out[ar]["ai"] for ar in AREAS),
                     "bugsTotal": sum(area_bug_ct[ar] for ar in AREAS)})
    rows.sort(key=lambda r: (r["date"], r["totalLogged"]), reverse=True)   # newest activity first
    return rows

# ---------- per-area totals (across tickets) ----------
def area_totals(rows):
    tot = {ar: {"tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "subBug": 0.0, "bugs": 0, "ai": 0} for ar in AREAS}
    archpr = 0.0; grand_log = 0.0
    for r in rows:
        for ar in AREAS:
            a = r["areas"][ar]
            if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                g = tot[ar]; g["tickets"] += 1
                for k in ("aEst", "dlEst", "logged", "subBug", "bugs"): g[k] += a[k]
                g["ai"] += int(a["ai"])
        archpr += r["archprH"]; grand_log += r["totalLogged"]
    return tot, round(archpr, 1), round(grand_log, 1)

def months_of(rows):
    return sorted({r["month"] for r in rows}, reverse=True)

# ---------- shared renderers (reused for the overall view and per month) ----------
def md_totals_lines(rows):
    tot, archpr_tot, grand_log = area_totals(rows)
    out = ["| Area | Tickets | A. Est h | DL. Est h | Total dev h | Logged h | Sub-bug h | AI-assisted | Arch gain | DL gain | Sub-bugs |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for ar in AREAS:
        g = tot[ar]
        out.append(f"| {AREA_LABEL[ar]} | {g['tickets']} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
                   f"{round(g['logged'] + g['subBug'],1)} | {round(g['logged'],1)} | {round(g['subBug'],1)} | {g['ai']}/{g['tickets']} | "
                   f"{gain_two(g['aEst'], g['logged'], g['subBug'])} | {gain_two(g['dlEst'], g['logged'], g['subBug'])} | {g['bugs']} |")
    out.append(f"| Architect/PR/mgmt | – | – | – | {archpr_tot} | {archpr_tot} | – | – | – | – | – |")
    out.append(f"| **Total** | | | | **{grand_log}** | **{grand_log}** | | | | | |")
    return out

def html_totals_table(rows):
    tot, archpr_tot, grand_log = area_totals(rows)
    h = ["<div class=\"tw\"><table><thead><tr>"
         "<th>Area</th><th class='r'>Tickets</th><th class='r'>A. Est h</th><th class='r'>DL. Est h</th>"
         "<th class='r'>Total dev h</th><th class='r'>Logged h</th><th class='r'>Sub-bug h</th><th class='r'>AI-assisted</th>"
         "<th class='r'>Arch gain</th><th class='r'>DL gain</th><th class='r'>Sub-bugs</th></tr></thead><tbody>"]
    for ar in AREAS:
        g = tot[ar]
        h.append(f"<tr><td class='name'>{AREA_LABEL[ar]}</td><td class='r'>{g['tickets']}</td>"
                 f"<td class='r'>{round(g['aEst'],1)}</td><td class='r'>{round(g['dlEst'],1)}</td>"
                 f"<td class='r'>{round(g['logged']+g['subBug'],1)}</td><td class='r'>{round(g['logged'],1)}</td>"
                 f"<td class='r'>{round(g['subBug'],1)}</td><td class='r'>{g['ai']}/{g['tickets']}</td>"
                 f"<td class='r'>{gain_two_html(g['aEst'],g['logged'],g['subBug'])}</td>"
                 f"<td class='r'>{gain_two_html(g['dlEst'],g['logged'],g['subBug'])}</td><td class='r'>{g['bugs']}</td></tr>")
    h.append(f"<tr><td class='name'>Architect/PR/mgmt</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>{archpr_tot}</td><td class='r'>{archpr_tot}</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td></tr>")
    h.append(f"<tr class='tot'><td class='name'>Total</td><td></td><td></td><td></td>"
             f"<td class='r'>{grand_log}</td><td class='r'>{grand_log}</td><td></td><td></td><td></td><td></td><td></td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)

MATRIX_SUB = ["Main dev", "A.Est", "DL.Est", "Tot dev", "Logged", "Sub-bug h", "AI", "Arch gain", "DL gain", "#SB"]
def html_matrix_head():
    head1 = ['<th rowspan="2">Ticket</th><th rowspan="2">Date</th><th rowspan="2">Type</th><th rowspan="2">Title</th>'
             '<th rowspan="2">Status</th><th rowspan="2" class="c">F</th>']
    for ar in AREAS:
        head1.append(f'<th colspan="{len(MATRIX_SUB)}" class="grp {ar}">{AREA_LABEL[ar]}</th>')
    head1.append('<th rowspan="2" class="r">Arch/PR h</th><th rowspan="2" class="r">Total log h</th>')
    head2 = []
    for ar in AREAS:
        for i, s in enumerate(MATRIX_SUB):
            cls = "c" if s == "AI" else ("" if s == "Main dev" else "r")
            head2.append(f'<th class="{cls}{" ledge" if i == 0 else ""}">{e(s)}</th>')
    return '<thead><tr>' + "".join(head1) + "</tr><tr>" + "".join(head2) + "</tr></thead>"

def html_matrix_body(rows):
    out = []
    for r in rows:
        tds = [f'<td class="key"><a href="https://opencellsoft.atlassian.net/browse/{e(r["key"])}" target="_blank" rel="noopener">{e(r["key"])}</a></td>'
               f'<td class="sm">{e(r["date"] or "–")}</td>'
               f'<td>{e(r["ttype"])}</td><td class="ti">{e(r["title"])}</td><td>{e(r["status"])}</td>'
               f'<td class="c">{"<span class=fin>T</span>" if r["final"] else ""}</td>']
        for ar in AREAS:
            x = r["areas"][ar]; blank = not (x["logged"] or x["subBug"] or x["aEst"] or x["dlEst"] or x["main"])
            if blank:
                tds.append(f'<td class="ledge dim area-{ar}" colspan="{len(MATRIX_SUB)}">&ndash;</td>'); continue
            tds.append(f'<td class="name ledge area-{ar}">{e(x["main"])}</td>'
                       f'<td class="r area-{ar}">{x["aEst"]}</td><td class="r area-{ar}">{x["dlEst"]}</td>'
                       f'<td class="r area-{ar}">{x["totalDev"]}</td><td class="r area-{ar}">{x["logged"]}</td><td class="r area-{ar}">{x["subBug"]}</td>'
                       f'<td class="c area-{ar}">{"<span class=aibadge>AI</span>" if x["ai"] else ""}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["aEst"], x["logged"], x["subBug"])}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["dlEst"], x["logged"], x["subBug"])}</td><td class="r area-{ar}">{x["bugs"]}</td>')
        arch = f'{r["archprH"]}' + (f'<span class="sm"> {e(", ".join(r["archprDevs"]))}</span>' if r["archprDevs"] else "")
        tds.append(f'<td class="r">{arch if r["archprH"] else "&ndash;"}</td><td class="r tot">{r["totalLogged"]}</td>')
        out.append("<tr>" + "".join(tds) + "</tr>")
    return "".join(out)

def html_report_body(rs):
    """Full report body (Totals by area overall + by month, then the per-ticket matrix grouped
    by month) for a subset of rows — used inside each tab panel."""
    if not rs:
        return '<p class="dim" style="padding:1rem">No tickets of this type in this window.</p>'
    _, _, grand = area_totals(rs)
    ms = months_of(rs)
    h = []; w = h.append
    w("<h2>Totals by area</h2>")
    w(html_totals_table(rs))
    w(f'<p class="meta"><b>Total logged across all groups:</b> {grand} h</p>')
    w('<p class="bm">By month</p>')
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} tickets)</span></summary>{html_totals_table(mr)}</details>')
    w("<h2>Per ticket &mdash; per-area columns</h2>")
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} tickets)</span></summary>'
          f'<div class="tw wide"><table class="matrix">{html_matrix_head()}<tbody>{html_matrix_body(mr)}</tbody></table></div></details>')
    return "".join(h)

# ---------- second report: finished-US per-developer summary ----------
US_COLS = [("dev", "Developer"), ("area", "Area"), ("nUS", "US (final)"),
           ("avgSub", "Avg sub-bugs / US"), ("sumAEst", "Sum A. Est h"), ("sumLogged", "Sum logged h"),
           ("sumSub", "Sum sub-bug h"), ("sumTotal", "Sum total h"),
           ("gainBug", "Gain (with sub-bugs)"), ("gainNoBug", "Gain (no sub-bugs)")]
US_NUM = {"nUS", "avgSub", "sumAEst", "sumLogged", "sumSub", "sumTotal", "gainBug", "gainNoBug"}

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
UMONTH_COLS = [("month", "Month"), ("nUS", "US (final)"), ("aiUS", "AI US"), ("avgSub", "Avg sub-bugs / US"),
               ("sumAEst", "Sum A. Est h"), ("sumLogged", "Sum logged h"), ("sumSub", "Sum sub-bug h"),
               ("sumTotal", "Sum total h"), ("gainBug", "Gain (with sub-bugs)"), ("gainNoBug", "Gain (no sub-bugs)")]
UMONTH_NUM = {"nUS", "aiUS", "avgSub", "sumAEst", "sumLogged", "sumSub", "sumTotal", "gainBug", "gainNoBug"}

def _umonth_cells(d):
    out = []
    for k, _ in UMONTH_COLS:
        if k in ("gainBug", "gainNoBug"):
            out.append(f'<td class="r {gain_cls(d[k])}">{gain_str(d[k])}</td>')
        elif k == "month":
            out.append(f'<td class="name">{e(d[k])}</td>')
        else:
            out.append(f'<td class="r">{d[k]}</td>')
    return "".join(out)

def _us_by_user_html(recs):
    """Per developer (area, then name), expandable month-by-month breakdown of their finished US."""
    by_dev = defaultdict(list)
    for x in recs: by_dev[x["dev"]].append(x)
    order = sorted(by_dev, key=lambda d: (AREAS.index(by_dev[d][0]["area"]), d.lower()))
    if not order:
        return '<p class="dim" style="padding:.6rem">No finished User Stories in this window.</p>'
    h = []
    for dev in order:
        drecs = by_dev[dev]; area = AREA_LABEL[drecs[0]["area"]]; tot = _us_agg("Total", "", drecs)
        h.append(f'<details><summary>{e(dev)} <span class="cnt">({e(area)} &middot; {tot["nUS"]} US &middot; '
                 f'{tot["aiUS"]} AI &middot; {tot["sumTotal"]}h)</span></summary>')
        h.append('<div class="tw"><table><thead><tr>'
                 + "".join(f'<th class="{ "r" if k in UMONTH_NUM else "" }">{e(t)}</th>' for k, t in UMONTH_COLS)
                 + '</tr></thead><tbody>')
        for m in sorted({x["month"] for x in drecs}, reverse=True):
            h.append('<tr>' + _umonth_cells(_us_agg(m, "", [x for x in drecs if x["month"] == m])) + '</tr>')
        h.append('<tr class="tot">' + _umonth_cells(tot) + '</tr></tbody></table></div></details>')
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
             '<b>Gain</b> = (Sum A. Est &minus; Sum logged)/Sum A. Est, <b>with / without</b> sub-bug hours; a dash marks a meaningless gain. '
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
                            row.append(gcell(d[k]) if k in ("gainBug", "gainNoBug") else d[k])
                        w.writerow(row)
    return len(recs), mons

# ======================= main =======================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tempo", required=True); ap.add_argument("--issues", required=True)
    ap.add_argument("--devmap", required=True); ap.add_argument("--dates")   # {issueId: latest worklog date}
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--project", default="INTRD")
    ap.add_argument("--md"); ap.add_argument("--out", required=True); ap.add_argument("--csv")
    a = ap.parse_args()
    tempo = json.load(open(a.tempo, encoding="utf-8"))
    devmap = json.load(open(a.devmap, encoding="utf-8"))
    wdates = json.load(open(a.dates, encoding="utf-8")) if a.dates and os.path.exists(a.dates) else {}
    ns = nodes(json.load(open(a.issues, encoding="utf-8")))
    rows = build_ticket_rows(ns, tempo, devmap, a.project, wdates)
    _, _, grand_log = area_totals(rows)
    mons = months_of(rows)

    # ---------- Markdown (per-area totals overall + by month; per-ticket grouped by month) ----------
    md = []; P = md.append
    P(f"# Estimation vs logged, per area — {a.project}, [{a.since or '…'} … {a.until or '…'})\n")
    if not rows:
        P("_No logged time for the roster in this window._")
    else:
        P("## Totals by area\n")
        for ln in md_totals_lines(rows): P(ln)
        P(f"\n**Total logged across all groups:** {grand_log} h\n")
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
            P("| Ticket | Date | Type | Status | F | Back (dev · log) | Front (dev · log) | QA (dev · log) | Arch/PR h | Total h |")
            P("|---|---|---|---|:-:|---|---|---|--:|--:|")
            for r in mr:
                def cell(ar):
                    x = r["areas"][ar]
                    return f"{x['main']} · {x['logged']}" if x["logged"] else "–"
                P(f"| {r['key']} | {r['date']} | {r['ttype']} | {r['status']} | {'T' if r['final'] else ''} | "
                  f"{cell('backend')} | {cell('frontend')} | {cell('qa')} | {r['archprH'] or '–'} | {r['totalLogged']} |")
    md_text = "\n".join(md)
    if a.md: open(a.md, "w", encoding="utf-8").write(md_text)
    print(md_text)

    # ---------- CSV (full per-area matrix, flattened) ----------
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        percol = ["Main dev", "A. Est h", "DL. Est h", "Total dev h", "Logged h", "Sub-bug h", "AI",
                  "Arch gain (w bug)", "Arch gain (no bug)", "DL gain (w bug)", "DL gain (no bug)", "Sub-bugs"]
        header = ["Ticket", "Date", "Month", "Type", "Title", "Status", "Final"]
        for ar in AREAS: header += [f"{AREA_LABEL[ar]} {c}" for c in percol]
        header += ["Arch/PR/mgmt logged h", "Arch/PR/mgmt devs", "Total logged h", "Total dev h"]
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh); w.writerow(header)
            for r in rows:
                row = [r["key"], r["date"], r["month"], r["ttype"], r["title"], r["status"], "T" if r["final"] else ""]
                for ar in AREAS:
                    x = r["areas"][ar]
                    row += [x["main"], x["aEst"], x["dlEst"], x["totalDev"], x["logged"], x["subBug"],
                            "Yes" if x["ai"] else "",
                            gain_cell(x["aEst"], x["logged"] + x["subBug"]), gain_cell(x["aEst"], x["logged"]),
                            gain_cell(x["dlEst"], x["logged"] + x["subBug"]), gain_cell(x["dlEst"], x["logged"]),
                            x["bugs"]]
                row += [r["archprH"], "; ".join(r["archprDevs"]), r["totalLogged"], r["totalDev"]]
                w.writerow(row)

    # ---------- HTML (wide per-area matrix) ----------
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    B = []; W = B.append
    W("<h1>Estimation vs logged hours — per area</h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; [{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} tickets</p>')
    if not rows:
        W('<p>No logged time for the roster in this window.</p>')
    else:
        us_rows = [r for r in rows if r["ttype"] == "US"]
        us_final = [r for r in us_rows if r["final"]]
        bug_final = [r for r in rows if r["ttype"] == "Bug" and r["final"]]
        other_rows = [r for r in rows if r["ttype"] != "US"]
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
        W(f'<section class="panel panel-all">{html_report_body(rows)}</section>')
        W(f'<section class="panel panel-us">{html_report_body(us_rows)}</section>')
        W(f'<section class="panel panel-usfinal">{html_report_body(us_final)}</section>')
        W(f'<section class="panel panel-bugfinal">{html_report_body(bug_final)}</section>')
        W(f'<section class="panel panel-other">{html_report_body(other_rows)}</section>')
        W('</div>')
    W('<p class="foot">One row per ticket, with a column group per area (Backend / Frontend / QA). '
      '<b>Date</b> = the ticket\'s latest Tempo worklog date (last activity); tickets are grouped into that month. '
      '<b>Main dev</b> = the roster developer of that area with the most logged hours on the ticket. '
      '<b>Logged h</b> = hours booked by that area\'s developers (a multi-role Architect/PR-review developer who is '
      '<i>not</i> their area\'s main dev on the ticket has their hours moved to the <b>Arch/PR h</b> column instead). '
      '<b>Sub-bug h</b> / <b>#SB</b> = hours this area\'s developers logged fixing the ticket\'s child Bug/Sub-bug sub-issues, and '
      'the count of such sub-bugs they worked on (attributed by the fixer\'s area, so nothing is lost when a sub-bug has no component). '
      '<b>Total dev h</b> = Logged + Sub-bug h. <b>A.Est</b> (Architect, per-area estimate '
      'field &times;8) and <b>DL.Est</b> (Dev-lead; a US sums that area\'s child sub-task estimates, else the ticket estimate). '
      '<b>Arch/DL gain</b> = (Est&minus;Logged)/Est shown with / without sub-bug hours; green positive, red negative, "-" when meaningless. '
      'The per-ticket <b>AI</b> badge marks an area developed with AI assistance (the ticket carries an AI-metrics record for '
      'that area, or a same-area sub-task does); in the Totals, <b>AI-assisted</b> = AI-assisted tickets / total tickets for that area. '
      '<b>Total log h</b> = logged across all groups (areas + Arch/PR). '
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

- **Tempo token visibility.** On this instance `TEMPO_API_TOKEN` has **organisation-wide** worklog visibility — the per-user endpoint (`/worklogs/user/{accountId}`) returns worklogs for **every** roster area (backend, frontend, QA), verified across all 27 developers. There is **no backend-only restriction**; report all areas. (A missing area therefore means those developers had no in-window worklogs or the roster name failed to resolve to an accountId — not a Tempo permission gap.)
- **Point-in-time.** Logged hours reflect the Tempo state when you run it. It requires `TEMPO_API_TOKEN`.
- **Per-area columns.** Each ticket has a column group per area (Backend/Frontend/QA); a developer's hours land in **their own roster area**. A multi-role `archpr` developer who isn't their area's main dev on a ticket has their non-bug hours moved to the **Arch/PR h** column, so per-area numbers reflect real development, not review.
- **Main dev = top by total work.** Per area, the main developer is the roster dev with the most **dev-logged + own sub-bug-fixing** hours — a token reviewer never wins. The **second report** credits each finished US to each area's main dev (up to three per US).
- **Roll-up.** Worklogs on a Story's non-bug sub-tasks fold into that Story's per-area **Logged h**; worklogs on its Bug/Sub-bug sub-tasks fold into per-area **Sub-bug h** (by the fixer's area). A top-level Bug the developer logged on is its own row (all time = that area's Logged h).
- **Date & month.** Each ticket's Date is its latest Tempo worklog date; tickets are grouped by that month (a long-running ticket's full hours land in its last-activity month).
- **Estimates.** A. Est needs the per-area estimate custom fields on the Story; DL. Est needs child sub-task estimates (Story) or the ticket estimate (Bug/Enabler). Areas with no estimate show `0` / `–` time gain.
- **Read-only** — the command never writes to Jira; outbound calls are read-only: the Jira REST enhanced-search reads (Task 3) and the Tempo per-user fetch (Task 2).

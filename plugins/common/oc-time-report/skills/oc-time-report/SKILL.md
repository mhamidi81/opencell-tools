---
name: oc-time-report
description: Produce an estimation-vs-logged-hours report over a period, independent of the AI-usage JSON. Tempo-worklog driven, TICKET-based — one row per ticket owned by its main developer (most total hours), with type, area, title, Architect & Dev-lead estimates, total logged & bug hours (all contributors, subtasks rolled up), time gain (without/with bugs), child-bug count, and a contributor breakdown. A ticket counts once, under its main developer. Prints Markdown and writes a styled, date-stamped HTML file and a CSV to ./docs/. Fetches Jira via direct REST (mandatory JIRA_API_TOKEN) and Tempo per-user (mandatory TEMPO_API_TOKEN) — no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH] [--csv PATH]"
---

## Purpose

A team **estimation-vs-actual** report. Unlike `/oc-ai-report`, this one is **not** tied to the AI-usage JSON field — it is driven by **Tempo worklogs** and is **ticket-based**: one row per ticket, owned by its **main developer**, comparing the ticket's estimate to the team's actual logged time.

> **Ticket · Type · Area · Title · Status · Final · Main dev · A. Est h · DL. Est h · Total dev h · Logged h · Bug h · AI · Arch gain (w/o · w bugs) · DL gain (w/o · w bugs) · Bugs · Contributors**

- **Main developer** — the roster developer with the **most total hours** (logged + bug) on the ticket. The ticket is attributed to that person only; helpers still appear in **Contributors** but the ticket does **not** count in their own totals.
- **Area** — the **main developer's** area (from the roster below), which also selects the estimate fields used.
- **Status / Final** — the ticket's Jira status, and a **T** flag when that status is *terminal* for the ticket's type (**Bug**: Done/Invalid; **US**: Ready for Sprint review / Need documentation / Ready for release / Released; **others**: Done), matched case-insensitively.
- **A. Est h** (Architect) — the Story's per-area estimate custom field for the main dev's area (days ×8), else the ticket's own estimate.
- **DL. Est h** (Dev-lead) — for a **Story**, the sum of that area's child **sub-task** estimates (sub-bugs excluded); for a **Bug/Enabler**, the ticket's own estimate.
- **Total dev h** — total development time on the ticket = **Logged h + Bug h** (the sum of all effort, bug-fixing included). Shown immediately before Logged h.
- **Logged h** — the **whole ticket's** Tempo hours on the ticket + its **non-bug** sub-tasks, summed across **all contributors** (subtasks rolled up to the parent).
- **Bug h** — the whole ticket's Tempo hours on its child **Bug/Sub-bug** sub-tasks, across all contributors.
- **Arch gain / DL gain** — two time gains, `(Est − Logged)/Est` and `(Est − (Logged+Bug h))/Est`, `without / with` bug hours, computed against the **Architect** and **Dev-lead** estimate respectively. A gain shows as **`-`** when it is meaningless: a placeholder estimate (≤0.5h, e.g. a 0.01-day field), no logged time, or a magnitude beyond ±1000%.
- **AI** — a badge marking a ticket **developed with AI assistance** (it, or any rolled-up sub-issue, carries the "AI metrics" field `customfield_10745`). Aggregates show **AI tk** = AI-assisted / total.
- **Bugs** — count of the ticket's child **Bug/Sub-bug** sub-issues; **only for Story / Enabler** tickets.
- **Contributors** — every roster developer who logged on the ticket, `Name total (logged+bug)`, sorted by total.

Output: Markdown in-session, plus a styled **HTML** file and a **CSV** of the detail rows, both date-stamped in `./docs/`.

**Second report — finished-US per-developer summary.** The same run also writes `time-report-<TODAY>-us-summary.html` and `…-us-summary.csv` (derived from `--out`/`--csv` by inserting `-us-summary`). It considers **only User Stories in a final status**, grouped by **main developer**, in **two tables — one where AI is true and one where AI is false**. Columns: **Developer · US (final) · Avg bugs / US · Sum A. Est h · Sum logged h · Sum bug h · Sum total h · Gain (with bugs) · Gain (no bugs)** — the gains are `(Sum A. Est − Sum logged)/Sum A. Est` without / with bug hours (same `-` rule for meaningless gains). Each table ends with a **Total** row: sums are added up and **Avg bugs / US = total bugs ÷ total US** (weighted by each developer's ticket count, not a mean of the per-developer averages). The CSV carries both groups (dev rows + their Total) with a leading **AI assisted** column.

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

Area is per developer. Resolve each name to a Jira **accountId** via Jira REST user search — `GET https://opencellsoft.atlassian.net/rest/api/3/user/search?query=<name>` (Basic auth `JIRA_EMAIL:JIRA_API_TOKEN`), pick the active `@opencellsoft.com` account whose `displayName` best matches (names below may differ slightly; warn on any you cannot resolve). Write the resolved map to `devmap.json` as `{ "<accountId>": {"name": "<display>", "area": "backend|frontend|qa"} }`. (If a `devmap.json` from a previous run already covers the roster, reuse it — accountIds are stable.)

| Developer | Area |
|---|---|
| Mohamed Amtiou | qa |
| Rajae Halabi | qa |
| Brahim Aachiq | qa |
| Souhayla Msellek | qa |
| Mohamed Hamidi | frontend |
| Mohamed Houssa | frontend |
| Oussama El Idrissi | frontend |
| Aissam Bahari | frontend |
| Vladimir Morev | frontend |
| Abdelmounaim Akakid | backend |
| Anas Rouaguebe | backend |
| Tarik Fakhouri | backend |
| Z Bariki | backend |
| Adil El Jaouhari | backend |
| M Stitane | backend |
| Hatim Oudad | backend |
| Zakaria El Meliani | backend |
| Andrius Karpavicius | backend |
| Mohamed El Azzouzi | backend |
| Rachid Ait Yazza | backend |
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

```bash
python "<SCRATCHPAD>/fetch_tempo_users.py" --devmap "<SCRATCHPAD>/devmap.json" \
  --from [SINCE] --to [UNTIL-1day] --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt"
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
- `customfield_10745` is the **"AI metrics"** field: its presence marks a ticket as **developed with AI assistance** (AI badge + AI tk count); a ticket is flagged if it *or any rolled-up sub-issue* carries it.
- Estimate custom fields are `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate* (days).

## Task 4 — Aggregate & render

Write `time_report.py` (below) and run it:

```bash
python "<SCRATCHPAD>/time_report.py" --tempo "<SCRATCHPAD>/tempo.json" --issues "<SCRATCHPAD>/issues.json" \
  --devmap "<SCRATCHPAD>/devmap.json" --since [SINCE] --until [UNTIL] --project [PROJECT] \
  --md "<SCRATCHPAD>/report.md" --out "./docs/time-report-[TODAY].html" --csv "./docs/time-report-[TODAY].csv"
```

Show the Markdown (`report.md`) to the user and report the HTML + CSV paths.

### `fetch_tempo_users.py`

```python
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
BASE="https://api.tempo.io/4"
def fetch_user(acc, tok, frm, to):
    per_issue={}  # issueId -> seconds
    url=f"{BASE}/worklogs/user/{urllib.parse.quote(acc,safe='')}?from={frm}&to={to}&limit=1000"
    n=0
    while url:
        req=urllib.request.Request(url, headers={"Authorization":f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: data=json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"  {acc}: HTTP {ex.code}\n"); return per_issue, n, ex.code
        for w in data.get("results") or []:
            iid=str(((w.get("issue") or {}).get("id")))
            sec=w.get("timeSpentSeconds") or 0
            if iid and iid!="None":
                per_issue[iid]=per_issue.get(iid,0)+sec; n+=1
        url=(data.get("metadata") or {}).get("next")
    return per_issue, n, 200

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--devmap",required=True); ap.add_argument("--from",dest="frm",required=True)
    ap.add_argument("--to",required=True); ap.add_argument("--out",required=True); ap.add_argument("--ids-out",required=True)
    a=ap.parse_args()
    tok=os.environ.get("TEMPO_API_TOKEN")
    if not tok: sys.stderr.write("no token\n"); sys.exit(1)
    dev=json.load(open(a.devmap,encoding="utf-8"))
    tempo={}  # issueId -> {acc: secs}
    for acc,info in dev.items():
        per,cnt,code=fetch_user(acc,tok,a.frm,a.to)
        for iid,sec in per.items():
            tempo.setdefault(iid,{})[acc]=tempo.get(iid,{}).get(acc,0)+sec
        sys.stderr.write(f"{info['area']:8} {info['name']:26} {cnt:5} worklogs, {len(per):4} issues\n")
    json.dump(tempo, open(a.out,"w"))
    open(a.ids_out,"w").write(",".join(tempo.keys()))
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
"""Estimation-vs-logged report, TICKET-based. One row per ticket, owned by its main developer
(the roster dev with the most total hours on it). Logged/Bug hours are the whole ticket's effort
(all contributors, rolled up from subtasks); a ticket counts once, under its main developer only.
Area/estimates follow the main developer's area."""
import argparse, json, re, html, csv, os
from collections import defaultdict

COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8
BUG_TYPES = {"bug", "sub-bug"}
SUBTASK_TYPES = {"sub-task", "sub-bug", "sub test execution", "sub-test execution"}
TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Bug", "enabler": "Enabler"}
# "final" (terminal) status per ticket type, matched case-insensitively:
FINAL_STATUS = {
    "Bug": {"done", "invalid"},
    "US": {"ready for sprint review", "need documentation", "ready for release", "released"},
}
DEFAULT_FINAL = {"done"}  # Enabler and any other type

def nodes(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        if "issues" in data:
            iss = data["issues"]
            return (iss.get("nodes", []) if isinstance(iss, dict) else iss) or []
        if "nodes" in data: return data["nodes"] or []
        vals = list(data.values())  # dict keyed by issue key -> values are nodes
        if vals and isinstance(vals[0], dict) and ("fields" in vals[0] or "key" in vals[0]):
            return vals
    return []

def hours(s): return round((s or 0) / 3600, 1)
def is_bug(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES
def is_subtask(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in SUBTASK_TYPES
def ticket_type(f):
    n = (f.get("issuetype") or {}).get("name") or ""
    return TYPE_MAP.get(n.lower(), n or "?")
def status_of(f): return ((f.get("status") or {}).get("name") or "").strip()
def is_final(ttype, status):
    return (status or "").strip().lower() in FINAL_STATUS.get(ttype, DEFAULT_FINAL)

def area_of(f):
    for c in f.get("components") or []:
        ar = COMP_AREA.get((c.get("name") or "").strip().lower())
        if ar: return ar
    m = _TAG.search(f.get("summary") or "")
    if m: return {"back": "backend", "front": "frontend", "test": "qa"}[m.group(1).lower()]
    return None

def area_estimate_h(f, area):
    vals = {ar: f.get(fld) for ar, fld in AREA_EST_FIELD.items()}
    if any(isinstance(v, (int, float)) for v in vals.values()):
        v = vals.get(area)
        est = round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    else:
        est = hours(f.get("timeoriginalestimate"))
    return 0.0 if 0 < est < EST_MIN else est  # a placeholder like 0.01d (~0.1h) counts as no estimate -> 0

GAIN_CAP = 1000  # |time gain %| beyond this is placeholder-driven noise -> show "-"
EST_MIN = 0.5    # estimates at/below this (e.g. a 0.01-day placeholder ~= 0.1h) are meaningless
def gain_pct(est, logged):
    if not est or est < EST_MIN or not logged or logged <= 0:
        return None  # placeholder estimate or no logged time -> gain is nonsense
    return round((est - logged) / est * 100)
def gain_str(g): return "-" if (g is None or abs(g) > GAIN_CAP) else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_two(est, logged, bug):
    return f"{gain_str(gain_pct(est, logged))} / {gain_str(gain_pct(est, logged + bug))}"
def gain_cell(est, logged):  # CSV: capped integer or "-"
    g = gain_pct(est, logged)
    return "-" if (g is None or abs(g) > GAIN_CAP) else g
def e(x): return html.escape(str(x))
def is_ai(f): return bool(f.get("customfield_10745"))  # AI-metrics JSON present -> developed with AI assistance
def ai_yn(b): return "Yes" if b else ""

def build_ticket_rows(parents, children_nodes, tempo, devmap, project):
    all_nodes = parents  # single merged list of every node
    by_id = {str(n.get("id")): n for n in all_nodes}
    by_key = {n.get("key"): n for n in all_nodes}
    children = defaultdict(list)
    for n in all_nodes:
        pk = ((n.get("fields") or {}).get("parent") or {}).get("key")
        if pk: children[pk].append(n)

    # per-ticket per-dev logged/bug seconds (roll subtasks up to their parent)
    tk = defaultdict(lambda: {"logged": defaultdict(float), "bug": defaultdict(float)})
    for iid, per in tempo.items():
        node = by_id.get(str(iid))
        if not node: continue
        nf = node.get("fields") or {}
        pk = (nf.get("parent") or {}).get("key")
        st = is_subtask(nf)
        tkey = pk if (st and pk and pk in by_key) else node.get("key")
        bucket = "bug" if (st and is_bug(nf)) else "logged"
        for acc, sec in per.items():
            if acc not in devmap: continue
            tk[tkey][bucket][acc] += sec

    rows = []
    for tkey, agg in tk.items():
        if project and not str(tkey).startswith(project + "-"): continue
        tnode = by_key.get(tkey)
        if not tnode: continue
        tf = tnode.get("fields") or {}
        # total hours per dev (logged + bug) -> main developer
        tot = defaultdict(float)
        for acc, s in agg["logged"].items(): tot[acc] += s
        for acc, s in agg["bug"].items(): tot[acc] += s
        if not tot: continue
        main = max(tot, key=lambda a: (round(tot[a], 3), round(agg["logged"].get(a, 0), 3)))
        area = devmap[main]["area"]
        ttype = ticket_type(tf)
        a_est = area_estimate_h(tf, area)
        if ttype == "US":
            dl = 0.0
            for c in children.get(tkey, []):
                cf = c.get("fields") or {}
                if is_bug(cf): continue
                if (area_of(cf) or area_of(tf)) == area:
                    dl += hours(cf.get("timeoriginalestimate"))
            dl_est = round(dl, 1)
        else:
            dl_est = hours(tf.get("timeoriginalestimate"))
        bugs = sum(1 for c in children.get(tkey, []) if is_bug(c.get("fields") or {})) if ttype in ("US", "Enabler") else 0
        logged = hours(sum(agg["logged"].values()))
        bug_logged = hours(sum(agg["bug"].values()))
        # contributors, sorted by total desc
        contrib = []
        for acc in sorted(tot, key=lambda a: -tot[a]):
            contrib.append({"name": devmap[acc]["name"], "logged": hours(agg["logged"].get(acc, 0)),
                            "bug": hours(agg["bug"].get(acc, 0)), "total": hours(tot[acc])})
        ai = is_ai(tf) or any(is_ai(c.get("fields") or {}) for c in children.get(tkey, []))
        status = status_of(tf)
        final = is_final(ttype, status)
        rows.append({"key": tkey, "ttype": ttype, "area": area, "title": (tf.get("summary") or "")[:70],
                     "status": status, "final": final,
                     "main": devmap[main]["name"], "mainAcc": main,
                     "aEst": a_est, "dlEst": dl_est, "logged": logged, "bugLogged": bug_logged,
                     "bugs": bugs, "ai": ai, "contrib": contrib})
    rows.sort(key=lambda r: (r["area"], r["main"].lower(), r["key"]))
    return rows

def contrib_str(contrib):
    return "; ".join(f"{c['name']} {c['total']} ({c['logged']}+{c['bug']})" for c in contrib)

def _us_agg_row(label, rs):
    """Aggregate a set of finished-US rows into one summary row. avgBugs is total bugs
    over total US, so a Total row is weighted by each developer's ticket count."""
    n = len(rs)
    sum_aest = round(sum(x["aEst"] for x in rs), 1)
    sum_log = round(sum(x["logged"] for x in rs), 1)
    sum_bug = round(sum(x["bugLogged"] for x in rs), 1)
    return {
        "dev": label, "nUS": n,
        "avgBugs": round(sum(x["bugs"] for x in rs) / n, 2) if n else 0,
        "sumAEst": sum_aest, "sumLogged": sum_log, "sumBug": sum_bug,
        "sumTotal": round(sum_log + sum_bug, 1),
        "gainNoBug": gain_pct(sum_aest, sum_log),
        "gainBug": gain_pct(sum_aest, sum_log + sum_bug),
    }

def us_summary_by_dev(rows):
    """Per-developer aggregates over finished User Stories only, split by AI true/false.
    Returns {True: {"rows": [...], "total": row|None}, False: {...}}."""
    buckets = {True: defaultdict(list), False: defaultdict(list)}
    for r in rows:
        if r["ttype"] != "US" or not r["final"]:
            continue
        buckets[bool(r["ai"])][r["main"]].append(r)
    out = {}
    for ai_flag, per_dev in buckets.items():
        devrows = [_us_agg_row(dev, per_dev[dev]) for dev in sorted(per_dev, key=str.lower)]
        allrs = [x for rs in per_dev.values() for x in rs]
        total = _us_agg_row(f"TOTAL ({len(per_dev)} dev)", allrs) if allrs else None
        out[ai_flag] = {"rows": devrows, "total": total}
    return out

def write_us_summary(rows, html_path, csv_path, project, since, until):
    """Write the per-developer finished-US summary as its own HTML (two tables: AI true / false)
    and, if csv_path is given, a CSV (both groups, with an AI column)."""
    summ = us_summary_by_dev(rows)
    COLS = [("dev", "Developer"), ("nUS", "US (final)"), ("avgBugs", "Avg bugs / US"),
            ("sumAEst", "Sum A. Est h"), ("sumLogged", "Sum logged h"), ("sumBug", "Sum bug h"),
            ("sumTotal", "Sum total h"), ("gainBug", "Gain (with bugs)"), ("gainNoBug", "Gain (no bugs)")]
    numcols = {"nUS", "avgBugs", "sumAEst", "sumLogged", "sumBug", "sumTotal", "gainNoBug", "gainBug"}

    def cells_for(d):
        out = []
        for k, _ in COLS:
            if k in ("gainNoBug", "gainBug"):
                out.append(f'<td class="r">{gain_str(d[k])}</td>')
            elif k == "dev":
                out.append(f'<td class="name">{e(d[k])}</td>')
            else:
                out.append(f'<td class="r">{d[k]}</td>')
        return "".join(out)

    def table_html(group, label):
        h = [f'<h2>AI-assisted: {label}</h2>']
        devrows = group.get("rows") if group else None
        if not devrows:
            return "".join(h) + '<p class="meta">No finished User Stories in this group.</p>'
        h.append('<div class="tw"><table><thead><tr>'
                 + "".join(f'<th class="{ "r" if k in numcols else "" }">{e(t)}</th>' for k, t in COLS)
                 + "</tr></thead><tbody>")
        for d in devrows:
            h.append("<tr>" + cells_for(d) + "</tr>")
        if group.get("total"):
            h.append('<tr class="total">' + cells_for(group["total"]) + "</tr>")
        h.append("</tbody></table></div>")
        return "".join(h)

    body = [f"<h1>Finished User Stories &mdash; per-developer summary</h1>",
            f'<p class="meta">Project <b>{e(project)}</b> &middot; [{e(since or "…")} … {e(until or "…")}) '
            f'&middot; only <b>User Stories</b> in a final status &middot; grouped by main developer</p>',
            table_html(summ.get(True) or {}, "true"),
            table_html(summ.get(False) or {}, "false"),
            '<p class="foot">Only <b>User Stories</b> whose status is final '
            '(Ready for Sprint review / Need documentation / Ready for release / Released) are counted, '
            'attributed to their <b>main developer</b>. <b>Avg bugs / US</b> = child Bug/Sub-bug count per US '
            '(the <b>Total</b> row uses total bugs &divide; total US, i.e. weighted by each developer\'s ticket count). '
            'Sums are over that developer\'s finished US. <b>Gain</b> = (Sum A. Est &minus; Sum logged)/Sum A. Est, '
            'without / with bug hours; a dash marks a meaningless gain. Generated by <code>/oc-time-report</code>.</p>']
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finished US summary — {e(project)} {e(since or '')}…{e(until or '')}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --accent:#2563eb; --zebra:#fafbfc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad;
  --line:#242a31; --head:#171b21; --accent:#6ea8fe; --zebra:#12161c; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ width:100%; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
.meta {{ color:var(--muted); margin:0 0 1.25rem; }}
.tw {{ border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.5rem .7rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; position:sticky; top:0; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
.r {{ text-align:right; }}
.name {{ font-weight:600; }}
tr.total td {{ font-weight:700; border-top:2px solid var(--line); background:var(--head); }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{"".join(body)}
</div></body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(html_path)) or ".", exist_ok=True)
    open(html_path, "w", encoding="utf-8").write(doc)

    if csv_path:
        def csv_row(label, d):
            row = [label]
            for k, _ in COLS:
                if k in ("gainNoBug", "gainBug"):
                    g = d[k]
                    row.append("-" if (g is None or abs(g) > GAIN_CAP) else g)
                else:
                    row.append(d[k])
            return row
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["AI assisted"] + [t for _, t in COLS])
            for ai_flag, label in ((True, "Yes"), (False, "No")):
                grp = summ.get(ai_flag) or {}
                for d in grp.get("rows", []):
                    w.writerow(csv_row(label, d))
                if grp.get("total"):
                    w.writerow(csv_row(label, grp["total"]))
    return summ

def _summary_path(path, tag):
    base, ext = os.path.splitext(path)
    return f"{base}-{tag}{ext}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tempo", required=True); ap.add_argument("--issues", required=True)
    ap.add_argument("--devmap", required=True)
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--project", default="INTRD")
    ap.add_argument("--md"); ap.add_argument("--out", required=True); ap.add_argument("--csv")
    a = ap.parse_args()
    tempo = json.load(open(a.tempo, encoding="utf-8"))
    devmap = json.load(open(a.devmap, encoding="utf-8"))
    ns = nodes(json.load(open(a.issues, encoding="utf-8")))
    rows = build_ticket_rows(ns, ns, tempo, devmap, a.project)

    # ---------- Markdown ----------
    md = []; P = md.append
    P(f"# Estimation vs logged (by ticket) — {a.project}, [{a.since or '…'} … {a.until or '…'})\n")
    if not rows:
        P("_No logged time for the roster in this window._")
    else:
        # Totals by area (by main developer's area)
        AR = defaultdict(lambda: {"devs": set(), "tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "bugLogged": 0.0, "bugs": 0, "ai": 0})
        for r in rows:
            g = AR[r["area"]]; g["devs"].add(r["mainAcc"]); g["tickets"] += 1
            for k in ("aEst", "dlEst", "logged", "bugLogged", "bugs"): g[k] += r[k]
            g["ai"] += int(r["ai"])
        P("## Totals by area\n")
        P("| Area | Devs | Tickets | A. Est h | DL. Est h | Total dev h | Logged h | Bug h | AI tk | Arch gain | DL gain | Bugs |")
        P("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for ar in ("backend", "frontend", "qa"):
            if ar not in AR: continue
            g = AR[ar]
            P(f"| {ar.capitalize()} | {len(g['devs'])} | {g['tickets']} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
              f"{round(g['logged'] + g['bugLogged'],1)} | {round(g['logged'],1)} | {round(g['bugLogged'],1)} | {g['ai']}/{g['tickets']} | {gain_two(g['aEst'], g['logged'], g['bugLogged'])} | "
              f"{gain_two(g['dlEst'], g['logged'], g['bugLogged'])} | {g['bugs']} |")
        # Summary by developer (as main developer)
        DV = defaultdict(lambda: {"area": "", "tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "bugLogged": 0.0, "bugs": 0, "ai": 0})
        for r in rows:
            g = DV[r["main"]]; g["area"] = r["area"]; g["tickets"] += 1
            for k in ("aEst", "dlEst", "logged", "bugLogged", "bugs"): g[k] += r[k]
            g["ai"] += int(r["ai"])
        P("\n## Summary by developer (owned tickets)\n")
        P("| Developer | Area | Tickets | A. Est h | DL. Est h | Total dev h | Logged h | Bug h | AI tk | Arch gain | DL gain | Bugs |")
        P("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for dev in sorted(DV, key=str.lower):
            g = DV[dev]
            P(f"| {dev} | {g['area']} | {g['tickets']} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
              f"{round(g['logged'] + g['bugLogged'],1)} | {round(g['logged'],1)} | {round(g['bugLogged'],1)} | {g['ai']}/{g['tickets']} | {gain_two(g['aEst'], g['logged'], g['bugLogged'])} | "
              f"{gain_two(g['dlEst'], g['logged'], g['bugLogged'])} | {g['bugs']} |")
        # Detail (one row per ticket)
        P("\n## Detail (by ticket)\n")
        P("| Ticket | Type | Area | Title | Status | Final | Main dev | A. Est h | DL. Est h | Total dev h | Logged h | Bug h | AI | Arch gain | DL gain | Bugs | Contributors |")
        P("|---|---|---|---|---|:--:|---|--:|--:|--:|--:|--:|:--:|--:|--:|--:|---|")
        for r in rows:
            P(f"| {r['key']} | {r['ttype']} | {r['area']} | {r['title']} | {r['status']} | {'T' if r['final'] else ''} | {r['main']} | {r['aEst']} | {r['dlEst']} | "
              f"{round(r['logged'] + r['bugLogged'],1)} | {r['logged']} | {r['bugLogged']} | {ai_yn(r['ai'])} | {gain_two(r['aEst'], r['logged'], r['bugLogged'])} | "
              f"{gain_two(r['dlEst'], r['logged'], r['bugLogged'])} | {r['bugs']} | {contrib_str(r['contrib'])} |")
    md_text = "\n".join(md)
    if a.md: open(a.md, "w", encoding="utf-8").write(md_text)
    print(md_text)

    # ---------- CSV (ticket detail) ----------
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Ticket", "Type", "Area", "Title", "Status", "Final status", "Main developer", "A. Est h", "DL. Est h",
                        "Total dev h", "Logged h", "Bug h", "AI assisted", "Arch gain % (no bugs)", "Arch gain % (with bugs)",
                        "DL gain % (no bugs)", "DL gain % (with bugs)", "Bugs", "Contributors"])
            for r in rows:
                w.writerow([r["key"], r["ttype"], r["area"], r["title"], r["status"], "T" if r["final"] else "", r["main"], r["aEst"], r["dlEst"],
                            round(r["logged"] + r["bugLogged"], 1), r["logged"], r["bugLogged"], "Yes" if r["ai"] else "No",
                            gain_cell(r["aEst"], r["logged"]), gain_cell(r["aEst"], r["logged"] + r["bugLogged"]),
                            gain_cell(r["dlEst"], r["logged"]), gain_cell(r["dlEst"], r["logged"] + r["bugLogged"]),
                            r["bugs"], contrib_str(r["contrib"])])

    # ---------- HTML ----------
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    B = []; W = B.append
    W("<h1>Estimation vs logged hours (by ticket)</h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; [{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} tickets</p>')
    if not rows:
        W('<p>No logged time for the roster in this window.</p>')
    else:
        W("<h2>Detail (one row per ticket)</h2>")
        head = ["Ticket", "Type", "Area", "Title", "Status", "Final", "Main dev", "A. Est h", "DL. Est h", "Total dev h", "Logged h", "Bug h", "AI", "Arch gain", "DL gain", "Bugs", "Contributors"]
        left = {"Ticket", "Type", "Area", "Title", "Status", "Main dev", "Contributors"}
        cent = {"AI", "Final"}
        W('<div class="tw"><table><thead><tr>' + "".join(f'<th class="{ "c" if h in cent else ("" if h in left else "r") }">{e(h)}</th>' for h in head) + "</tr></thead><tbody>")
        AIBADGE = '<span class="aibadge">AI</span>'
        for r in rows:
            aicell = AIBADGE if r["ai"] else ""
            finalcell = '<span class="finalbadge">T</span>' if r["final"] else ""
            W(f'<tr><td class="key">{e(r["key"])}</td><td>{e(r["ttype"])}</td><td>{e(r["area"])}</td>'
              f'<td>{e(r["title"])}</td><td>{e(r["status"])}</td><td class="c">{finalcell}</td><td class="name">{e(r["main"])}</td><td class="r">{r["aEst"]}</td><td class="r">{r["dlEst"]}</td>'
              f'<td class="r">{round(r["logged"] + r["bugLogged"], 1)}</td><td class="r">{r["logged"]}</td><td class="r">{r["bugLogged"]}</td>'
              f'<td class="c">{aicell}</td>'
              f'<td class="r">{gain_two(r["aEst"], r["logged"], r["bugLogged"])}</td>'
              f'<td class="r">{gain_two(r["dlEst"], r["logged"], r["bugLogged"])}</td><td class="r">{r["bugs"]}</td>'
              f'<td class="sm">{e(contrib_str(r["contrib"]))}</td></tr>')
        W("</tbody></table></div>")
    W('<p class="foot">One row per ticket, owned by its <b>main developer</b> (most total hours). Logged h &amp; Bug h are the '
      'whole ticket\'s effort (all contributors, subtasks rolled up); a ticket counts once, under its main developer. Area &amp; '
      'estimates follow the main developer\'s area. Logged = non-bug work; Bug h = child Bug/Sub-bug work. '
      '<b>Arch gain</b> = (A.Est&minus;Logged)/A.Est and <b>DL gain</b> = (DL.Est&minus;Logged)/DL.Est, each shown '
      'without / with bug hours; a dash (&ndash;) marks a meaningless gain &mdash; a placeholder estimate '
      '(&le;0.5h, e.g. a 0.01-day field), no logged time, or a magnitude beyond &plusmn;1000%. '
      'The <b>AI</b> badge (and <b>AI tk</b> = AI-assisted / total in the aggregates) marks a ticket carrying an '
      'AI-usage record (the "AI metrics" field), i.e. developed with AI assistance. '
      '<b>Status</b> is the ticket\'s Jira status; <b>Final</b> (T) marks a ticket in a terminal status for its type '
      '(Bug: Done/Invalid; US: Ready for Sprint review / Need documentation / Ready for release / Released; others: Done). '
      'Generated by <code>/oc-time-report</code>.</p>')
    body = "\n".join(B)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estimation vs logged — {e(a.project)} {e(a.since or '')}…{e(a.until or '')}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --accent:#2563eb; --zebra:#fafbfc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad;
  --line:#242a31; --head:#171b21; --accent:#6ea8fe; --zebra:#12161c; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ width:100%; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
.meta {{ color:var(--muted); margin:0 0 1.25rem; }}
.tw {{ border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.5rem .7rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; position:sticky; top:0; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
.r {{ text-align:right; }}
.c {{ text-align:center; }}
.aibadge {{ display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.03em; color:#fff;
  background:var(--accent); border-radius:4px; padding:.05rem .35rem; }}
.finalbadge {{ display:inline-block; font-size:.7rem; font-weight:700; color:#fff;
  background:#16a34a; border-radius:4px; padding:.05rem .4rem; }}
.name {{ font-weight:600; }}
.sm {{ color:var(--muted); font-size:.85em; }}
.key {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--accent); font-weight:600; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{body}
</div></body></html>"""
    open(a.out, "w", encoding="utf-8").write(doc)

    # ---------- Finished-US per-developer summary (second report) ----------
    summ_html = _summary_path(a.out, "us-summary")
    summ_csv = _summary_path(a.csv, "us-summary") if a.csv else None
    summ = write_us_summary(rows, summ_html, summ_csv, a.project, a.since, a.until)
    n_true = len((summ.get(True) or {}).get("rows", [])); n_false = len((summ.get(False) or {}).get("rows", []))
    print(f"\nFinished-US summary: {summ_html}"
          + (f" + {summ_csv}" if summ_csv else "")
          + f"  ({n_true} dev(s) with AI, {n_false} without)")

if __name__ == "__main__":
    main()
```

## Notes & limitations

- **Tempo token visibility.** On this instance `TEMPO_API_TOKEN` has **organisation-wide** worklog visibility — the per-user endpoint (`/worklogs/user/{accountId}`) returns worklogs for **every** roster area (backend, frontend, QA), verified across all 27 developers. There is **no backend-only restriction**; report all areas. (A missing area therefore means those developers had no in-window worklogs or the roster name failed to resolve to an accountId — not a Tempo permission gap.)
- **Point-in-time.** Logged hours reflect the Tempo state when you run it. It requires `TEMPO_API_TOKEN`.
- **Area is per developer** (from the roster), not the ticket — a backend dev's rows are all `backend` even on a cross-area story.
- **Roll-up.** A developer's worklogs on a Story's non-bug sub-tasks fold into that Story's Logged h; worklogs on its Bug/Sub-bug sub-tasks fold into Bug h. A top-level Bug the developer logged on is its own row (all time = Logged h, Bugs = 0).
- **Estimates.** A. Est needs the per-area estimate custom fields on the Story; DL. Est needs child sub-task estimates (Story) or the ticket estimate (Bug/Enabler). Rows for tickets with no estimate show `0` / `–` time gain.
- **Read-only** — the command never writes to Jira; outbound calls are read-only: the Jira REST enhanced-search reads (Task 3) and the Tempo per-user fetch (Task 2).

---
name: oc-noai-report
description: Companion to /oc-time-report that surfaces work reaching test/review/done WITHOUT AI. Same Tempo-worklog data and the same Project + grouped Fix-version filters and five tabs. Scope: tickets whose status is one of In Test / Need sync (after dev) / Ready for Test / Ready for Sprint Review / Done, ticket-date >= a cutoff (default 2026-09-01, since AI use before then was negligible). Sub-tasks roll up into their parent US, but sub-bugs are kept as their OWN rows (not rolled under the US); the unit is one ticket x dev area (backend/frontend/qa; overhead excluded). A unit has AI when it has AI-classified logged time (same rule as the time report: a worklog is AI when its author holds an AI-metrics record on the issue; a US record propagates to its non-bug sub-tasks; a sub-bug uses its own record). Three sections: Totals by area and Totals by month (Area/Month, total tickets, AI tickets, % AI tickets, logged d, AI logged d, % AI logged), and Details listing the no-AI units (Ticket, date, Type, Fix version, title, status, Logged d, area, main developer) grouped by area then month. All times in days (1 d = 8 h). Date-stamped HTML to ./docs/. Jira via direct REST (mandatory JIRA_API_TOKEN) + Tempo per-user (mandatory TEMPO_API_TOKEN); no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD,MACRD] [--out PATH]"
---

## Purpose

A **non-AI adoption** report — the companion to `/oc-time-report`. It answers: *which work reached testing / review / done **without** any AI-logged time?* It is driven by the same **Tempo worklogs** + **AI-metrics records** and shares the time report's **Project** and grouped **Fix-version** filters and the same **five tabs** (All · User Stories (All) · User Stories (Final) · Bugs (Final) · Bugs and Others).

**Scope.** A ticket is in scope when its **status** is one of **In Test · Need sync (after dev) · Ready for Test · Ready for Sprint Review · Done** and its **ticket-date** (`resolutiondate`, else `updated`) is **>= the cutoff** (`--since`, default **2026-09-01** — before then AI use was negligible, so earlier tickets would distort the % AI).

**Unit = one ticket × one dev area.** A ticket worked by two areas counts once per area, so "% AI" is a per-area adoption rate. **Sub-tasks roll up into their parent US; sub-bugs are kept as their OWN rows** (not rolled under the US). **Overhead** people (Architect / PO / DevOps / Consultant / management) are **excluded** (not a dev area).

**AI classification** is the time report's rule: a worklog is **AI-assisted** when its author holds an AI-metrics record (`customfield_10745`) on the issue it is booked on; a **US's record propagates to its non-bug sub-tasks**; a **sub-bug** is judged on its **own** record. A unit **has AI** when it has any AI-classified logged time.

**Sections** (inside each tab, recomputing live under the filters):
- **Totals by area** — one row per area (Backend / Frontend / QA) + a Total row: **Area · Tickets · AI tickets · % AI tickets · Logged d · AI logged d · % AI logged**.
- **Totals by month** — same columns, grouped by month instead of area.
- **Details** — only the units with **no** AI logged time, grouped by **area → month**: **Ticket · Date · Type · Fix version · Title · Status · Logged d · Area · Main developer**. Ticket keys link to Jira.

All times are in **days** (1 d = 8 h). Output: a self-contained styled **HTML** file, date-stamped in `./docs/`.

## Access

Both tokens are **mandatory** and read from the environment (never passed on the command line). If either is missing, tell the user how to create it and **stop**.

- **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token from *id.atlassian.com → Security → API tokens*. All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `jira_fetch_dates.py` below. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql`** — it force-includes each issue's full `description` and caps at ~5 issues/call. Direct REST honours the `fields` list, returns 100/page and paginates via `nextPageToken`.
- **`TEMPO_API_TOKEN`** (each developer's own token, *Tempo → Settings → API keys*, worklog **read** scope) — logged hours are the whole point. Fetched **per-user** (`/worklogs/user/{accountId}`), org-wide visibility.

## Arguments

Parse `$ARGUMENTS` — all optional.

- `--since YYYY-MM-DD` — the **cutoff**: only tickets whose date is on/after this are counted. Default **2026-09-01**. (Passed as `--since` to the Jira fetch and as `--cutoff` to the aggregator.)
- `--until YYYY-MM-DD` — end (exclusive). Default: tomorrow.
- `--project KEY[,KEY...]` — Jira project(s), comma-separated. **When the user passes `--project` explicitly, honour it verbatim and do NOT ask.** **When `--project` is NOT passed, the base default is `INTRD,MACRD`, and — because `PRT730` (Protected - 730) is a Protected project — you MUST ask the user before report generation whether PRT730 should be included** (e.g. "PRT730 is a Protected project — include it? (yes/no)"). On **yes** run with `INTRD,MACRD,PRT730`; on **no** `INTRD,MACRD`. Echo the resolved project list + window back.
- `--out PATH` — HTML output. Default `./docs/noai-report-<TODAY>-<SINCE>-<UNTIL>.html`.

Compute dates with `date -u +%Y-%m-%d` etc.; echo the resolved window back to the user.

## Developer roster (embedded)

Write the roster below to `<SCRATCHPAD>/devmap.json` verbatim (accountIds are stable). Schema `{ "<accountId>": {"name", "area", "role", "active"} }`, **area ∈ `backend` | `frontend` | `qa` | `overhead`**. Overhead roles (ARCHI/PO/DEVOPS/CONSULTANT/NONE) are excluded from this report's areas. If the team changed, re-resolve via `GET /rest/api/3/users/search?startAt=&maxResults=200` and update here.

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

Write the embedded `devmap.json` (above) to `<SCRATCHPAD>/devmap.json` verbatim.

## Task 2 — Select the in-window tickets (Jira, direct REST)

Write `jira_fetch_dates.py` (below) to scratchpad and run it with `--since` = the cutoff, so it selects tickets dated on/after the cutoff plus their parents and full sub-task lists:

```bash
python "<SCRATCHPAD>/jira_fetch_dates.py" --since [SINCE] --until [UNTIL] --project [PROJECT]   --out "<SCRATCHPAD>/issues.json"
```

It fetches `customfield_10745` (AI metrics), `fixVersions`, `status`, `resolutiondate`/`updated`, `parent`, etc., and writes `{issues:{nodes:[…]}}` keyed by numeric `id` (the aggregator joins Tempo by id). `customfield_10745` records are keyed `domain/accountId/name`; the aggregator extracts the accountIds that authored a record on each issue to classify worklogs AI vs non-AI.

## Task 3 — Fetch Tempo worklogs (per-user, all-time, cached)

Write `fetch_tempo_users.py` (below) to scratchpad and run it against `devmap.json`. Because a selected ticket's worklogs may pre-date the window, fetch **all-time** (so per-ticket totals match Jira's `aggregatetimespent`); the aggregator windows by ticket date. Use the persistent `--cache` so only the recent ~45 days re-fetch each run.

```bash
python "<SCRATCHPAD>/fetch_tempo_users.py" --devmap "<SCRATCHPAD>/devmap.json"   --from 2010-01-01 --to [UNTIL-1day] --cache "$HOME/.claude/oc-time-report/tempo_cache.json"   --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt" --dates-out "<SCRATCHPAD>/wdates.json"
```

(The cache is shared with `/oc-time-report`; `wdates.json` is written but this report does not need it.) It prints a per-developer worklog count to stderr; if Tempo returns nothing, tell the user and stop.

## Task 4 — Aggregate & render

Write `noai_report.py` (below) and run it (set `PYTHONIOENCODING=utf-8` on Windows so accented names print cleanly):

```bash
python "<SCRATCHPAD>/noai_report.py" --issues "<SCRATCHPAD>/issues.json" --tempo "<SCRATCHPAD>/tempo.json"   --devmap "<SCRATCHPAD>/devmap.json" --cutoff [SINCE] --project [PROJECT]   --out "./docs/noai-report-[TODAY]-[SINCE]-[UNTIL].html"
```

It prints the unit count and the status distribution to stderr (the five in-scope statuses are marked) — report the HTML path to the user and that they can open it in a browser (Windows: `start "" "<path>"`).

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

### `noai_report.py`

```python
#!/usr/bin/env python3
"""Non-AI adoption report, built on the same data as the time report (issues.json + tempo.json + devmap).
Unit = (reportable ticket x dev area). Sub-tasks roll up into their parent US; sub-bugs are their OWN
rows (NOT rolled under the US). A unit is counted per dev area (backend/frontend/qa; overhead excluded).
A unit 'has AI' when it has AI-classified logged hours (time-report rule: a worklog is AI when its author
holds an AI-metrics record on the issue; a US record propagates to non-bug sub-tasks; a sub-bug uses its own).
Scope: tickets whose status is one of the given set, ticket-date >= CUTOFF. Same project + fix-version filters
and the same five tabs as the time report. Sections: Totals by area, Totals by month, Details (no-AI only).
All times shown in days (1 d = 8 h). Self-contained (no external imports beyond the stdlib)."""
import argparse, json, os, re, html
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
BUG_TYPES = {"bug", "sub-bug"}
SUBTASK_TYPES = {"sub-task", "sub-bug", "sub test execution", "sub-test execution"}
STATUS_SET = {"in test", "need sync (after dev)", "ready for test", "ready for sprint review", "done"}
TMAP = {"story": "US", "sub-bug": "Sub-bug", "bug": "Bug", "enabler": "Enabler", "sub-task": "Sub-task"}
DAY_HOURS = 8

def e(x): return html.escape(str(x))

def nodes(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        if "issues" in data:
            iss = data["issues"]; return (iss.get("nodes", []) if isinstance(iss, dict) else iss) or []
        if "nodes" in data: return data["nodes"] or []
    return []

def is_bug(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES
def is_subtask(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in SUBTASK_TYPES
def status_of(f): return ((f.get("status") or {}).get("name") or "").strip()
def ticket_date(f):
    d = f.get("resolutiondate") or f.get("updated") or ""
    return d[:10]
def ttype_of(f):
    n = (f.get("issuetype") or {}).get("name") or ""
    return TMAP.get(n.lower(), n or "?")

def _cf_text(raw):
    """Recover the raw JSON text from an 'AI metrics' field value (plain string or Jira ADF dict)."""
    if isinstance(raw, dict):
        txt = []
        def w(n):
            if isinstance(n, dict):
                if n.get("type") == "text": txt.append(n.get("text", ""))
                for c in n.get("content") or []: w(c)
            elif isinstance(n, list):
                for c in n: w(c)
        w(raw); return "".join(txt)
    return raw if isinstance(raw, str) else ""

def ai_accounts(f):
    """AccountIds that authored an AI-metrics record on THIS issue (customfield_10745). Record keys are
    'domain/accountId/name'; the accountId (middle segment) matches the roster."""
    raw = _cf_text(f.get("customfield_10745")); accs = set()
    if raw and raw.strip():
        try: doc = json.loads(raw)
        except json.JSONDecodeError: doc = None
        for rk in ((doc or {}).get("records") or {}):
            p = rk.split("/", 2)
            if len(p) >= 2 and p[0] in AREAS and p[1]: accs.add(p[1])
    return accs

def version_options(fixvers):
    """Group the Fix Version/s picklist by release line (17.x, 17.2.x); non-numeric names kept as-is."""
    bases = {}; names = set()
    for v in fixvers:
        p = v.split(".")
        if p and p[0].isdigit():
            bases[p[0]] = p[0] + ".x"
            if len(p) >= 2 and p[1].isdigit(): bases[p[0] + "." + p[1]] = p[0] + "." + p[1] + ".x"
        else:
            names.add(v)
    def keyf(b):
        try: return (0,) + tuple(int(x) for x in b.split("."))
        except ValueError: return (1,)
    return [(b, bases[b]) for b in sorted(bases, key=keyf)] + [(v, v) for v in sorted(names)]

def build_units(ns, tempo, devmap, cutoff):
    by_id = {str(n.get("id")): n for n in ns}
    by_key = {n.get("key"): n for n in ns}

    # Accumulate hours per OWNER x area, split AI/non-AI. Owner = the ticket the hours belong to:
    #   non-bug sub-task -> its parent US (rolled up); sub-bug or any non-sub-task issue -> itself.
    owners = defaultdict(lambda: {ar: {"ai": 0.0, "no": 0.0, "dev": defaultdict(float)} for ar in AREAS})
    for iid, per in tempo.items():
        node = by_id.get(str(iid))
        if not node: continue
        f = node.get("fields") or {}
        st = is_subtask(f); bug = is_bug(f)
        pk = (f.get("parent") or {}).get("key")
        if st and not bug and pk and pk in by_key:          # non-bug sub-task -> roll into the parent US
            owner = pk
            eff_ai = ai_accounts(f) | ai_accounts(by_key[pk].get("fields") or {})
        else:                                               # sub-bug or a top-level issue -> its own row
            owner = node.get("key")
            eff_ai = ai_accounts(f)
        for acc, sec in per.items():
            d = devmap.get(acc)
            if not d: continue
            ar = d["area"]
            if ar not in AREAS: continue                    # overhead excluded
            o = owners[owner][ar]
            o["ai" if acc in eff_ai else "no"] += sec
            o["dev"][acc] += sec

    status_seen = defaultdict(int)
    units = []
    for owner, data in owners.items():
        node = by_key.get(owner)
        if not node: continue
        f = node.get("fields") or {}
        status = status_of(f); status_seen[status] += 1
        if status.lower() not in STATUS_SET: continue
        date = ticket_date(f)
        if not date or date < cutoff: continue
        tp = ttype_of(f); fv = f.get("fixVersions") or []
        is_us = tp == "US"; isb = tp in ("Bug", "Sub-bug")
        usf = is_us and status.lower() == "ready for sprint review"
        bugf = isb and status.lower() == "done"
        for ar in AREAS:
            o = data[ar]; lg = o["ai"] + o["no"]
            if lg <= 0: continue
            main = max(o["dev"], key=lambda a: o["dev"][a]) if o["dev"] else None
            units.append({"k": owner, "p": owner.split("-")[0], "fv": fv, "m": date[:7], "date": date,
                          "t": tp, "us": 1 if is_us else 0, "usf": 1 if usf else 0, "bugf": 1 if bugf else 0,
                          "a": ar, "lg": round(lg / 3600, 2), "ai": round(o["ai"] / 3600, 2),
                          "dev": devmap.get(main, {}).get("name", "?") if main else "?",
                          "title": (f.get("summary") or "")[:80], "status": status})
    return units, status_seen

CSS = r"""
:root { color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --card:#fff; --accent:#2563eb; --pos:#15803d; --neg:#b91c1c; --zebra:#fafbfc; }
@media (prefers-color-scheme: dark){ :root{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad; --line:#242a31;
  --head:#171b21; --card:#141821; --accent:#6ea8fe; --pos:#4ade80; --neg:#f87171; --zebra:#12161c; } }
*{ box-sizing:border-box; }
body{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
h1{ font-size:1.6rem; margin:0 0 .25rem; } h2{ font-size:1.15rem; margin:1.6rem 0 .5rem; padding-bottom:.3rem; border-bottom:2px solid var(--line); }
h3{ font-size:1rem; margin:1.1rem 0 .3rem; } .meta{ color:var(--muted); margin:0 0 1rem; }
.tw{ border:1px solid var(--line); border-radius:10px; overflow-x:auto; margin:.3rem 0 .8rem; }
table{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th,td{ padding:.4rem .6rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }
thead th{ background:var(--head); font-weight:600; } tbody tr:nth-child(even){ background:var(--zebra); }
.r{ text-align:right; } .name{ font-weight:600; } .sm{ color:var(--muted); font-size:.85em; }
.aih{ color:var(--accent); font-weight:600; } .dim{ color:var(--muted); }
.ti{ max-width:360px; overflow:hidden; text-overflow:ellipsis; }
.key a{ font-family:ui-monospace,Menlo,monospace; color:var(--accent); font-weight:600; text-decoration:none; }
.key a:hover{ text-decoration:underline; }
tr.tot td{ font-weight:700; background:var(--head); }
details{ border:1px solid var(--line); border-radius:10px; margin:.35rem 0; padding:0 .6rem; }
details[open]{ padding-bottom:.4rem; } summary{ cursor:pointer; font-weight:600; padding:.45rem .2rem; }
summary .cnt{ color:var(--muted); font-weight:400; font-size:.9em; }
.filterbar{ margin:1rem 0 .25rem; } .filterbar select{ padding:.3rem .55rem; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--fg); font:inherit; }
.tabbar{ display:flex; flex-wrap:wrap; gap:.25rem; border-bottom:2px solid var(--line); margin:1rem 0 .5rem; }
.tabbar button{ padding:.5rem 1rem; cursor:pointer; color:var(--muted); font-weight:600; font:inherit; background:none;
  border:1px solid transparent; border-bottom:none; border-radius:8px 8px 0 0; margin-bottom:-2px; }
.tabbar button.active{ color:var(--fg); background:var(--card); border-color:var(--line); border-bottom:2px solid var(--card); }
.tabbar button .cnt{ font-weight:400; }
.foot{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }
"""

JS = r"""
(function(){
  var U=JSON.parse(document.getElementById('units').textContent||'[]');
  var cur={tab:'all',proj:'all',fx:'all'};
  var AR=['backend','frontend','qa'], LBL={backend:'Backend',frontend:'Frontend',qa:'QA'};
  function pct(a,b){ return b?Math.round(a/b*100)+'%':'&ndash;'; }
  function d1(h){ return (Math.round(h/8*10)/10).toFixed(1); }   // hours -> days, 1 dp
  function esc(s){ var e=document.createElement('div'); e.textContent=(s==null?'':s); return e.innerHTML; }
  function vHit(v,fx){ return v===fx||v.indexOf(fx+'.')===0; }
  function fvMatch(fv,fx){ if(fx==='all')return true; if(!fv)return false; for(var i=0;i<fv.length;i++) if(vHit(fv[i],fx))return true; return false; }
  function tabMatch(u,t){ if(t==='all')return true; if(t==='us')return u.us; if(t==='usfinal')return u.usf; if(t==='bugfinal')return u.bugf; if(t==='other')return !u.us; return true; }
  function F(u){ return tabMatch(u,cur.tab) && (cur.proj==='all'||u.p===cur.proj) && fvMatch(u.fv,cur.fx); }

  function totTable(title, keyfn, label, rows){
    var by={}, order=[];
    rows.forEach(function(u){ var k=keyfn(u); if(!(k in by)){by[k]=[]; order.push(k);} by[k].push(u); });
    order.sort(function(a,b){ return a<b?1:(a>b?-1:0); });
    var out='<h2>'+title+'</h2><div class="tw"><table><thead><tr><th>'+label+'</th><th class="r">Tickets</th>'
      +'<th class="r">AI tickets</th><th class="r">% AI tickets</th><th class="r">Logged d</th><th class="r">AI logged d</th><th class="r">% AI logged</th></tr></thead><tbody>';
    var tT=0,tA=0,tL=0,tAL=0;
    order.forEach(function(k){ var g=by[k]; var n=g.length,
      na=g.filter(function(u){return u.ai>0;}).length,
      L=g.reduce(function(s,u){return s+u.lg;},0), AL=g.reduce(function(s,u){return s+u.ai;},0);
      tT+=n;tA+=na;tL+=L;tAL+=AL;
      out+='<tr><td class="name">'+esc(k)+'</td><td class="r">'+n+'</td><td class="r">'+na+'</td><td class="r">'+pct(na,n)
        +'</td><td class="r">'+d1(L)+'</td><td class="r aih">'+d1(AL)+'</td><td class="r">'+pct(AL,L)+'</td></tr>';
    });
    out+='<tr class="tot"><td class="name">Total</td><td class="r">'+tT+'</td><td class="r">'+tA+'</td><td class="r">'+pct(tA,tT)
      +'</td><td class="r">'+d1(tL)+'</td><td class="r aih">'+d1(tAL)+'</td><td class="r">'+pct(tAL,tL)+'</td></tr>';
    return out+'</tbody></table></div>';
  }
  function totArea(rows){ return totTable('Totals by area', function(u){return LBL[u.a];}, 'Area', rows); }
  function totMonth(rows){ return totTable('Totals by month', function(u){return u.m;}, 'Month', rows); }

  function details(rows){
    var no=rows.filter(function(u){return u.ai<=0;});
    var out='<h2>Details &mdash; tickets without AI logged time <span class="sm">('+no.length+' area-rows)</span></h2>';
    if(!no.length) return out+'<p class="dim">None in this view.</p>';
    AR.forEach(function(ar){
      var g=no.filter(function(u){return u.a===ar;}); if(!g.length) return;
      out+='<h3>'+LBL[ar]+' <span class="sm">('+g.length+')</span></h3>';
      var by={}; g.forEach(function(u){ (by[u.m]=by[u.m]||[]).push(u); });
      Object.keys(by).sort().reverse().forEach(function(m){
        var mr=by[m]; mr.sort(function(a,b){ return a.date<b.date?1:-1; });
        out+='<details open><summary>'+m+' <span class="cnt">('+mr.length+')</span></summary>'
          +'<div class="tw"><table><thead><tr><th>Ticket</th><th>Date</th><th>Type</th><th>Fix ver</th><th>Title</th><th>Status</th><th class="r">Logged d</th><th>Area</th><th>Main dev</th></tr></thead><tbody>';
        mr.forEach(function(u){
          out+='<tr><td class="key"><a href="https://opencellsoft.atlassian.net/browse/'+u.k+'" target="_blank" rel="noopener">'+u.k+'</a></td>'
            +'<td class="sm">'+u.date+'</td><td>'+esc(u.t)+'</td><td class="sm">'+(u.fv.length?esc(u.fv.join(', ')):'&ndash;')+'</td>'
            +'<td class="ti">'+esc(u.title)+'</td><td>'+esc(u.status)+'</td><td class="r">'+d1(u.lg)+'</td><td>'+LBL[ar]+'</td><td class="name">'+esc(u.dev)+'</td></tr>';
        });
        out+='</tbody></table></div></details>';
      });
    });
    return out;
  }

  function render(){
    var rows=U.filter(F);
    document.getElementById('content').innerHTML = totArea(rows)+totMonth(rows)+details(rows);
    var TABS={'tab-all':'all','tab-us':'us','tab-usfinal':'usfinal','tab-bugfinal':'bugfinal','tab-other':'other'};
    for(var id in TABS){ var b=document.getElementById(id); if(!b) continue;
      var n=U.filter(function(u){ return tabMatch(u,TABS[id]) && (cur.proj==='all'||u.p===cur.proj) && fvMatch(u.fv,cur.fx); }).length;
      var c=b.querySelector('.cnt'); if(c) c.textContent='('+n+')';
      if(TABS[id]===cur.tab) b.classList.add('active'); else b.classList.remove('active');
    }
  }
  document.getElementById('tabbar').addEventListener('click', function(ev){ var b=ev.target.closest('button'); if(!b)return; cur.tab=b.getAttribute('data-tab'); render(); });
  var ps=document.getElementById('projfilter'), fs=document.getElementById('fixvfilter');
  if(ps) ps.addEventListener('change', function(){ cur.proj=this.value; render(); });
  if(fs) fs.addEventListener('change', function(){ cur.fx=this.value; render(); });
  render();
})();
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issues", required=True); ap.add_argument("--tempo", required=True)
    ap.add_argument("--devmap", required=True); ap.add_argument("--cutoff", default="2026-09-01")
    ap.add_argument("--project", default="INTRD,MACRD,PRT730"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ns = nodes(json.load(open(a.issues, encoding="utf-8")))
    tempo = json.load(open(a.tempo, encoding="utf-8"))
    devmap = json.load(open(a.devmap, encoding="utf-8"))
    units, status_seen = build_units(ns, tempo, devmap, a.cutoff)
    import sys
    sys.stderr.write(f"units: {len(units)} (ticket x area)\n")
    sys.stderr.write("statuses seen (total owners); '<=' marks the in-scope set:\n")
    for s, c in sorted(status_seen.items(), key=lambda kv: -kv[1])[:30]:
        sys.stderr.write(f"   {c:5}  {s!r}{'  <=' if s.lower() in STATUS_SET else ''}\n")

    projects = sorted({u["p"] for u in units})
    fixvers = sorted({v for u in units for v in u["fv"]})
    vopts = version_options(fixvers)
    proj_opts = '<option value="all">All projects</option>' + "".join(f'<option value="{e(p)}">{e(p)}</option>' for p in projects)
    ver_opts = '<option value="all">All versions</option>' + "".join(f'<option value="{e(val)}">{e(lbl)}</option>' for val, lbl in vopts)
    tabs = [("tab-all", "all", "All"), ("tab-us", "us", "User Stories (All)"), ("tab-usfinal", "usfinal", "User Stories (Final)"),
            ("tab-bugfinal", "bugfinal", "Bugs (Final)"), ("tab-other", "other", "Bugs and Others")]
    tabbar = "".join(f'<button id="{tid}" data-tab="{tk}"{" class=\"active\"" if tk=="all" else ""}>{e(lbl)} <span class="cnt"></span></button>' for tid, tk, lbl in tabs)

    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
           f"<title>Non-AI work report — {e(a.project)} &ge;{e(a.cutoff)}</title><style>{CSS}</style></head><body>"
           "<h1>Non-AI work report <span class='sm'>(tickets in test/review/done without AI-logged time)</span></h1>"
           f"<p class=\"meta\">Project <b>{e(a.project)}</b> &middot; ticket-date &ge; <b>{e(a.cutoff)}</b> &middot; "
           "status in <b>In Test / Need sync (after dev) / Ready for Test / Ready for Sprint Review / Done</b> &middot; "
           "sub-tasks rolled into their US, sub-bugs kept as their own rows &middot; one row per ticket &times; dev area (overhead excluded).</p>"
           '<div class="filterbar"><label><b>Project:</b> <select id="projfilter">' + proj_opts + '</select></label> &nbsp; '
           '<label><b>Fix version:</b> <select id="fixvfilter">' + ver_opts + '</select></label> '
           '<span class="sm">versions grouped by release line (e.g. 17.x, 17.2.x); filters + tabs recompute live.</span></div>'
           '<div class="tabbar" id="tabbar">' + tabbar + '</div>'
           '<div id="content"></div>'
           '<div class="foot"><b>Field guide.</b> A <b>unit</b> is one ticket &times; one dev area. '
           'A unit <b>has AI</b> when it has AI-classified logged time (a worklog is AI when its author holds an AI-metrics record on the issue; a US record propagates to its non-bug sub-tasks; a sub-bug uses its own record). '
           '<b>Totals by area / by month</b> count every in-scope unit (with and without AI) to give the AI-adoption share. '
           '<b>Details</b> list only the units with <b>no</b> AI logged time &mdash; the work that reached test/review/done without AI. '
           'Sub-tasks roll into their parent US; sub-bugs are separate rows; overhead (PO/Archi/DevOps/Consultant) is excluded. All times in days (1 d = 8 h). Ticket-date = resolutiondate, else updated.</div>'
           '<script id="units" type="application/json">' + json.dumps(units, separators=(",", ":")) + '</script>'
           '<script>' + JS + '</script>'
           "</body></html>")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(doc)
    print(f"Wrote {a.out} ({len(doc)} bytes, {len(units)} units)")

if __name__ == "__main__":
    main()
```

## Notes & limitations

- **Unit = ticket × dev area.** A ticket worked by two areas is counted under each; "% AI" is therefore a per-area adoption rate, and a no-AI ticket appears in Details under each area that worked it with no AI.
- **Sub-bugs are their own rows** (not rolled under the US); **non-bug sub-tasks roll up** into their parent US. **Overhead is excluded.**
- **Cutoff applies to the whole report** (Totals and Details), so the % AI reflects the AI-era only.
- **Shared data with `/oc-time-report`.** Same `jira_fetch_dates.py`, `fetch_tempo_users.py` (and Tempo cache) and roster — only the aggregation differs. If both are run in one session, the `issues.json`/`tempo.json` can be reused (but note the time report fetches from its own `--since`, which may be earlier).
- **Read-only** — never writes to Jira, Tempo or git.

---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period. AI metrics grouped by developer domain (backend/frontend/QA); per-area Architect estimate (custom fields) and Dev-lead estimate (ticket field / sum of child sub-task estimates); ticket type; bug counts and hours-logged-on-bugs per area; logged hours per user & ticket via the Tempo API (fallback Jira worklogs); time gain without/with bug hours; sections ordered Totals → Summary → Detail. Fetches Jira via direct Cloud REST (enhanced /search/jql, fields-limited, no descriptions, paginated) using a mandatory JIRA_API_TOKEN — no Atlassian MCP; Tempo optional. Prints Markdown and writes a styled, date-stamped HTML file to ./docs/ai-usage-report-<date>.html.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH]"
---

## Purpose

Aggregate the machine-readable **AI-usage records** that `/oc-be-calculate-ai-use` (and the future frontend / QA equivalents) write to the **"AI metrics"** field (`customfield_10745`), across many tickets over a time window, into one report:

- A **summary table by user** (one row per developer, aggregated), then **details per user by ticket**, then **totals by area** (a plain sum of the detail rows).
- **AI metrics** (contribution / retention / tests / requests) are grouped by each record's **domain** (`backend`/`frontend`/`qa`, per developer). Each detail row also shows the **ticket type** (US / Bug / Enabler) and **two estimates per area**: **A. Est h** (Architect) from the Story's estimate custom fields — *Architect estimate back* (`customfield_10157`), *front* (`customfield_10158`), *QA estimate* (`customfield_10189`), days ×8, else the ticket's own estimate; and **DL. Est h** (Dev-lead) from the ticket's *estimation field* — for a User Story the sum of that area's child **sub-task** estimates (sub-bug estimates excluded), for a Bug/Enabler the ticket's own estimate. A **Sub-bugs** count and a separate **Sub-bug h** (hours logged on child Bug/Sub-bug sub-issues) are attributed per area. **Logged hours** are per user & ticket (booked on the parent): Tempo per-user → Jira worklog → ticket total. Plus a **time-gain %** (Architect estimate vs. logged, shown **with / without** bug hours) — in every **aggregate** row (area, user, month, KPI card) the gain is computed over **only the tickets carrying that estimate**, so an unestimated ticket contributes neither its estimate nor its logged hours. Every **ticket key is a link** to `https://opencellsoft.atlassian.net/browse/<KEY>`. Sections are ordered **Totals by area → Summary by user → Detail per user**, and users are ordered **by area, then name**. A cross-area sub-bug (one whose component area has no AI record on the ticket) is not mixed into another area's numbers — it is shown as an annotation like **`2 (front +1 7.8h)`**.

This command is **read-only** — it only queries Jira. It needs **no** Bitbucket token, **no** git, and **no** repo checkout; it can run from any directory.

## Access

Requires **`JIRA_API_TOKEN`** (+ **`JIRA_EMAIL`**, default `andrius.karpavicius@opencellsoft.com`) — an Atlassian API token (*id.atlassian.com → Security → API tokens*). All Jira reads go through the **Jira Cloud REST enhanced search** (`POST https://opencellsoft.atlassian.net/rest/api/3/search/jql`, Basic auth `email:token`) via `ai_jira_fetch.py` below. The token is **mandatory** and read from the environment (never on the command line); if unset, tell the user to create one and stop. **Do not use the Atlassian MCP `searchJiraIssuesUsingJql`** — it force-includes each issue's full `description` and caps at ~5 issues/call with no cursor. Direct REST honours the `fields` list (excludes `description`), returns 100/page and paginates via `nextPageToken`.

> **Tempo (per-user logged time).** Tempo syncs its worklogs into Jira under the **Tempo app account**, so Jira alone can't attribute logged time per developer. For true per-user hours, set **`TEMPO_API_TOKEN`** (each developer makes their own in *Tempo → Settings → API keys*, worklog **read** scope) and the report calls the Tempo REST API (`api.tempo.io/4`) in Pass C. It is **optional**: without the token the report falls back to the Jira `worklog` / `timespent` fields (ticket total). The token is read from the environment, never passed on the command line.

## Arguments

Parse `$ARGUMENTS` — **all optional**. A bare `/oc-ai-report` reports the **last 30 days** for **INTRD**.

- `--since YYYY-MM-DD` — start of the period (inclusive), matched against each record's `at`. **Default: 30 days before `--until`.**
- `--until YYYY-MM-DD` — end of the period (exclusive). **Default: tomorrow** (so today's records are included).
- `--project KEY` — Jira project. **Default: `INTRD`.**
- `--out PATH` — where to write the HTML report. **Default: `./docs/ai-usage-report-<TODAY>.html`** where `<TODAY>` is the run date (`date -u +%Y-%m-%d`), e.g. `./docs/ai-usage-report-2026-08-05.html` (relative to the current directory; the `docs/` folder is created if missing).
- `--csv PATH` — also write the **ticket-detail rows** as CSV (spreadsheet-friendly). **Default: `./docs/ai-usage-report-<TODAY>.csv`** (same folder/date-stamp as the HTML).

Compute any missing date with the shell — `date -u +%Y-%m-%d` (today), `date -u -d 'tomorrow' +%Y-%m-%d`, `date -u -d '30 days ago' +%Y-%m-%d`; if `date -d` is unavailable, use Python `datetime`. Echo the resolved window back to the user (e.g. "Reporting INTRD, 2026-07-04 → 2026-08-03") so the defaults are visible.

## Task 1 — Fetch the tickets (two passes: parents, then sub-issues)

Only Jira dates are JQL-filterable (the record's `at` lives *inside* the text field), so cast a slightly wide net on `updated` and let the aggregator do the precise `at` filtering. Writing the AI record updates the ticket, so `updated >= since` never drops an in-period record.

**Why two passes.** AI metrics are grouped by the record key's **domain** (`backend`/`frontend`/`qa`, per developer). The **Architect estimate (A. Est h)** is on the parent (per-area custom fields). But the **Dev-lead estimate (DL. Est h)** for a User Story is the **sum of its child sub-tasks' estimates** per area, and **bug counts / bug-logged hours** come from its child **Bug / Sub-bug** sub-issues — neither the subtasks' estimates nor their `timespent`/area are in the parent payload, so a second fetch of the children is needed.

**Both passes in one script.** Write `ai_jira_fetch.py` (below) to scratchpad and run it — it does Pass A and Pass B via the Jira REST enhanced-search endpoint (fields-limited, `description` excluded, 100/page, `nextPageToken` paging) and writes `tickets.json` + `children.json`:

```bash
python "<SCRATCHPAD>/ai_jira_fetch.py" --since [SINCE] --project [PROJECT] \
  --out-tickets "<SCRATCHPAD>/tickets.json" --out-children "<SCRATCHPAD>/children.json"
```

- **Pass A** runs `project = [PROJECT] AND cf[10745] IS NOT EMPTY AND updated >= "[SINCE]"` with fields `["summary","assignee","issuetype","status","resolutiondate","updated","timeoriginalestimate","timespent","worklog","components","customfield_10157","customfield_10158","customfield_10189","customfield_10745","customfield_10613"]` → `tickets.json`. If it returns 0 tickets, tell the user "No tickets with AI-metrics data found for [PROJECT] since [SINCE]" and stop.
- **Pass B** fetches every child sub-issue of those parents (`parent in (<keys>)`, batched) with `["summary","issuetype","components","timeoriginalestimate","timespent","parent"]` → `children.json`. Both regular sub-tasks and Bug/Sub-bug sub-tasks are needed: non-bug sub-tasks feed the Dev-lead estimate, Bug/Sub-bug ones feed the bug count and Sub-bug h. **Issue links are deliberately NOT used.**

Notes on the fields:
- `status` drives the **Status** column and the **Final** flag in the *Detail per user* tables: a ticket is *final* when its Jira status (case-insensitive) is terminal for its type — **Bug**: Done/Invalid; **US**: Ready for Sprint review / Need documentation / Ready for release / Released; **any other type**: Done. **AI Contrib below 60% is shown in red** in both the *Summary by user* and *Detail per user* tables.
- The three estimate custom fields (**days**) are the per-area estimates on a User Story: `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate*. The aggregator converts days → hours (×8) and, if none are set (a standalone Bug), falls back to the ticket's own `timeoriginalestimate`. Sub-issue estimates are **never summed**.

**Pass C — per-user logged time from Tempo (optional but preferred):**
5. Tempo Timesheets syncs its worklogs into the Jira `worklog` field **under the Tempo app account**, so Jira alone cannot split logged time per developer. Tempo's own REST API keeps the real `author.accountId`. If the environment variable **`TEMPO_API_TOKEN`** is set (each developer creates their own token in *Tempo → Settings → API keys*, worklog **read** scope), fetch true per-user hours; otherwise skip and the aggregator falls back to Jira worklogs / ticket total.
6. Write `fetch_tempo.py` (below) to scratchpad and run it with the **numeric issue ids** of the parents (`node.id` from Pass A) **and the bug sub-issues** (from Pass B) — so both the ticket's per-user logged hours and the per-user *Bug h* can be resolved:
   ```bash
   python "<SCRATCHPAD>/fetch_tempo.py" --ids "93179,107118,109478,<bug-ids…>" --out "<SCRATCHPAD>/tempo.json"
   ```
   It reads `TEMPO_API_TOKEN` from the environment (never pass the token on the command line), calls `GET https://api.tempo.io/4/worklogs/issue/{id}` (paginated via `metadata.next`), and writes `{"<issueId>": {"<accountId>": seconds}}`. On a missing token or a 401 it writes `{}` and the report still runs (logged falls back to Jira worklog / ticket total; Bug h to the bug's `timespent`).

### `ai_jira_fetch.py`

```python
#!/usr/bin/env python3
"""Fetch the AI-usage report's tickets via direct Jira Cloud REST (enhanced JQL search).
Pass A = tickets carrying an AI-metrics record; Pass B = their child sub-issues.
Honours `fields` (excludes description), paginates via nextPageToken. Auth: JIRA_EMAIL:JIRA_API_TOKEN."""
import os, sys, json, time, base64, argparse, urllib.request, urllib.error
BASE="https://opencellsoft.atlassian.net"
EMAIL=os.environ.get("JIRA_EMAIL") or "andrius.karpavicius@opencellsoft.com"
TOK=os.environ["JIRA_API_TOKEN"]
AUTH=base64.b64encode(f"{EMAIL}:{TOK}".encode()).decode()
# Pass A carries the AI record + estimates + worklog (Jira fallback) + AI tag
FIELDS_A=["summary","assignee","issuetype","status","resolutiondate","updated","timeoriginalestimate",
          "timespent","worklog","components","customfield_10157","customfield_10158","customfield_10189",
          "customfield_10745","customfield_10613"]
FIELDS_B=["summary","issuetype","components","timeoriginalestimate","timespent","parent"]

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

def fetch_jql(jql, fields):
    nodes=[]; token=None
    while True:
        body={"jql":jql,"fields":fields,"maxResults":100}
        if token: body["nextPageToken"]=token
        d=post("/rest/api/3/search/jql", body)
        nodes+=d.get("issues") or []
        if d.get("isLast") or not d.get("nextPageToken"): break
        token=d["nextPageToken"]
    return nodes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--since", required=True); ap.add_argument("--project", default="INTRD")
    ap.add_argument("--out-tickets", required=True); ap.add_argument("--out-children", required=True)
    a=ap.parse_args()
    # Pass A — parent tickets that carry an AI-metrics record (customfield_10745 not empty)
    jqlA=f'project = {a.project} AND cf[10745] IS NOT EMPTY AND updated >= "{a.since}" ORDER BY updated DESC'
    parents=fetch_jql(jqlA, FIELDS_A)
    json.dump({"issues":{"nodes":parents}}, open(a.out_tickets,"w",encoding="utf-8"))
    sys.stderr.write(f"Pass A: {len(parents)} tickets with AI records\n")
    # Pass B — every child sub-issue of those parents (for Dev-lead estimate, bug counts, Sub-bug h)
    keys=[n["key"] for n in parents]
    children=[]
    for i in range(0,len(keys),100):
        children+=fetch_jql("parent in ("+",".join(keys[i:i+100])+")", FIELDS_B)
    json.dump({"issues":{"nodes":children}}, open(a.out_children,"w",encoding="utf-8"))
    sys.stderr.write(f"Pass B: {len(children)} child sub-issues\n")

if __name__=="__main__": main()
```

### `fetch_tempo.py`

```python
#!/usr/bin/env python3
"""Fetch per-user logged seconds per issue from the Tempo API and write
{"<issueId>": {"<accountId>": seconds}} to --out. Reads the token from the
TEMPO_API_TOKEN environment variable (never passed on the command line). If the
token is unset or the call fails, writes {} so the report falls back to Jira worklogs."""
import argparse, json, os, sys, urllib.request, urllib.error

BASE = "https://api.tempo.io/4"

def sum_results(results):
    per = {}
    for w in results or []:
        acc = (w.get("author") or {}).get("accountId")
        if acc:
            per[acc] = per.get(acc, 0) + (w.get("timeSpentSeconds") or 0)
    return per

def fetch_issue(issue_id, token):
    """Return ({accountId: seconds}, http_status). Follows metadata.next pagination."""
    per = {}
    url = f"{BASE}/worklogs/issue/{issue_id}?limit=1000"
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"Tempo issue {issue_id}: HTTP {ex.code}\n"); return per, ex.code
        except Exception as ex:  # noqa
            sys.stderr.write(f"Tempo issue {issue_id}: {ex}\n"); return per, None
        for acc, secs in sum_results(data.get("results")).items():
            per[acc] = per.get(acc, 0) + secs
        url = (data.get("metadata") or {}).get("next")
    return per, 200

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)   # comma-separated numeric issue ids
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    token = os.environ.get("TEMPO_API_TOKEN")
    out = {}
    if not token:
        sys.stderr.write("TEMPO_API_TOKEN not set — skipping Tempo; report falls back to Jira worklogs.\n")
        json.dump(out, open(a.out, "w")); return
    ids = [i.strip() for i in a.ids.split(",") if i.strip()]
    ok = 0
    for iid in ids:
        per, code = fetch_issue(iid, token)
        if code == 401:
            sys.stderr.write("Tempo 401 — bad/expired token; falling back to Jira worklogs.\n"); out = {}; break
        if per:
            out[iid] = per; ok += 1
    json.dump(out, open(a.out, "w"))
    sys.stderr.write(f"Tempo: {ok}/{len(ids)} issues had worklogs.\n")

if __name__ == "__main__":
    main()
```

## Task 2 — Run the aggregator

Write the script below to your scratchpad as `ai_report.py` and run it (Python 3 is available as `python`):

```bash
python "<SCRATCHPAD>/ai_report.py" --input "<SCRATCHPAD>/tickets.json" --children "<SCRATCHPAD>/children.json" --tempo "<SCRATCHPAD>/tempo.json" --since [SINCE] --until [UNTIL]
```

(`--children`/`--tempo` are optional; omit if that pass was skipped.) It prints a Markdown report in this order: **Totals by area** (a plain sum of the detail rows), **Summary by user**, then **Detail per user by ticket** (which also shows ticket type). AI metrics group by the record's **domain**; **A. Est h** (Architect) per area from the Story's estimate custom fields; **DL. Est h** (Dev-lead) per area from the ticket estimation field (US → sum of child sub-task estimates, else the ticket estimate); **bug counts** and **Sub-bug h** per area from child Bug/Sub-bug sub-issues; **logged hours** per user & ticket. Display it to the user verbatim.

### `ai_report.py`

```python
#!/usr/bin/env python3
"""AI-usage report. AI metrics grouped by record domain. Estimate hours come from per-area
Architect/QA estimate custom fields on the Story (days x8), else the ticket's own estimate
(sub-issue estimates are never summed). Sub-bug counts and bug-logged hours come from Bug/Sub-bug
sub-issues, per area. Aggregate gains use only the rows that carry the matching estimate. Logged hours are per user & ticket (Tempo per-user -> Jira -> ticket total).
Totals = plain sum of the detail rows."""
import argparse, json, re
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8            # Jira workday
BUG_TYPES = {"bug", "sub-bug"}
JIRA_BROWSE = "https://opencellsoft.atlassian.net/browse/"   # ticket keys render as links

def recover_json(val):
    if val is None: return None
    if isinstance(val, str): return val
    if isinstance(val, dict):
        out = []
        def walk(n):
            if isinstance(n, dict):
                if n.get("type") == "text" and isinstance(n.get("text"), str): out.append(n["text"])
                for c in n.get("content") or []: walk(c)
            elif isinstance(n, list):
                for c in n: walk(c)
        walk(val); return "".join(out)
    return None

def nodes(data):
    issues = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(issues, dict): issues = issues.get("nodes", [])
    return issues or []

def hours(s): return round((s or 0) / 3600, 1)
def num(x): return x if isinstance(x, (int, float)) else 0

def area_of(fields):
    for c in fields.get("components") or []:
        a = COMP_AREA.get((c.get("name") or "").strip().lower())
        if a: return a
    m = _TAG.search(fields.get("summary") or "")
    if m: return {"back": "backend", "front": "frontend", "test": "qa"}[m.group(1).lower()]
    return None

def worklog_by_user(worklog):
    per = defaultdict(int)
    for w in (worklog or {}).get("worklogs") or []:
        per[(w.get("author") or {}).get("accountId")] += w.get("timeSpentSeconds", 0) or 0
    return per

def is_bug(fields): return ((fields.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES

FOREIGN_SHORT = {"backend": "back", "frontend": "front", "qa": "qa"}
def record_domains(pf):
    """Set of areas (AREAS) that carry an AI-metrics record on this ticket."""
    raw = recover_json(pf.get("customfield_10745")); doms = set()
    if raw:
        try: doc = json.loads(raw)
        except json.JSONDecodeError: doc = None
        for rk in ((doc or {}).get("records") or {}):
            parts = rk.split("/", 2)
            if parts and parts[0] in AREAS: doms.add(parts[0])
    return doms
def merge_foreign(dst, src):
    for a, c in (src or {}).items(): dst[a] = dst.get(a, 0) + c
def sum_foreign(rows):
    d = {}
    for r in rows: merge_foreign(d, r.get("bugsForeign"))
    return d
def sum_foreign_h(rows):
    d = {}
    for r in rows:
        for a, h in (r.get("bugsForeignH") or {}).items(): d[a] = round(d.get(a, 0.0) + h, 1)
    return d
def bugs_label(n, foreign, foreign_h=None):
    """Own-area sub-bug count, annotating cross-area sub-bugs (count + total hours) that this
    report keeps OUT of the area's numbers, e.g. '2 (front +1 7.8h)'."""
    if foreign:
        fh = foreign_h or {}
        extra = ", ".join(f"{FOREIGN_SHORT.get(a, a)} +{c} {fh.get(a, 0)}h" for a, c in sorted(foreign.items()))
        return f"{n} ({extra})"
    return f"{n}"

TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Bug", "enabler": "Enabler"}
def ticket_type(pf):
    n = (pf.get("issuetype") or {}).get("name") or ""
    return TYPE_MAP.get(n.lower(), n or "?")
# terminal status per ticket type (case-insensitive):
FINAL_STATUS = {
    "Bug": {"done", "invalid"},
    "US": {"ready for sprint review", "need documentation", "ready for release", "released"},
}
DEFAULT_FINAL = {"done"}
def status_of(pf): return ((pf.get("status") or {}).get("name") or "").strip()
def is_final(ttype, status): return (status or "").strip().lower() in FINAL_STATUS.get(ttype, DEFAULT_FINAL)

def area_estimate_h(pf, area):
    """Architect estimate (A. Est h) in hours. If any per-area estimate custom field is set
    (a Story), use that area's field (days x8); a field absent for that area => 0. Otherwise
    (a standalone Bug/Enabler) fall back to the ticket's own timeoriginalestimate."""
    vals = {ar: pf.get(f) for ar, f in AREA_EST_FIELD.items()}
    if any(isinstance(v, (int, float)) for v in vals.values()):
        v = vals.get(area)
        est = round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    else:
        est = hours(pf.get("timeoriginalestimate"))
    return 0.0 if 0 < est < EST_MIN else est  # a placeholder like 0.01d (~0.1h) counts as no estimate -> 0

def bug_logged_h(bug_nodes, acc, tempo):
    """Hours logged on the given bug sub-issues for this user: Tempo per-user if available,
    else the bug's own timespent (whole)."""
    total = 0.0
    for b in bug_nodes:
        bid = str(b.get("id")); bf = b.get("fields", {}) or {}
        tw = tempo.get(bid, {})
        total += hours(tw.get(acc)) if acc in tw else hours(bf.get("timespent"))
    return round(total, 1)

GAIN_CAP = 1000  # |time gain %| beyond this is placeholder-driven noise -> show "-"
EST_MIN = 0.5    # estimates at/below this (e.g. a 0.01-day placeholder ~= 0.1h) are meaningless
def gain_pct(est, logged):
    if not est or est < EST_MIN or not logged or logged <= 0:
        return None  # placeholder estimate or no logged time -> gain is nonsense
    return round((est - logged) / est * 100)
def gain_str(g): return "-" if (g is None or abs(g) > GAIN_CAP) else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_two(est, logged, bug):
    """Time gain WITH / WITHOUT bug hours: (est-(logged+bug))/est  /  (est-logged)/est."""
    return f"{gain_str(gain_pct(est, logged + bug))} / {gain_str(gain_pct(est, logged))}"
def gain_basis(rows, est_key):
    """(estimate, logged, bug) summed over ONLY the rows that carry a usable estimate for
    est_key. A ticket with no estimate contributes neither its 0 estimate nor its logged
    hours, so it cannot drag a group's gain down; per-ticket rows already show "-"."""
    est = logged = bug = 0.0
    for r in rows:
        if r[est_key] >= EST_MIN:
            est += r[est_key]; logged += r["logged"]; bug += r["bugLogged"]
    return round(est, 1), round(logged, 1), round(bug, 1)

def build_rows(parents, children, tempo, since, until):
    ch_by_parent = defaultdict(list)
    for c in children:
        cf = c.get("fields", {}) or {}
        pk = (cf.get("parent") or {}).get("key")
        if pk: ch_by_parent[pk].append(c)

    # From the ticket's OWN child sub-issues only (never issue links): Bug/Sub-bug -> count + Sub-bug h;
    # non-bug sub-tasks -> Dev-lead estimate (DL. Est h), summed per area (sub-bug estimates excluded).
    p_bugs = {}; p_dl = {}; p_has_sub = {}; p_foreign_ct = {}; p_foreign_hr = {}
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw_bugs = {ar: [] for ar in AREAS}; dl_by_area = {ar: 0.0 for ar in AREAS}
        pa = area_of(pf); saw_sub = False; rec_areas = record_domains(pf)
        for c in ch_by_parent.get(key, []):
            cf = c.get("fields", {}) or {}
            if is_bug(cf):
                bar = area_of(cf)              # bugs: attributed by their OWN component/title only (no parent inheritance)
                if bar: raw_bugs[bar].append(c)
            else:
                ar = area_of(cf) or pa         # non-bug sub-tasks still inherit the parent area for the DL estimate
                saw_sub = True
                if ar: dl_by_area[ar] += hours(cf.get("timeoriginalestimate"))
        # Only own-area sub-bugs drive an area's count & Sub-bug h. A sub-bug whose area has no
        # AI record on the ticket is NOT mixed into another area's numbers (this report measures
        # per-area AI impact, and each area is a different developer) — it is surfaced only as an
        # annotation "(front +1 7.8h)" on a record area's cell, carrying its count and total hours.
        bugs_by_area = {ar: list(raw_bugs[ar]) if ar in rec_areas else [] for ar in AREAS}
        fct = {ar: {} for ar in AREAS}; fhr = {ar: {} for ar in AREAS}
        fallback = pa if pa in rec_areas else (sorted(rec_areas)[0] if rec_areas else None)
        if fallback:
            for ar in AREAS:
                if ar in rec_areas or not raw_bugs[ar]: continue
                fct[fallback][ar] = fct[fallback].get(ar, 0) + len(raw_bugs[ar])
                fhr[fallback][ar] = round(fhr[fallback].get(ar, 0.0)
                    + sum(hours((b.get("fields") or {}).get("timespent")) for b in raw_bugs[ar]), 1)
        p_bugs[key] = bugs_by_area; p_dl[key] = dl_by_area; p_has_sub[key] = saw_sub
        p_foreign_ct[key] = fct; p_foreign_hr[key] = fhr

    rows = []
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw = recover_json(pf.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError: continue
        summary = (pf.get("summary") or "")[:44]; ttype = ticket_type(pf)
        status = status_of(pf); final = is_final(ttype, status)
        parent_logged = hours(pf.get("timespent")); parent_est = hours(pf.get("timeoriginalestimate"))
        wl = worklog_by_user(pf.get("worklog")); tw = tempo.get(str(p.get("id")), {})
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]; name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if since and at and at < since: continue
            if until and at and at >= until: continue
            a_est = area_estimate_h(pf, domain)                                     # architect
            dl_est = round(p_dl[key][domain], 1) if p_has_sub[key] else parent_est  # dev-lead
            bug_nodes = p_bugs[key][domain]                     # own-area sub-bugs only
            foreign_ct = dict(p_foreign_ct[key][domain])        # {srcArea: n} cross-area, annotation only
            foreign_hr = dict(p_foreign_hr[key][domain])        # {srcArea: hours} cross-area, annotation only
            bug_logged = bug_logged_h(bug_nodes, acc, tempo)    # Sub-bug h = own-area only (no cross-area mixing)
            if acc in tw: logged = hours(tw.get(acc))
            elif acc in wl: logged = hours(wl.get(acc))
            else: logged = parent_logged
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key,
                         "ttype": ttype, "summary": summary, "status": status, "final": final,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "aEst": round(a_est, 1), "dlEst": round(dl_est, 1),
                         "logged": round(logged, 1), "bugLogged": bug_logged,
                         "bugs": len(bug_nodes), "bugsForeign": foreign_ct, "bugsForeignH": foreign_hr})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--children"); ap.add_argument("--tempo")
    ap.add_argument("--since"); ap.add_argument("--until")
    a = ap.parse_args()
    parents = nodes(json.load(open(a.input, encoding="utf-8")))
    children = nodes(json.load(open(a.children, encoding="utf-8"))) if a.children else []
    tempo = json.load(open(a.tempo, encoding="utf-8")) if a.tempo else {}
    rows = build_rows(parents, children, tempo, a.since, a.until)

    out = []; P = out.append
    if not rows:
        P("_No AI-usage records in this window._"); print("\n".join(out)); return
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else "-"
    SUM = ("utAdd", "utMod", "pmTests", "turns", "aEst", "dlEst", "logged", "bugLogged", "bugs")

    # ---- Totals by area (shown first) ----
    areas = {ar: {"contrib": [], "retain": [], "rows": [], **{k: 0 for k in SUM}} for ar in AREAS}
    for r in rows:
        g = areas[r["area"]]; g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        g["rows"].append(r)
        for k in SUM: g[k] += r[k]
    P("## Totals by area (sum of detail rows)\n")
    P("| Area | Rows | AI Contrib | Retain | Review phase | U.tests +/~ | P.tests | Requests | A. Est h | DL. Est h | Total dev h | Logged h | Sub-bug h | Arch gain | DL gain | Sub-bugs |")
    P("|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for ar in AREAS:
        g = areas[ar]
        if not g["contrib"]: continue
        P(f"| {ar.capitalize()} | {len(g['contrib'])} | {avg(g['contrib'])}% | {avg(g['retain'])}% | {avg([r['rework'] for r in g['rows']])}% | "
          f"{g['utAdd']}/{g['utMod']} | {g['pmTests']} | {g['turns']} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
          f"{round(g['logged'] + g['bugLogged'],1)} | {round(g['logged'],1)} | {round(g['bugLogged'],1)} | {gain_two(*gain_basis(g['rows'], 'aEst'))} | "
          f"{gain_two(*gain_basis(g['rows'], 'dlEst'))} | {bugs_label(g['bugs'], sum_foreign(g['rows']), sum_foreign_h(g['rows']))} |")

    # ---- Summary by user ----
    users = {}
    for r in rows:
        u = users.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
             "contrib": [], "retain": [], "rework": [], "rows": [], **{k: 0 for k in SUM}})
        u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"]); u["rows"].append(r)
        u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
        for k in SUM: u[k] += r[k]
    P("\n## Summary by user\n")
    P("| User | Area | Tickets | AI Contrib | Retain | Review phase | U.tests +/~ | P.tests | Requests | A. Est h | DL. Est h | Total dev h | Logged h | Sub-bug h | Arch gain | DL gain | Sub-bugs |")
    P("|---|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for acc, u in sorted(users.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
        ac = avg(u['contrib']); acc_cell = f"**{ac}%**" if ac < 60 else f"{ac}%"  # <60% flagged (red in HTML)
        P(f"| {u['name']} | {'/'.join(sorted(u['areas']))} | {len(u['tickets'])} | {acc_cell} | "
          f"{avg(u['retain'])}% | {avg(u['rework'])}% | {u['utAdd']}/{u['utMod']} | {u['pmTests']} | {u['turns']} | "
          f"{round(u['aEst'],1)} | {round(u['dlEst'],1)} | {round(u['logged'] + u['bugLogged'],1)} | {round(u['logged'],1)} | {round(u['bugLogged'],1)} | "
          f"{gain_two(*gain_basis(u['rows'], 'aEst'))} | {gain_two(*gain_basis(u['rows'], 'dlEst'))} | {bugs_label(u['bugs'], sum_foreign(u['rows']), sum_foreign_h(u['rows']))} |")

    # ---- Detail per user, by ticket ----
    P("\n## Detail per user")
    by_user = defaultdict(list)
    for r in rows: by_user[r["acc"]].append(r)
    for acc, u in sorted(users.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
        P(f"\n### {u['name']}\n")
        P("| Ticket | Date | Type | Area | Summary | Status | Final | AI Contrib | Retain | Review phase | U.tests +/~ | P.tests | Requests | A. Est h | DL. Est h | Total dev h | Logged h | Sub-bug h | Arch gain | DL gain | Sub-bugs |")
        P("|---|---|---|---|---|---|:--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
            c = r['contrib']
            cc = f"**{c}%**" if isinstance(c, (int, float)) and c < 60 else f"{c}%"  # <60% flagged (red in HTML)
            P(f"| [{r['key']}]({JIRA_BROWSE}{r['key']}) | {r['at']} | {r['ttype']} | {r['area']} | {r['summary']} | {r['status']} | {'T' if r['final'] else ''} | {cc} | {r['retain']}% | {r['rework']}% | "
              f"{r['utAdd']}/{r['utMod']} | {r['pmTests']} | {r['turns']} | {r['aEst']} | {r['dlEst']} | {round(r['logged'] + r['bugLogged'],1)} | {r['logged']} | "
              f"{r['bugLogged']} | {gain_two(r['aEst'], r['logged'], r['bugLogged'])} | {gain_two(r['dlEst'], r['logged'], r['bugLogged'])} | {bugs_label(r['bugs'], r['bugsForeign'], r['bugsForeignH'])} |")
    print("\n".join(out))

if __name__ == "__main__":
    main()
```

## Task 3 — Write the HTML report

Also render a **self-contained, styled HTML file** from the same `tickets.json`. Write the script below to your scratchpad as `ai_report_html.py` and run it, pointing `--out` at the resolved output path (default `./docs/ai-usage-report-<TODAY>.html`, `<TODAY>` = `date -u +%Y-%m-%d` — the date-stamp keeps successive reports side by side rather than overwriting):

```bash
python "<SCRATCHPAD>/ai_report_html.py" --input "<SCRATCHPAD>/tickets.json" \
  --children "<SCRATCHPAD>/children.json" --tempo "<SCRATCHPAD>/tempo.json" \
  --since [SINCE] --until [UNTIL] --project [PROJECT] \
  --out "./docs/ai-usage-report-[TODAY].html" --csv "./docs/ai-usage-report-[TODAY].csv"
```

The page is theme-aware (light/dark) and embeds all CSS — no external assets — so it opens straight from disk. **Five tabs (HTML only):** an **All** tab (every ticket, the default), a **User Stories (All)** tab (US only), a **User Stories (Final)** tab (US whose status is terminal, Final = T), a **Bugs (final)** tab (Bug/Sub-bug tickets in a terminal status) and a **Bugs and others** tab (every non-US ticket); each tab holds the full report (KPI cards + the three sections) filtered to that ticket set. Tabs are pure CSS (`<input type="radio">` + `:checked` sibling selectors) — no JavaScript. Within each tab, KPI cards lead, then the three sections mirroring the Markdown. **Grouping (HTML only):** *Totals by area* shows the overall table, then an expandable `<details>` block per month (the date is the record's `at`, newest open). *Summary by user* shows the overall one-row-per-user table (each developer's name **links down to their Detail-per-user section** in the same tab), then an expandable `<details>` block **per user**, each holding that developer's month-by-month breakdown (user → month). *Detail per user* groups each developer's tickets into expandable months, and every ticket key is a link to its Jira issue. (Anchor ids are prefixed per tab, so the same developer is uniquely addressable in each tab.) Tell the user the absolute path and that they can open it in a browser (Windows: `start "" "<path>"`).

`--csv` additionally writes the **ticket-detail rows** (one row per ticket × developer, all detail columns, both time-gain values and a trailing **URL** column with the ticket's Jira link) to a spreadsheet-friendly CSV (UTF-8 with BOM so Excel renders accented names). Default `./docs/ai-usage-report-<TODAY>.csv`. Report both file paths to the user.

### `ai_report_html.py`

```python
#!/usr/bin/env python3
"""Render the AI-usage report as a self-contained, styled HTML file. AI metrics grouped by record
domain. Estimate hours from per-area Architect/QA estimate custom fields on the Story (days x8),
else the ticket's own estimate. Sub-bug counts & bug-logged hours from Bug/Sub-bug sub-issues, per area.
Aggregate gains use only the rows carrying that estimate; ticket keys link to Jira.
Logged hours per user & ticket (Tempo per-user -> Jira -> ticket total). Totals = sum of detail rows."""
import argparse, json, re, html, csv, os
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8
BUG_TYPES = {"bug", "sub-bug"}
JIRA_BROWSE = "https://opencellsoft.atlassian.net/browse/"   # ticket keys render as links

def recover_json(val):
    if val is None: return None
    if isinstance(val, str): return val
    if isinstance(val, dict):
        out = []
        def walk(n):
            if isinstance(n, dict):
                if n.get("type") == "text" and isinstance(n.get("text"), str): out.append(n["text"])
                for c in n.get("content") or []: walk(c)
            elif isinstance(n, list):
                for c in n: walk(c)
        walk(val); return "".join(out)
    return None

def nodes(data):
    issues = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(issues, dict): issues = issues.get("nodes", [])
    return issues or []

def hours(s): return round((s or 0) / 3600, 1)
def num(x): return x if isinstance(x, (int, float)) else 0

def area_of(fields):
    for c in fields.get("components") or []:
        a = COMP_AREA.get((c.get("name") or "").strip().lower())
        if a: return a
    m = _TAG.search(fields.get("summary") or "")
    if m: return {"back": "backend", "front": "frontend", "test": "qa"}[m.group(1).lower()]
    return None

def worklog_by_user(worklog):
    per = defaultdict(int)
    for w in (worklog or {}).get("worklogs") or []:
        per[(w.get("author") or {}).get("accountId")] += w.get("timeSpentSeconds", 0) or 0
    return per

def is_bug(fields): return ((fields.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES

FOREIGN_SHORT = {"backend": "back", "frontend": "front", "qa": "qa"}
def record_domains(pf):
    """Set of areas (AREAS) that carry an AI-metrics record on this ticket."""
    raw = recover_json(pf.get("customfield_10745")); doms = set()
    if raw:
        try: doc = json.loads(raw)
        except json.JSONDecodeError: doc = None
        for rk in ((doc or {}).get("records") or {}):
            parts = rk.split("/", 2)
            if parts and parts[0] in AREAS: doms.add(parts[0])
    return doms
def merge_foreign(dst, src):
    for a, c in (src or {}).items(): dst[a] = dst.get(a, 0) + c
def sum_foreign(rows):
    d = {}
    for r in rows: merge_foreign(d, r.get("bugsForeign"))
    return d
def sum_foreign_h(rows):
    d = {}
    for r in rows:
        for a, h in (r.get("bugsForeignH") or {}).items(): d[a] = round(d.get(a, 0.0) + h, 1)
    return d
def bugs_label(n, foreign, foreign_h=None):
    """Own-area sub-bug count, annotating cross-area sub-bugs (count + total hours) that this
    report keeps OUT of the area's numbers, e.g. '2 (front +1 7.8h)'."""
    if foreign:
        fh = foreign_h or {}
        extra = ", ".join(f"{FOREIGN_SHORT.get(a, a)} +{c} {fh.get(a, 0)}h" for a, c in sorted(foreign.items()))
        return f"{n} ({extra})"
    return f"{n}"

TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Bug", "enabler": "Enabler"}
def ticket_type(pf):
    n = (pf.get("issuetype") or {}).get("name") or ""
    return TYPE_MAP.get(n.lower(), n or "?")
# terminal status per ticket type (case-insensitive):
FINAL_STATUS = {
    "Bug": {"done", "invalid"},
    "US": {"ready for sprint review", "need documentation", "ready for release", "released"},
}
DEFAULT_FINAL = {"done"}
def status_of(pf): return ((pf.get("status") or {}).get("name") or "").strip()
def is_final(ttype, status): return (status or "").strip().lower() in FINAL_STATUS.get(ttype, DEFAULT_FINAL)

def area_estimate_h(pf, area):
    vals = {ar: pf.get(f) for ar, f in AREA_EST_FIELD.items()}
    if any(isinstance(v, (int, float)) for v in vals.values()):
        v = vals.get(area)
        est = round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    else:
        est = hours(pf.get("timeoriginalestimate"))
    return 0.0 if 0 < est < EST_MIN else est  # a placeholder like 0.01d (~0.1h) counts as no estimate -> 0

def bug_logged_h(bug_nodes, acc, tempo):
    total = 0.0
    for b in bug_nodes:
        bid = str(b.get("id")); bf = b.get("fields", {}) or {}
        tw = tempo.get(bid, {})
        total += hours(tw.get(acc)) if acc in tw else hours(bf.get("timespent"))
    return round(total, 1)

GAIN_CAP = 1000  # |time gain %| beyond this is placeholder-driven noise -> show dash
EST_MIN = 0.5    # estimates at/below this (e.g. a 0.01-day placeholder ~= 0.1h) are meaningless
def gain_pct(est, logged):
    if not est or est < EST_MIN or not logged or logged <= 0:
        return None  # placeholder estimate or no logged time -> gain is nonsense
    return round((est - logged) / est * 100)
def gain_str(g): return "—" if (g is None or abs(g) > GAIN_CAP) else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_two(est, logged, bug):  # WITH / WITHOUT bug hours
    return f"{gain_str(gain_pct(est, logged + bug))} / {gain_str(gain_pct(est, logged))}"
def gain_basis(rows, est_key):
    """(estimate, logged, bug) summed over ONLY the rows with a usable estimate for est_key,
    so an unestimated ticket cannot distort a group's gain (per-ticket rows already show a dash)."""
    est = logged = bug = 0.0
    for r in rows:
        if r[est_key] >= EST_MIN:
            est += r[est_key]; logged += r["logged"]; bug += r["bugLogged"]
    return round(est, 1), round(logged, 1), round(bug, 1)
def gain_cell(est, logged):  # CSV: capped integer or dash
    g = gain_pct(est, logged)
    return "-" if (g is None or abs(g) > GAIN_CAP) else g
def gain_cls(g): return "" if (g is None or abs(g) > GAIN_CAP) else ("pos" if g >= 0 else "neg")
def e(x): return html.escape(str(x))

def build_rows(parents, children, tempo, since, until):
    ch_by_parent = defaultdict(list)
    for c in children:
        cf = c.get("fields", {}) or {}
        pk = (cf.get("parent") or {}).get("key")
        if pk: ch_by_parent[pk].append(c)
    p_bugs = {}; p_dl = {}; p_has_sub = {}; p_foreign_ct = {}; p_foreign_hr = {}
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw_bugs = {ar: [] for ar in AREAS}; dl_by_area = {ar: 0.0 for ar in AREAS}
        pa = area_of(pf); saw_sub = False; rec_areas = record_domains(pf)
        # Only the ticket's OWN child sub-issues (never issue links): Bug/Sub-bug -> count + Sub-bug h;
        # non-bug sub-tasks -> Dev-lead estimate (sub-bug estimates excluded).
        for c in ch_by_parent.get(key, []):
            cf = c.get("fields", {}) or {}
            if is_bug(cf):
                bar = area_of(cf)              # bugs: attributed by their OWN component/title only (no parent inheritance)
                if bar: raw_bugs[bar].append(c)
            else:
                ar = area_of(cf) or pa         # non-bug sub-tasks still inherit the parent area for the DL estimate
                saw_sub = True
                if ar: dl_by_area[ar] += hours(cf.get("timeoriginalestimate"))
        # Only own-area sub-bugs drive an area's count & Sub-bug h. A sub-bug whose area has no
        # AI record on the ticket is NOT mixed into another area's numbers (this report measures
        # per-area AI impact, and each area is a different developer) — it is surfaced only as an
        # annotation "(front +1 7.8h)" on a record area's cell, carrying its count and total hours.
        bugs_by_area = {ar: list(raw_bugs[ar]) if ar in rec_areas else [] for ar in AREAS}
        fct = {ar: {} for ar in AREAS}; fhr = {ar: {} for ar in AREAS}
        fallback = pa if pa in rec_areas else (sorted(rec_areas)[0] if rec_areas else None)
        if fallback:
            for ar in AREAS:
                if ar in rec_areas or not raw_bugs[ar]: continue
                fct[fallback][ar] = fct[fallback].get(ar, 0) + len(raw_bugs[ar])
                fhr[fallback][ar] = round(fhr[fallback].get(ar, 0.0)
                    + sum(hours((b.get("fields") or {}).get("timespent")) for b in raw_bugs[ar]), 1)
        p_bugs[key] = bugs_by_area; p_dl[key] = dl_by_area; p_has_sub[key] = saw_sub
        p_foreign_ct[key] = fct; p_foreign_hr[key] = fhr

    rows = []
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw = recover_json(pf.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError: continue
        summary = (pf.get("summary") or "")[:60]; ttype = ticket_type(pf)
        status = status_of(pf); final = is_final(ttype, status)
        parent_logged = hours(pf.get("timespent")); parent_est = hours(pf.get("timeoriginalestimate"))
        wl = worklog_by_user(pf.get("worklog")); tw = tempo.get(str(p.get("id")), {})
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]; name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if since and at and at < since: continue
            if until and at and at >= until: continue
            a_est = area_estimate_h(pf, domain)
            dl_est = round(p_dl[key][domain], 1) if p_has_sub[key] else parent_est
            bug_nodes = p_bugs[key][domain]                     # own-area sub-bugs only
            foreign_ct = dict(p_foreign_ct[key][domain])        # {srcArea: n} cross-area, annotation only
            foreign_hr = dict(p_foreign_hr[key][domain])        # {srcArea: hours} cross-area, annotation only
            if acc in tw: logged = hours(tw.get(acc))
            elif acc in wl: logged = hours(wl.get(acc))
            else: logged = parent_logged
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key,
                         "ttype": ttype, "summary": summary, "status": status, "final": final,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "aEst": round(a_est, 1), "dlEst": round(dl_est, 1), "logged": round(logged, 1),
                         "bugLogged": bug_logged_h(bug_nodes, acc, tempo),   # own-area only
                         "bugs": len(bug_nodes), "bugsForeign": foreign_ct, "bugsForeignH": foreign_hr})
    return rows

CSV_COLS = [
    ("key", "Ticket"), ("at", "Date"), ("ttype", "Type"), ("area", "Area"),
    ("name", "User"), ("summary", "Summary"), ("status", "Status"), ("finalTxt", "Final status"),
    ("contrib", "AI Contrib %"), ("retain", "Retain %"), ("rework", "Review phase %"),
    ("utAdd", "U.tests added"), ("utMod", "U.tests modified"), ("pmTests", "P.tests"),
    ("turns", "Requests"), ("aEst", "A. Est h"), ("dlEst", "DL. Est h"),
    ("totalDev", "Total dev h"), ("logged", "Logged h"), ("bugLogged", "Sub-bug h"),
    ("gainBug", "Arch gain % (with bugs)"), ("gain", "Arch gain % (no bugs)"),
    ("gainDlBug", "DL gain % (with bugs)"), ("gainDl", "DL gain % (no bugs)"),
    ("bugs", "Sub-bugs"), ("bugsForeignTxt", "Sub-bugs (other areas)"),
    ("url", "URL"),
]

def write_csv(rows, path):
    """Write the ticket-detail rows (one per ticket x developer record) as CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:  # utf-8-sig so Excel reads accents
        w = csv.writer(fh)
        w.writerow([h for _, h in CSV_COLS])
        for r in sorted(rows, key=lambda x: (x["area"], x["name"].lower(), x["at"], x["key"])):
            r = dict(r)
            r["finalTxt"] = "T" if r.get("final") else ""
            fg = r.get("bugsForeign") or {}; fh = r.get("bugsForeignH") or {}
            r["bugsForeignTxt"] = ", ".join(f"{FOREIGN_SHORT.get(a, a)} +{c} {fh.get(a, 0)}h" for a, c in sorted(fg.items()))
            r["url"] = JIRA_BROWSE + r["key"]
            r["totalDev"] = round(r["logged"] + r["bugLogged"], 1)
            r["gain"] = gain_cell(r["aEst"], r["logged"])
            r["gainBug"] = gain_cell(r["aEst"], r["logged"] + r["bugLogged"])
            r["gainDl"] = gain_cell(r["dlEst"], r["logged"])
            r["gainDlBug"] = gain_cell(r["dlEst"], r["logged"] + r["bugLogged"])
            w.writerow(["" if r.get(k) is None else r.get(k) for k, _ in CSV_COLS])
    print(f"Wrote {path} ({len(rows)} rows)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--children"); ap.add_argument("--tempo")
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--out", required=True)
    ap.add_argument("--csv")   # optional: also write the ticket-detail rows as CSV
    ap.add_argument("--project", default="INTRD")
    a = ap.parse_args()
    parents = nodes(json.load(open(a.input, encoding="utf-8")))
    children = nodes(json.load(open(a.children, encoding="utf-8"))) if a.children else []
    tempo = json.load(open(a.tempo, encoding="utf-8")) if a.tempo else {}
    rows = build_rows(parents, children, tempo, a.since, a.until)

    if a.csv:
        write_csv(rows, a.csv)

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None
    pct = lambda v: "—" if v is None else f"{v}%"
    SUM = ("utAdd", "utMod", "pmTests", "turns", "aEst", "dlEst", "logged", "bugLogged", "bugs")
    B = []; W = B.append
    W("<h1>AI-usage report</h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; records with <code>at</code> in '
      f'[{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} record(s) across '
      f'{len({r["key"] for r in rows})} ticket(s)</p>')
    if not rows:
        W('<p class="empty">No AI-usage records in this window.</p>')
    else:
        AH = ["Rows","Avg AI contrib","Avg retain","Avg review phase","U.tests +/~","P.tests","Requests","A. Est h","DL. Est h","Total dev h","Logged h","Sub-bug h","Arch gain","DL gain","Sub-bugs"]
        HEAD = ["AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est h","DL. Est h","Total dev h","Logged h","Sub-bug h","Arch gain","DL gain","Sub-bugs"]
        DHEAD = ["Ticket","Date","Type","Area","Summary","Status","Final","AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est h","DL. Est h","Total dev h","Logged h","Sub-bug h","Arch gain","DL gain","Sub-bugs"]
        _left = ("Ticket", "Date", "Type", "Area", "Summary", "Status"); _cent = ("Final",)

        # period grouping keys off the AI record's `at` date
        def month_of(at): return (at or "")[:7] or "no-date"

        def totals_area_html(rs):
            ag = {ar: {"contrib": [], "retain": [], "rows": [], **{k: 0 for k in SUM}} for ar in AREAS}
            for r in rs:
                gg = ag[r["area"]]; gg["contrib"].append(r["contrib"]); gg["retain"].append(r["retain"])
                gg["rows"].append(r)
                for k in SUM: gg[k] += r[k]
            h = ['<div class="tw"><table><thead><tr><th>Area</th>'
                 + "".join(f'<th class="r">{e(x)}</th>' for x in AH) + "</tr></thead><tbody>"]
            for ar in AREAS:
                g = ag[ar]
                if not g["contrib"]: continue
                ba = gain_basis(g["rows"], "aEst"); bd = gain_basis(g["rows"], "dlEst")
                gp = gain_pct(ba[0], ba[1] + ba[2]); gpd = gain_pct(bd[0], bd[1] + bd[2])  # colour by with-bug (shown first)
                h.append(f'<tr><td class="name">{e(ar.capitalize())}</td><td class="r">{len(g["contrib"])}</td>'
                  f'<td class="r">{pct(avg(g["contrib"]))}</td><td class="r">{pct(avg(g["retain"]))}</td>'
                  f'<td class="r">{pct(avg([r["rework"] for r in g["rows"]]))}</td>'
                  f'<td class="r">{g["utAdd"]}/{g["utMod"]}</td><td class="r">{g["pmTests"]}</td>'
                  f'<td class="r">{g["turns"]}</td><td class="r">{round(g["aEst"],1)}</td><td class="r">{round(g["dlEst"],1)}</td>'
                  f'<td class="r">{round(g["logged"] + g["bugLogged"],1)}</td><td class="r">{round(g["logged"],1)}</td><td class="r">{round(g["bugLogged"],1)}</td>'
                  f'<td class="r {gain_cls(gp)}">{gain_two(*ba)}</td>'
                  f'<td class="r {gain_cls(gpd)}">{gain_two(*bd)}</td><td class="r">{e(bugs_label(g["bugs"], sum_foreign(g["rows"]), sum_foreign_h(g["rows"])))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        def summary_user_html(rs, pfx=""):
            uu = {}
            for r in rs:
                u = uu.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
                     "contrib": [], "retain": [], "rework": [], "rows": [], **{k: 0 for k in SUM}})
                u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"]); u["rows"].append(r)
                u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
                for k in SUM: u[k] += r[k]
            h = ['<div class="tw"><table><thead><tr><th>User</th><th>Area</th><th class="r">Tickets</th>'
                 + "".join(f'<th class="r">{e(x)}</th>' for x in HEAD) + "</tr></thead><tbody>"]
            for _acc, u in sorted(uu.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
                ba = gain_basis(u["rows"], "aEst"); bd = gain_basis(u["rows"], "dlEst")
                g = gain_pct(ba[0], ba[1] + ba[2]); gd = gain_pct(bd[0], bd[1] + bd[2])  # colour by with-bug (shown first)
                namecell = f'<a href="#{pfx}-user-{e(_acc)}">{e(u["name"])}</a>' if pfx else e(u["name"])
                h.append(f'<tr><td class="name">{namecell}</td><td>{e("/".join(sorted(u["areas"])))}</td>'
                  f'<td class="r">{len(u["tickets"])}</td>'
                  f'<td class="r{" low" if avg(u["contrib"]) < 60 else ""}">{pct(avg(u["contrib"]))}</td><td class="r">{pct(avg(u["retain"]))}</td>'
                  f'<td class="r">{pct(avg(u["rework"]))}</td><td class="r">{u["utAdd"]}/{u["utMod"]}</td>'
                  f'<td class="r">{u["pmTests"]}</td><td class="r">{u["turns"]}</td>'
                  f'<td class="r">{round(u["aEst"],1)}</td><td class="r">{round(u["dlEst"],1)}</td>'
                  f'<td class="r">{round(u["logged"] + u["bugLogged"],1)}</td><td class="r">{round(u["logged"],1)}</td>'
                  f'<td class="r">{round(u["bugLogged"],1)}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_two(*ba)}</td>'
                  f'<td class="r {gain_cls(gd)}">{gain_two(*bd)}</td><td class="r">{e(bugs_label(u["bugs"], sum_foreign(u["rows"]), sum_foreign_h(u["rows"])))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        MHEAD = ["Month","Tickets","AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est h","DL. Est h","Total dev h","Logged h","Sub-bug h","Arch gain","DL gain","Sub-bugs"]
        def user_month_html(user_rows):
            """One row per month for a single user (used under the per-user Summary groups)."""
            h = ['<div class="tw"><table><thead><tr>'
                 + "".join(f'<th class="{ "" if x == "Month" else "r" }">{e(x)}</th>' for x in MHEAD)
                 + "</tr></thead><tbody>"]
            for m in sorted({month_of(r["at"]) for r in user_rows}, reverse=True):
                rs = [r for r in user_rows if month_of(r["at"]) == m]
                contrib = [r["contrib"] for r in rs]; retain = [r["retain"] for r in rs]; rework = [r["rework"] for r in rs]
                agg = {k: 0 for k in SUM}
                for r in rs:
                    for k in SUM: agg[k] += r[k]
                ba = gain_basis(rs, "aEst"); bd = gain_basis(rs, "dlEst")
                g = gain_pct(ba[0], ba[1] + ba[2]); gd = gain_pct(bd[0], bd[1] + bd[2])  # colour by with-bug (shown first)
                h.append(f'<tr><td class="name">{e(m)}</td><td class="r">{len({r["key"] for r in rs})}</td>'
                  f'<td class="r{" low" if avg(contrib) < 60 else ""}">{pct(avg(contrib))}</td>'
                  f'<td class="r">{pct(avg(retain))}</td><td class="r">{pct(avg(rework))}</td>'
                  f'<td class="r">{agg["utAdd"]}/{agg["utMod"]}</td><td class="r">{agg["pmTests"]}</td><td class="r">{agg["turns"]}</td>'
                  f'<td class="r">{round(agg["aEst"],1)}</td><td class="r">{round(agg["dlEst"],1)}</td>'
                  f'<td class="r">{round(agg["logged"] + agg["bugLogged"],1)}</td><td class="r">{round(agg["logged"],1)}</td>'
                  f'<td class="r">{round(agg["bugLogged"],1)}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_two(*ba)}</td>'
                  f'<td class="r {gain_cls(gd)}">{gain_two(*bd)}</td><td class="r">{e(bugs_label(agg["bugs"], sum_foreign(rs), sum_foreign_h(rs)))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        def detail_table_html(rs):
            h = ['<div class="tw"><table><thead><tr>'
                 + "".join(f'<th class="{ "c" if x in _cent else ("" if x in _left else "r") }">{e(x)}</th>' for x in DHEAD)
                 + "</tr></thead><tbody>"]
            for r in sorted(rs, key=lambda x: (x["at"], x["key"])):
                g = gain_pct(r["aEst"], r["logged"] + r["bugLogged"]); gd = gain_pct(r["dlEst"], r["logged"] + r["bugLogged"])  # colour by with-bug (shown first)
                finalcell = '<span class="finalbadge">T</span>' if r["final"] else ""
                low = isinstance(r["contrib"], (int, float)) and r["contrib"] < 60  # flag weak AI contribution
                h.append(f'<tr><td class="key"><a href="{JIRA_BROWSE}{e(r["key"])}" target="_blank" rel="noopener">{e(r["key"])}</a></td><td>{e(r["at"])}</td><td>{e(r["ttype"])}</td><td>{e(r["area"])}</td>'
                  f'<td>{e(r["summary"])}</td><td>{e(r["status"])}</td><td class="c">{finalcell}</td>'
                  f'<td class="r{" low" if low else ""}">{r["contrib"]}%</td><td class="r">{r["retain"]}%</td><td class="r">{r["rework"]}%</td>'
                  f'<td class="r">{r["utAdd"]}/{r["utMod"]}</td><td class="r">{r["pmTests"]}</td>'
                  f'<td class="r">{r["turns"]}</td><td class="r">{r["aEst"]}</td><td class="r">{r["dlEst"]}</td>'
                  f'<td class="r">{round(r["logged"] + r["bugLogged"],1)}</td><td class="r">{r["logged"]}</td>'
                  f'<td class="r">{r["bugLogged"]}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_two(r["aEst"], r["logged"], r["bugLogged"])}</td>'
                  f'<td class="r {gain_cls(gd)}">{gain_two(r["dlEst"], r["logged"], r["bugLogged"])}</td><td class="r">{e(bugs_label(r["bugs"], r["bugsForeign"], r["bugsForeignH"]))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        def render_body(rs, pfx=""):
            """Full report body (KPI cards + Totals + Summary + Detail) for a subset of rows."""
            if not rs:
                return '<p class="empty">No records of this ticket type in this window.</p>'
            users_x = {}
            for r in rs:
                u = users_x.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
                     "contrib": [], "retain": [], "rework": [], **{k: 0 for k in SUM}})
                u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
                u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
                for k in SUM: u[k] += r[k]
            by_user_x = defaultdict(list)
            for r in rs: by_user_x[r["acc"]].append(r)
            latest_month = max((month_of(r["at"]) for r in rs), default=None)

            def month_details(section_rows, render_fn):
                out = []
                for m in sorted({month_of(r["at"]) for r in section_rows}, reverse=True):
                    mr = [r for r in section_rows if month_of(r["at"]) == m]
                    op = " open" if m == latest_month else ""
                    out.append(f'<details{op}><summary>{e(m)} <span class="cnt">({len(mr)} record(s))</span></summary>')
                    out.append(render_fn(mr)); out.append('</details>')
                return "".join(out)

            h = []; w = h.append
            allc = [r["contrib"] for r in rs]; allr = [r["retain"] for r in rs]
            tot_aest = sum(u["aEst"] for u in users_x.values()); tot_dlest = sum(u["dlEst"] for u in users_x.values())
            tot_log = sum(u["logged"] for u in users_x.values()); tot_bug = sum(u["bugLogged"] for u in users_x.values())
            card_a = gain_basis(rs, "aEst"); card_d = gain_basis(rs, "dlEst")  # gains skip unestimated rows
            w('<div class="cards">')
            for label, val in [("Avg contribution", pct(avg(allc))), ("Avg retention", pct(avg(allr))),
                               ("Requests", sum(u["turns"] for u in users_x.values())),
                               ("Est h (A / DL)", f"{round(tot_aest,1)} / {round(tot_dlest,1)}"),
                               ("Logged h (w/o / w bugs)", f"{round(tot_log,1)} / {round(tot_log+tot_bug,1)}"),
                               ("Arch gain (w / w/o bugs)", gain_two(*card_a)),
                               ("DL gain (w / w/o bugs)", gain_two(*card_d))]:
                w(f'<div class="card"><div class="v">{e(val)}</div><div class="l">{e(label)}</div></div>')
            w('</div>')
            # Totals by area (overall, then expandable by month)
            w("<h2>Totals by area <span class=\"sub\">(sum of detail rows)</span></h2>")
            w(totals_area_html(rs)); w('<p class="bm">By month</p>'); w(month_details(rs, totals_area_html))
            # Summary by user (overall, then expandable per user -> month)
            w("<h2>Summary by user</h2>")
            w(summary_user_html(rs, pfx)); w('<p class="bm">By user &rarr; month</p>')
            for acc, u in sorted(users_x.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
                ur = by_user_x[acc]; ac = avg([r["contrib"] for r in ur])
                w(f'<details><summary>{e(u["name"])} '
                  f'<span class="cnt">({len(u["tickets"])} ticket(s), avg contrib {pct(ac)})</span></summary>')
                w(user_month_html(ur)); w('</details>')
            # Detail per user (grouped by month)
            w("<h2>Detail per user</h2>")
            for acc, u in sorted(users_x.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
                w(f'<h3 id="{pfx}-user-{e(acc)}">{e(u["name"])}</h3>'); w(month_details(by_user_x[acc], detail_table_html))
            return "".join(h)

        # Tabs: All (default), User Stories, US (final), Bugs (final), and every other ticket type
        us_rows = [r for r in rows if r["ttype"] == "US"]
        us_final_rows = [r for r in us_rows if r["final"]]
        bug_final_rows = [r for r in rows if r["ttype"] == "Bug" and r["final"]]
        other_rows = [r for r in rows if r["ttype"] != "US"]
        W('<div class="tabs">')
        W('<input type="radio" name="aitab" id="tab-all" checked>')
        W('<input type="radio" name="aitab" id="tab-us">')
        W('<input type="radio" name="aitab" id="tab-usfinal">')
        W('<input type="radio" name="aitab" id="tab-bugfinal">')
        W('<input type="radio" name="aitab" id="tab-other">')
        W('<div class="tabbar">'
          f'<label for="tab-all">All <span class="cnt">({len(rows)})</span></label>'
          f'<label for="tab-us">User Stories (All) <span class="cnt">({len(us_rows)})</span></label>'
          f'<label for="tab-usfinal">User Stories (Final) <span class="cnt">({len(us_final_rows)})</span></label>'
          f'<label for="tab-bugfinal">Bugs (final) <span class="cnt">({len(bug_final_rows)})</span></label>'
          f'<label for="tab-other">Bugs and others <span class="cnt">({len(other_rows)})</span></label></div>')
        W(f'<section class="panel panel-all">{render_body(rows, "all")}</section>')
        W(f'<section class="panel panel-us">{render_body(us_rows, "us")}</section>')
        W(f'<section class="panel panel-usfinal">{render_body(us_final_rows, "usf")}</section>')
        W(f'<section class="panel panel-bugfinal">{render_body(bug_final_rows, "bugf")}</section>')
        W(f'<section class="panel panel-other">{render_body(other_rows, "other")}</section>')
        W('</div>')
    W('<p class="foot">AI metrics are recorded per developer per ticket by <code>/oc-be-calculate-ai-use</code> and grouped here by record domain (backend / frontend / QA). '
      '<b>AI Contrib</b> = share of the delivered work that came from AI (Claude Code); '
      '<b>Retain</b> = share of the AI\'s output that survived to the final code (higher is better); '
      '<b>Review phase</b> = of the AI-authored lines, the share written during the review-and-fix phase (main context, after the reviewer) rather than the sub-agent\'s first pass (from <code>reviewer_rework_pct</code>) &mdash; a timing split, <i>not</i> a redo/discard rate, so it is unrelated to Contrib&minus;Retain; '
      '<b>U.tests +/~</b> = unit tests added / modified; '
      '<b>P.tests</b> = Postman assertion test cases exercised; '
      '<b>Requests</b> = substantive developer&harr;AI interactions in the session. '
      'The area aggregates show the average AI Contrib / Retain / Review phase and the summed counts. '
      '<b>A. Est h</b> (Architect) per area from the estimate '
      'custom fields (days &times;8), else the ticket estimate; <b>DL. Est h</b> (Dev-lead) from the ticket estimation '
      'field &mdash; a User Story sums its child sub-task estimates per area (sub-bugs excluded), a Bug/Enabler uses its '
      'own estimate. <b>Sub-bugs</b> = count of the area\'s <b>own</b> child Bug/Sub-bug sub-issues (by their component), with <b>Sub-bug h</b> (hours logged on them). '
      'This report measures per-area AI impact (a different developer per area), so a cross-area sub-bug is <b>not</b> mixed into another area\'s numbers: '
      'a sub-bug whose component is a different area (when that area has no AI record on the ticket) is shown only as an annotation, e.g. '
      '<b>2 (front +1 7.8h)</b> &mdash; 2 own-area sub-bugs, plus 1 frontend sub-bug totalling 7.8h that is counted under frontend, not here. '
      '<b>Logged h</b> = hours booked on the ticket per user (Tempo per-user &rarr; Jira worklog &rarr; ticket total); '
      '<b>Total dev h</b> = Logged h + Sub-bug h (all development effort). <b>Arch gain</b> = (A.Est&minus;Logged)/A.Est and '
      '<b>DL gain</b> = (DL.Est&minus;Logged)/DL.Est, each shown <b>with / without</b> bug hours; a dash (&mdash;) marks a '
      'meaningless gain &mdash; a placeholder estimate (&le;0.5h), no logged time, or a magnitude beyond &plusmn;1000%. '
      'In every aggregate row (area, user, month, KPI card) the gain is computed over <b>only the tickets that carry '
      'that estimate</b> &mdash; an unestimated ticket contributes neither its estimate nor its logged hours &mdash; so '
      'the gain can be based on fewer tickets than the Est h / Logged h columns beside it. Ticket keys link to Jira. '
      'In the detail tables, <b>Status</b> is the ticket\'s Jira status and <b>Final</b> (T) marks a terminal status for its type '
      '(Bug: Done/Invalid; US: Ready for Sprint review / Need documentation / Ready for release / Released; others: Done); '
      '<b>AI Contrib</b> below 60% is shown in <span class="low">red</span>. '
      'Generated by <code>/oc-ai-report</code>.</p>')
    body = "\n".join(B)
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI-usage report — {e(a.project)} {e(a.since or '')}…{e(a.until or '')}</title>
<style>
:root {{ color-scheme: light dark; --bg:#f7f8fa; --fg:#1a1d21; --muted:#6b7280; --line:#e3e6ea;
  --head:#eef1f5; --card:#fff; --accent:#2563eb; --pos:#15803d; --neg:#b91c1c; --zebra:#fafbfc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1216; --fg:#e6e8eb; --muted:#9aa3ad;
  --line:#242a31; --head:#171b21; --card:#141821; --accent:#6ea8fe; --pos:#4ade80; --neg:#f87171; --zebra:#12161c; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ width:100%; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
h2 .sub {{ font-weight:400; font-size:.8rem; color:var(--muted); }}
h3 {{ font-size:1rem; margin:1.4rem 0 .5rem; }}
.meta {{ color:var(--muted); margin:0 0 1.25rem; }}
.meta code, .foot code {{ background:var(--head); padding:.05rem .3rem; border-radius:4px; }}
.cards {{ display:flex; flex-wrap:wrap; gap:.75rem; margin:.5rem 0 1rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.8rem 1rem; min-width:130px; flex:1; }}
.card .v {{ font-size:1.35rem; font-weight:700; }}
.card .l {{ color:var(--muted); font-size:.78rem; margin-top:.15rem; }}
.tw {{ border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.5rem .7rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; position:sticky; top:0; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
tbody tr:last-child td {{ border-bottom:0; }}
.r {{ text-align:right; }}
.c {{ text-align:center; }}
.low {{ color:var(--neg); font-weight:700; }}
.finalbadge {{ display:inline-block; font-size:.7rem; font-weight:700; color:#fff; background:#16a34a; border-radius:4px; padding:.05rem .4rem; }}
details {{ border:1px solid var(--line); border-radius:10px; margin:.4rem 0; padding:0 .6rem; background:var(--card); }}
details[open] {{ padding-bottom:.5rem; }}
summary {{ cursor:pointer; font-weight:600; padding:.5rem .2rem; }}
summary .cnt {{ color:var(--muted); font-weight:400; font-size:.85em; }}
details .tw {{ margin:.35rem 0 .4rem; }}
.bm {{ color:var(--muted); font-size:.72rem; margin:.6rem 0 .2rem; text-transform:uppercase; letter-spacing:.05em; }}
.tabs > input {{ position:absolute; opacity:0; width:0; height:0; }}
.tabbar {{ display:flex; gap:.25rem; border-bottom:2px solid var(--line); margin:1.25rem 0 0; }}
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
h4 {{ margin:.55rem 0 .3rem; font-size:.88rem; color:var(--muted); }}
.name {{ font-weight:600; }}
td.name a {{ color:var(--accent); text-decoration:none; }}
td.name a:hover {{ text-decoration:underline; }}
h3 {{ scroll-margin-top:.5rem; }}
.key {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--accent); font-weight:600; }}
.key a {{ color:inherit; text-decoration:none; }}
.key a:hover {{ text-decoration:underline; }}
.pos {{ color:var(--pos); font-weight:600; }}
.neg {{ color:var(--neg); font-weight:600; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{body}
</div></body></html>"""
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(doc)
    print(f"Wrote {a.out} ({len(doc)} bytes, {len(rows)} records)")

if __name__ == "__main__":
    main()
```

## Task 4 — Present (and optionally visualise)

- Show the Markdown report and the path to the HTML file.
- Optionally offer a richer **dashboard Artifact** (bar charts: contribution/retention per area & developer, estimate-vs-logged, bug counts) — build it only if the user asks, and see the `dataviz` skill before drawing charts.

## Notes & limitations

- **Two area sources & two estimates.** *AI metrics* group by the record `domain` (per developer — a story worked by backend and frontend keeps both). **A. Est h** (Architect) comes from the Story's **per-area estimate custom fields** — `customfield_10157` (back), `customfield_10158` (front), `customfield_10189` (QA), in **days ×8**; if none are set (a standalone Bug/Enabler) the ticket's own `timeoriginalestimate` is used. **DL. Est h** (Dev-lead) comes from the **ticket estimation field**: for a User Story, the **sum of that area's child sub-task estimates** (sub-bug estimates excluded); for a Bug/Enabler, the ticket's own estimate. *Sub-bugs* (the count) and *Sub-bug h* come from the ticket's **child Bug/Sub-bug** sub-issues (never issue links), attributed by the bug's Component/title, else the parent's area. Ticket **type** (US/Bug/Enabler) is shown per detail row. Only areas that have an AI record show up (the report is record-driven).
- **Totals = sum of the detail rows** (no independent recompute). A ticket's estimate/bugs land under the area(s) with records; if two developers in the same area worked one ticket, their rows both count (rare).
- **Date = the AI record's `at`** (the day the metric was measured/confirmed). The JQL `updated >=` window is only a pre-filter; precise period membership is decided by `at` in the aggregator.
- **Logged hours** (per user & ticket, booked on the parent): **Tempo per-user** (`TEMPO_API_TOKEN`, real author) → **Jira worklog** author → **ticket-total** `timespent`. Shown in **hours** (8h/day). **Time gain** is shown as **two numbers, `with / without` bug hours**, and in the aggregate rows is computed over **only the tickets that have the matching estimate** (a ticket with no Architect estimate is left out of the Arch gain entirely — both its estimate and its logged hours — and likewise for the Dev-lead gain), so an unestimated ticket can no longer drag a whole area or developer negative; the Est h / Logged h columns beside it still show the **full** sums: `(estimate − (logged + Bug h))/estimate` first (with bugs), then `(estimate − logged)/estimate` (without bugs). Positive = under estimate. (When logged falls back to a ticket total rather than Tempo per-user, the estimate is per-area while logged is whole-ticket, so the value can read oddly.)
- **Sub-bugs & Sub-bug h** = the ticket's **own child sub-issues** of type `Bug` or `Sub-bug` — **issue links are not counted** (a "Relates" link would pull in duplicate/related bugs not raised against this ticket's work). Each sub-bug is attributed to an area **by its own Component/title only** — unlike non-bug sub-tasks (which inherit the parent's area for the DL estimate), a sub-bug does **not** inherit the parent's area, so a sub-bug with **no area signal of its own is not counted**. Only a sub-bug **in the area's own component** drives that area's count and **Sub-bug h**. Because this report measures **per-area AI impact** (a different developer per area — one backend, one frontend, one QA on a User Story), a cross-area sub-bug is **not mixed into another area's numbers**: a sub-bug whose component is a different area (and that area has no AI record on the ticket) is surfaced **only as an annotation**, **`2 (front +1 7.8h)`** — 2 own-area sub-bugs, plus a note that 1 frontend sub-bug totalling 7.8h exists (counted under frontend, not here). The base number and **Sub-bug h** are own-area only; the parenthetical lists each cross-area source's count and total hours. **Sub-bug h** is the hours logged on the own-area bugs (Tempo per-user → the bug's `timespent`), shown as a **separate** column from the ticket's Logged h. The CSV keeps the own count in **Sub-bugs** and the cross-area note in a **Sub-bugs (other areas)** column.
- **Read-only** — the command never writes to Jira, Bitbucket, or git; outbound calls are read-only: the Jira REST enhanced-search reads (Passes A/B) and the Tempo worklog fetch (Pass C) when a token is set.
- The AI records are **latest-only per developer×domain**, so the report reflects the most recent measurement per person per ticket, not a full history.

## Examples

```bash
# Monthly report for INTRD
/oc-ai-report --since 2026-07-01 --until 2026-08-01

# A specific sprint window, another project
/oc-ai-report --since 2026-07-14 --until 2026-07-28 --project ABC
```

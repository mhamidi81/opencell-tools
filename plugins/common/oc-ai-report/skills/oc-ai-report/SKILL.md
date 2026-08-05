---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period. AI metrics grouped by developer domain (backend/frontend/QA); estimate hours from the Story's per-area Architect/QA estimate custom fields (else ticket estimate); bug counts and hours-logged-on-bugs per area; logged hours per user & ticket via the Tempo API (fallback Jira worklogs); Totals = sum of details. Reads Jira (read-only) + optional Tempo. Prints Markdown and writes a styled, date-stamped HTML file to ./docs/ai-usage-report-<date>.html.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH]"
---

## Purpose

Aggregate the machine-readable **AI-usage records** that `/oc-be-calculate-ai-use` (and the future frontend / QA equivalents) write to the **"AI metrics"** field (`customfield_10745`), across many tickets over a time window, into one report:

- A **summary table by user** (one row per developer, aggregated), then **details per user by ticket**, then **totals by area** (a plain sum of the detail rows).
- **AI metrics** (contribution / retention / tests / requests) are grouped by each record's **domain** (`backend`/`frontend`/`qa`, per developer). **Estimate hours** per area come from the Story's estimate custom fields — *Architect estimate back* (`customfield_10157`), *front* (`customfield_10158`), *QA estimate* (`customfield_10189`), in days ×8 — else the ticket's own estimate. **Bug counts** and a separate **Bug h** (hours logged on Bug/Sub-bug sub-issues) are attributed per area from those sub-issues (Component, fallback title tag). **Logged hours** are per user & ticket (booked on the parent): Tempo per-user → Jira worklog → ticket total. Plus a **time-gain %** (estimate vs. logged).

This command is **read-only** — it only queries Jira. It needs **no** Bitbucket token, **no** git, and **no** repo checkout; it can run from any directory.

## Access

Requires the **Atlassian MCP** (the official `atlassian` / claude.ai Atlassian Rovo connector), site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`. If it is not connected, tell the user to run `/mcp` and connect it, then stop.

> **Tempo (per-user logged time).** Tempo syncs its worklogs into Jira under the **Tempo app account**, so Jira alone can't attribute logged time per developer. For true per-user hours, set **`TEMPO_API_TOKEN`** (each developer makes their own in *Tempo → Settings → API keys*, worklog **read** scope) and the report calls the Tempo REST API (`api.tempo.io/4`) in Pass C. It is **optional**: without the token the report falls back to the Jira `worklog` / `timespent` fields (ticket total). The token is read from the environment, never passed on the command line.

## Arguments

Parse `$ARGUMENTS` — **all optional**. A bare `/oc-ai-report` reports the **last 30 days** for **INTRD**.

- `--since YYYY-MM-DD` — start of the period (inclusive), matched against each record's `at`. **Default: 30 days before `--until`.**
- `--until YYYY-MM-DD` — end of the period (exclusive). **Default: tomorrow** (so today's records are included).
- `--project KEY` — Jira project. **Default: `INTRD`.**
- `--out PATH` — where to write the HTML report. **Default: `./docs/ai-usage-report-<TODAY>.html`** where `<TODAY>` is the run date (`date -u +%Y-%m-%d`), e.g. `./docs/ai-usage-report-2026-08-05.html` (relative to the current directory; the `docs/` folder is created if missing).

Compute any missing date with the shell — `date -u +%Y-%m-%d` (today), `date -u -d 'tomorrow' +%Y-%m-%d`, `date -u -d '30 days ago' +%Y-%m-%d`; if `date -d` is unavailable, use Python `datetime`. Echo the resolved window back to the user (e.g. "Reporting INTRD, 2026-07-04 → 2026-08-03") so the defaults are visible.

## Task 1 — Fetch the tickets (two passes: parents, then sub-issues)

Only Jira dates are JQL-filterable (the record's `at` lives *inside* the text field), so cast a slightly wide net on `updated` and let the aggregator do the precise `at` filtering. Writing the AI record updates the ticket, so `updated >= since` never drops an in-period record.

**Why two passes.** AI metrics are grouped by the record key's **domain** (`backend`/`frontend`/`qa`, per developer). **Estimate hours** come from the Story's **per-area estimate custom fields** (below), so they are on the parent. But **sub-bug counts** and **bug-logged hours** come from the ticket's **Bug / Sub-bug** sub-issues, whose area (Component / title tag) and `timespent` are not in the parent payload — so a second fetch is needed.

**Pass A — parent tickets (carry the AI record):**
1. JQL:
   ```
   project = [PROJECT] AND cf[10745] IS NOT EMPTY AND updated >= "[SINCE]" ORDER BY updated DESC
   ```
2. `searchJiraIssuesUsingJql` with fields:
   `["summary","assignee","issuetype","resolutiondate","updated","timeoriginalestimate","timespent","worklog","issuelinks","subtasks","components","customfield_10157","customfield_10158","customfield_10189","customfield_10745","customfield_10613"]`
   - The three estimate custom fields (**days**) are the per-area estimates on a User Story: `customfield_10157` = *Architect estimate back*, `customfield_10158` = *Architect estimate front*, `customfield_10189` = *QA estimate*. The aggregator converts days → hours (×8) and, if none are set (e.g. a standalone Bug), falls back to the ticket's own `timeoriginalestimate`. Sub-issue estimates are **never summed**.
   - **Paginate** until all pages are collected. Write to scratchpad as `tickets.json` (shape `{issues:{nodes:[…]}}` or `{issues:[…]}` — both accepted; if the result is large and auto-saved to a file, point the aggregator at that file).

If no issues match, tell the user "No tickets with AI-metrics data found for [PROJECT] since [SINCE]" and stop.

**Pass B — bug sub-issues (for bug counts & bug-logged hours):**
3. From the Pass-A results, collect every **Bug / Sub-bug** key: subtasks whose `fields.subtasks[].fields.issuetype.name` is `Bug` or `Sub-bug`, plus **linked** issues of those types (`fields.issuelinks[].{inwardIssue,outwardIssue}`). Also collect their **numeric ids** for Pass C. If the set is empty, skip this pass (bug count / Bug h are then 0).
4. `searchJiraIssuesUsingJql` with JQL `key in (<those bug keys>)` (chunk into batches of ≤ ~80 keys) and fields:
   `["summary","issuetype","components","timespent","parent"]`
   - Write to scratchpad as `children.json` (same shape). Each node's `id`, `components`/title (area), and `timespent` let the aggregator count bugs per area and total the hours logged on them.

**Pass C — per-user logged time from Tempo (optional but preferred):**
5. Tempo Timesheets syncs its worklogs into the Jira `worklog` field **under the Tempo app account**, so Jira alone cannot split logged time per developer. Tempo's own REST API keeps the real `author.accountId`. If the environment variable **`TEMPO_API_TOKEN`** is set (each developer creates their own token in *Tempo → Settings → API keys*, worklog **read** scope), fetch true per-user hours; otherwise skip and the aggregator falls back to Jira worklogs / ticket total.
6. Write `fetch_tempo.py` (below) to scratchpad and run it with the **numeric issue ids** of the parents (`node.id` from Pass A) **and the bug sub-issues** (from Pass B) — so both the ticket's per-user logged hours and the per-user *Bug h* can be resolved:
   ```bash
   python "<SCRATCHPAD>/fetch_tempo.py" --ids "93179,107118,109478,<bug-ids…>" --out "<SCRATCHPAD>/tempo.json"
   ```
   It reads `TEMPO_API_TOKEN` from the environment (never pass the token on the command line), calls `GET https://api.tempo.io/4/worklogs/issue/{id}` (paginated via `metadata.next`), and writes `{"<issueId>": {"<accountId>": seconds}}`. On a missing token or a 401 it writes `{}` and the report still runs (logged falls back to Jira worklog / ticket total; Bug h to the bug's `timespent`).

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

(`--children`/`--tempo` are optional; omit if that pass was skipped.) It prints a Markdown report: **Summary by user**, **Detail per user by ticket**, then **Totals by area** (a plain sum of the detail rows). AI metrics (contribution/retention/tests/requests) are grouped by the record's **domain**; **estimate hours** per area come from the Story's estimate custom fields (else the ticket estimate); **bug counts** and **Bug h** are per area from Bug/Sub-bug sub-issues; **logged hours** are per user & ticket (booked on the parent). Display it to the user verbatim.

### `ai_report.py`

```python
#!/usr/bin/env python3
"""AI-usage report. AI metrics grouped by record domain. Estimate hours come from per-area
Architect/QA estimate custom fields on the Story (days x8), else the ticket's own estimate
(sub-issue estimates are never summed). Bug counts and bug-logged hours come from Bug/Sub-bug
sub-issues, per area. Logged hours are per user & ticket (Tempo per-user -> Jira -> ticket total).
Totals = plain sum of the detail rows."""
import argparse, json, re
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8            # Jira workday
BUG_TYPES = {"bug", "sub-bug"}

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

def linked_bug_keys(fields):
    ks = []
    for lk in fields.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            li = lk.get(side)
            if li and is_bug(li.get("fields") or {}): ks.append(li.get("key"))
    return ks

def area_estimate_h(pf, area):
    """Per-area estimate in hours. If any per-area estimate custom field is set (a Story), use
    that area's field (days x8); a field absent for that area => 0. Otherwise (no per-area fields,
    e.g. a standalone Bug) fall back to the ticket's own timeoriginalestimate. Never sums sub-issues."""
    vals = {ar: pf.get(f) for ar, f in AREA_EST_FIELD.items()}
    if any(isinstance(v, (int, float)) for v in vals.values()):
        v = vals.get(area)
        return round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    return hours(pf.get("timeoriginalestimate"))

def bug_logged_h(bug_nodes, acc, tempo):
    """Hours logged on the given bug sub-issues for this user: Tempo per-user if available,
    else the bug's own timespent (whole)."""
    total = 0.0
    for b in bug_nodes:
        bid = str(b.get("id")); bf = b.get("fields", {}) or {}
        tw = tempo.get(bid, {})
        total += hours(tw.get(acc)) if acc in tw else hours(bf.get("timespent"))
    return round(total, 1)

def gain_pct(est, logged): return round((est - logged) / est * 100) if est else None
def gain_str(g): return "-" if g is None else (f"+{g}%" if g >= 0 else f"{g}%")

def build_rows(parents, children, tempo, since, until):
    ch_by_parent = defaultdict(list); ch_by_key = {}
    for c in children:
        cf = c.get("fields", {}) or {}
        ch_by_key[c.get("key")] = c
        pk = (cf.get("parent") or {}).get("key")
        if pk: ch_by_parent[pk].append(c)

    # per-parent: Bug/Sub-bug sub-issues bucketed by area (for count + bug-logged)
    p_bugs = {}
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        by_area = {ar: [] for ar in AREAS}
        subs = list(ch_by_parent.get(key, []))
        linked = [ch_by_key[k] for k in linked_bug_keys(pf) if k in ch_by_key]
        pa = area_of(pf); seen = set()
        for c in subs + linked:
            ck = c.get("key")
            if ck in seen: continue
            seen.add(ck)
            cf = c.get("fields", {}) or {}
            if not is_bug(cf): continue
            ar = area_of(cf) or pa
            if ar: by_area[ar].append(c)
        p_bugs[key] = by_area

    rows = []
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw = recover_json(pf.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError: continue
        summary = (pf.get("summary") or "")[:44]
        parent_logged = hours(pf.get("timespent"))
        wl = worklog_by_user(pf.get("worklog")); tw = tempo.get(str(p.get("id")), {})
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]; name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if since and at and at < since: continue
            if until and at and at >= until: continue
            est = area_estimate_h(pf, domain)
            bug_nodes = p_bugs[key][domain]
            bugs = len(bug_nodes)
            bug_logged = bug_logged_h(bug_nodes, acc, tempo)
            if acc in tw: logged = hours(tw.get(acc))
            elif acc in wl: logged = hours(wl.get(acc))
            else: logged = parent_logged
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key, "summary": summary,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "est": round(est, 1), "logged": round(logged, 1), "bugLogged": bug_logged, "bugs": bugs})
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
    SUM = ("utAdd", "utMod", "pmTests", "turns", "est", "logged", "bugLogged", "bugs")

    users = {}
    for r in rows:
        u = users.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
             "contrib": [], "retain": [], "rework": [], **{k: 0 for k in SUM}})
        u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
        u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
        for k in SUM: u[k] += r[k]

    P("## Summary by user\n")
    P("| User | Area | Tickets | AI Contrib | Retain | Rework | U.tests +/~ | P.tests | Requests | Est h | Logged h | Bug h | Time gain | Bugs |")
    P("|---|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|")
    for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
        P(f"| {u['name']} | {'/'.join(sorted(u['areas']))} | {len(u['tickets'])} | {avg(u['contrib'])}% | "
          f"{avg(u['retain'])}% | {avg(u['rework'])}% | {u['utAdd']}/{u['utMod']} | {u['pmTests']} | {u['turns']} | "
          f"{round(u['est'],1)} | {round(u['logged'],1)} | {round(u['bugLogged'],1)} | {gain_str(gain_pct(u['est'], u['logged']))} | {u['bugs']} |")

    P("\n## Detail per user")
    by_user = defaultdict(list)
    for r in rows: by_user[r["acc"]].append(r)
    for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
        P(f"\n### {u['name']}\n")
        P("| Ticket | Date | Area | Summary | AI Contrib | Retain | U.tests +/~ | P.tests | Requests | Est h | Logged h | Bug h | Time gain | Bugs |")
        P("|---|---|---|---|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|")
        for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
            P(f"| {r['key']} | {r['at']} | {r['area']} | {r['summary']} | {r['contrib']}% | {r['retain']}% | "
              f"{r['utAdd']}/{r['utMod']} | {r['pmTests']} | "
              f"{r['turns']} | {r['est']} | {r['logged']} | {r['bugLogged']} | {gain_str(gain_pct(r['est'], r['logged']))} | {r['bugs']} |")

    P("\n## Totals by area (sum of detail rows)\n")
    areas = {ar: {"contrib": [], "retain": [], **{k: 0 for k in SUM}} for ar in AREAS}
    for r in rows:
        g = areas[r["area"]]; g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        for k in SUM: g[k] += r[k]
    P("| Area | Rows | AI Contrib | Retain | U.tests +/~ | P.tests | Requests | Est h | Logged h | Bug h | Time gain | Bugs |")
    P("|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|")
    for ar in AREAS:
        g = areas[ar]
        if not g["contrib"]: continue
        P(f"| {ar.capitalize()} | {len(g['contrib'])} | {avg(g['contrib'])}% | {avg(g['retain'])}% | "
          f"{g['utAdd']}/{g['utMod']} | {g['pmTests']} | {g['turns']} | {round(g['est'],1)} | "
          f"{round(g['logged'],1)} | {round(g['bugLogged'],1)} | {gain_str(gain_pct(g['est'], g['logged']))} | {g['bugs']} |")
    print("\n".join(out))

if __name__ == "__main__":
    main()
```

## Task 3 — Write the HTML report

Also render a **self-contained, styled HTML file** from the same `tickets.json`. Write the script below to your scratchpad as `ai_report_html.py` and run it, pointing `--out` at the resolved output path (default `./docs/ai-usage-report-<TODAY>.html`, `<TODAY>` = `date -u +%Y-%m-%d` — the date-stamp keeps successive reports side by side rather than overwriting):

```bash
python "<SCRATCHPAD>/ai_report_html.py" --input "<SCRATCHPAD>/tickets.json" \
  --children "<SCRATCHPAD>/children.json" --tempo "<SCRATCHPAD>/tempo.json" \
  --since [SINCE] --until [UNTIL] --project [PROJECT] --out "./docs/ai-usage-report-[TODAY].html"
```

The page is theme-aware (light/dark), leads with KPI cards, then the three sections mirroring the Markdown (summary by user → detail per user → totals by area). It embeds all CSS — no external assets — so it opens straight from disk. Tell the user the absolute path and that they can open it in a browser (Windows: `start "" "<path>"`).

### `ai_report_html.py`

```python
#!/usr/bin/env python3
"""Render the AI-usage report as a self-contained, styled HTML file. AI metrics grouped by record
domain. Estimate hours from per-area Architect/QA estimate custom fields on the Story (days x8),
else the ticket's own estimate. Bug counts & bug-logged hours from Bug/Sub-bug sub-issues, per area.
Logged hours per user & ticket (Tempo per-user -> Jira -> ticket total). Totals = sum of detail rows."""
import argparse, json, re, html
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]
COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8
BUG_TYPES = {"bug", "sub-bug"}

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

def linked_bug_keys(fields):
    ks = []
    for lk in fields.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            li = lk.get(side)
            if li and is_bug(li.get("fields") or {}): ks.append(li.get("key"))
    return ks

def area_estimate_h(pf, area):
    vals = {ar: pf.get(f) for ar, f in AREA_EST_FIELD.items()}
    if any(isinstance(v, (int, float)) for v in vals.values()):
        v = vals.get(area)
        return round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    return hours(pf.get("timeoriginalestimate"))

def bug_logged_h(bug_nodes, acc, tempo):
    total = 0.0
    for b in bug_nodes:
        bid = str(b.get("id")); bf = b.get("fields", {}) or {}
        tw = tempo.get(bid, {})
        total += hours(tw.get(acc)) if acc in tw else hours(bf.get("timespent"))
    return round(total, 1)

def gain_pct(est, logged): return round((est - logged) / est * 100) if est else None
def gain_str(g): return "—" if g is None else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_cls(g): return "" if g is None else ("pos" if g >= 0 else "neg")
def e(x): return html.escape(str(x))

def build_rows(parents, children, tempo, since, until):
    ch_by_parent = defaultdict(list); ch_by_key = {}
    for c in children:
        cf = c.get("fields", {}) or {}
        ch_by_key[c.get("key")] = c
        pk = (cf.get("parent") or {}).get("key")
        if pk: ch_by_parent[pk].append(c)
    p_bugs = {}
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        by_area = {ar: [] for ar in AREAS}
        subs = list(ch_by_parent.get(key, []))
        linked = [ch_by_key[k] for k in linked_bug_keys(pf) if k in ch_by_key]
        pa = area_of(pf); seen = set()
        for c in subs + linked:
            ck = c.get("key")
            if ck in seen: continue
            seen.add(ck)
            cf = c.get("fields", {}) or {}
            if not is_bug(cf): continue
            ar = area_of(cf) or pa
            if ar: by_area[ar].append(c)
        p_bugs[key] = by_area

    rows = []
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw = recover_json(pf.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError: continue
        summary = (pf.get("summary") or "")[:60]
        parent_logged = hours(pf.get("timespent"))
        wl = worklog_by_user(pf.get("worklog")); tw = tempo.get(str(p.get("id")), {})
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]; name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if since and at and at < since: continue
            if until and at and at >= until: continue
            est = area_estimate_h(pf, domain)
            bug_nodes = p_bugs[key][domain]
            if acc in tw: logged = hours(tw.get(acc))
            elif acc in wl: logged = hours(wl.get(acc))
            else: logged = parent_logged
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key, "summary": summary,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "est": round(est, 1), "logged": round(logged, 1),
                         "bugLogged": bug_logged_h(bug_nodes, acc, tempo), "bugs": len(bug_nodes)})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--children"); ap.add_argument("--tempo")
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--out", required=True)
    ap.add_argument("--project", default="INTRD")
    a = ap.parse_args()
    parents = nodes(json.load(open(a.input, encoding="utf-8")))
    children = nodes(json.load(open(a.children, encoding="utf-8"))) if a.children else []
    tempo = json.load(open(a.tempo, encoding="utf-8")) if a.tempo else {}
    rows = build_rows(parents, children, tempo, a.since, a.until)

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None
    pct = lambda v: "—" if v is None else f"{v}%"
    SUM = ("utAdd", "utMod", "pmTests", "turns", "est", "logged", "bugLogged", "bugs")
    users = {}
    for r in rows:
        u = users.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
             "contrib": [], "retain": [], "rework": [], **{k: 0 for k in SUM}})
        u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
        u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
        for k in SUM: u[k] += r[k]
    by_user = defaultdict(list)
    for r in rows: by_user[r["acc"]].append(r)
    areas = {ar: {"contrib": [], "retain": [], **{k: 0 for k in SUM}} for ar in AREAS}
    for r in rows:
        g = areas[r["area"]]; g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        for k in SUM: g[k] += r[k]

    HEAD = ["AI Contrib","Retain","Rework","U.tests +/~","P.tests","Requests","Est h","Logged h","Bug h","Time gain","Bugs"]
    B = []; W = B.append
    W("<h1>AI-usage report</h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; records with <code>at</code> in '
      f'[{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} record(s) across '
      f'{len({r["key"] for r in rows})} ticket(s)</p>')
    if not rows:
        W('<p class="empty">No AI-usage records in this window.</p>')
    else:
        allc = [r["contrib"] for r in rows]; allr = [r["retain"] for r in rows]
        tot_est = sum(u["est"] for u in users.values()); tot_log = sum(u["logged"] for u in users.values())
        W('<div class="cards">')
        for label, val in [("Avg contribution", pct(avg(allc))), ("Avg retention", pct(avg(allr))),
                           ("Requests", sum(u["turns"] for u in users.values())),
                           ("Est → Logged h", f"{round(tot_est,1)} → {round(tot_log,1)}"),
                           ("Time gain", gain_str(gain_pct(tot_est, tot_log)))]:
            W(f'<div class="card"><div class="v">{e(val)}</div><div class="l">{e(label)}</div></div>')
        W('</div>')
        W("<h2>Summary by user</h2>")
        W('<div class="tw"><table><thead><tr><th>User</th><th>Area</th><th class="r">Tickets</th>'
          + "".join(f'<th class="r">{e(h)}</th>' for h in HEAD) + "</tr></thead><tbody>")
        for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
            g = gain_pct(u["est"], u["logged"])
            W(f'<tr><td class="name">{e(u["name"])}</td><td>{e("/".join(sorted(u["areas"])))}</td>'
              f'<td class="r">{len(u["tickets"])}</td>'
              f'<td class="r">{pct(avg(u["contrib"]))}</td><td class="r">{pct(avg(u["retain"]))}</td>'
              f'<td class="r">{pct(avg(u["rework"]))}</td><td class="r">{u["utAdd"]}/{u["utMod"]}</td>'
              f'<td class="r">{u["pmTests"]}</td><td class="r">{u["turns"]}</td>'
              f'<td class="r">{round(u["est"],1)}</td><td class="r">{round(u["logged"],1)}</td>'
              f'<td class="r">{round(u["bugLogged"],1)}</td>'
              f'<td class="r {gain_cls(g)}">{gain_str(g)}</td><td class="r">{u["bugs"]}</td></tr>')
        W("</tbody></table></div>")
        W("<h2>Detail per user</h2>")
        DHEAD = ["Ticket","Date","Area","Summary","AI Contrib","Retain","U.tests +/~","P.tests","Requests","Est h","Logged h","Bug h","Time gain","Bugs"]
        for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
            W(f'<h3>{e(u["name"])}</h3>')
            W('<div class="tw"><table><thead><tr>'
              + "".join(f'<th class="{ "r" if h not in ("Ticket","Date","Area","Summary") else "" }">{e(h)}</th>' for h in DHEAD)
              + "</tr></thead><tbody>")
            for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
                g = gain_pct(r["est"], r["logged"])
                W(f'<tr><td class="key">{e(r["key"])}</td><td>{e(r["at"])}</td><td>{e(r["area"])}</td>'
                  f'<td>{e(r["summary"])}</td><td class="r">{r["contrib"]}%</td><td class="r">{r["retain"]}%</td>'
                  f'<td class="r">{r["utAdd"]}/{r["utMod"]}</td><td class="r">{r["pmTests"]}</td>'
                  f'<td class="r">{r["turns"]}</td><td class="r">{r["est"]}</td><td class="r">{r["logged"]}</td>'
                  f'<td class="r">{r["bugLogged"]}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_str(g)}</td><td class="r">{r["bugs"]}</td></tr>')
            W("</tbody></table></div>")
        W("<h2>Totals by area <span class=\"sub\">(sum of detail rows)</span></h2>")
        AH = ["Rows","Avg AI contrib","Avg retain","U.tests +/~","P.tests","Requests","Est h","Logged h","Bug h","Time gain","Bugs"]
        W('<div class="tw"><table><thead><tr><th>Area</th>'
          + "".join(f'<th class="r">{e(h)}</th>' for h in AH) + "</tr></thead><tbody>")
        for ar in AREAS:
            g = areas[ar]
            if not g["contrib"]: continue
            gp = gain_pct(g["est"], g["logged"])
            W(f'<tr><td class="name">{e(ar.capitalize())}</td><td class="r">{len(g["contrib"])}</td>'
              f'<td class="r">{pct(avg(g["contrib"]))}</td><td class="r">{pct(avg(g["retain"]))}</td>'
              f'<td class="r">{g["utAdd"]}/{g["utMod"]}</td><td class="r">{g["pmTests"]}</td>'
              f'<td class="r">{g["turns"]}</td><td class="r">{round(g["est"],1)}</td>'
              f'<td class="r">{round(g["logged"],1)}</td><td class="r">{round(g["bugLogged"],1)}</td>'
              f'<td class="r {gain_cls(gp)}">{gain_str(gp)}</td><td class="r">{g["bugs"]}</td></tr>')
        W("</tbody></table></div>")
    W('<p class="foot">AI metrics grouped by record domain. Estimate hours per area from the Architect/QA '
      'estimate custom fields (days &times;8), else the ticket estimate. Bug count &amp; <b>Bug h</b> (logged on '
      'Sub-bugs) per area. Logged hours per user &amp; ticket (Tempo per-user &rarr; Jira worklog &rarr; ticket total). '
      'Time gain = (est &minus; logged) / est. Generated by <code>/oc-ai-report</code>.</p>')
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
.wrap {{ max-width:1220px; margin:0 auto; }}
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
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.5rem .7rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; position:sticky; top:0; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
tbody tr:last-child td {{ border-bottom:0; }}
.r {{ text-align:right; }}
.name {{ font-weight:600; }}
.key {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--accent); font-weight:600; }}
.pos {{ color:var(--pos); font-weight:600; }}
.neg {{ color:var(--neg); font-weight:600; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{body}
</div></body></html>"""
    import os
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

- **Two area sources.** *AI metrics* group by the record `domain` (per developer — a story worked by backend and frontend keeps both). *Estimate hours* come from the Story's **per-area estimate custom fields** — `customfield_10157` (Architect estimate back), `customfield_10158` (front), `customfield_10189` (QA), in **days ×8**; if none are set (e.g. a standalone Bug) the ticket's own `timeoriginalestimate` is used for the area that worked it. Sub-issue estimates are **never summed**. *Bug counts* and *Bug h* are attributed to an area by each Bug/Sub-bug's **Component** (`Backend`/`Frontend`/`Testing` → area), fallback **title tag** (`[back]`/`[front]`/`[test]`), else the parent's area. Only areas that have an AI record show up (the report is record-driven).
- **Totals = sum of the detail rows** (no independent recompute). A ticket's estimate/bugs land under the area(s) with records; if two developers in the same area worked one ticket, their rows both count (rare).
- **Date = the AI record's `at`** (the day the metric was measured/confirmed). The JQL `updated >=` window is only a pre-filter; precise period membership is decided by `at` in the aggregator.
- **Logged hours** (per user & ticket, booked on the parent): **Tempo per-user** (`TEMPO_API_TOKEN`, real author) → **Jira worklog** author → **ticket-total** `timespent`. Shown in **hours** (8h/day). **Time gain** = `(estimate − logged) / estimate`; positive = under estimate. Note the scope mismatch when it falls back: estimate is per-area but a ticket-total logged is whole-ticket, so time gain can read oddly until Tempo per-user data is available.
- **Bugs & Bug h** = sub-issues / linked issues of type `Bug` or `Sub-bug`, attributed to an area by their own Component/title. **Bug h** is the hours logged on those bugs (Tempo per-user → the bug's `timespent`), shown as a **separate** column from the ticket's Logged h. Adjust the matcher if your team relates defects differently.
- **Read-only to Jira** — the command never writes to Jira, Bitbucket, or git; the only outbound call is the read-only Tempo worklog fetch (Pass C) when a token is set.
- The AI records are **latest-only per developer×domain**, so the report reflects the most recent measurement per person per ticket, not a full history.

## Examples

```bash
# Monthly report for INTRD
/oc-ai-report --since 2026-07-01 --until 2026-08-01

# A specific sprint window, another project
/oc-ai-report --since 2026-07-14 --until 2026-07-28 --project ABC
```

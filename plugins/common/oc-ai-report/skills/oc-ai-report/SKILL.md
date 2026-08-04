---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period, split by area (backend / frontend / QA) and grouped by date → user → ticket, augmented per ticket with the original estimate, Tempo-logged time, and the number of linked bugs. Reads the "AI metrics" JSON field from Jira; read-only. Prints Markdown and writes a styled HTML file to ./docs/ai-usage-report.html.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH]"
---

## Purpose

Aggregate the machine-readable **AI-usage records** that `/oc-be-calculate-ai-use` (and the future frontend / QA equivalents) write to the **"AI metrics"** field (`customfield_10745`), across many tickets over a time window, into one report:

- A **summary table by user** (one row per developer, aggregated), then **details per user by ticket**, then **totals by the three areas** (`backend`, `frontend`, `qa`, from each record's `domain`).
- Each row also shows **original estimate**, **time logged in Tempo**, a **time-gain %** (estimate vs. logged), and the **number of bugs** raised against the ticket.

This command is **read-only** — it only queries Jira. It needs **no** Bitbucket token, **no** git, and **no** repo checkout; it can run from any directory.

## Access

Requires the **Atlassian MCP** (the official `atlassian` / claude.ai Atlassian Rovo connector), site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`. If it is not connected, tell the user to run `/mcp` and connect it, then stop.

> **Tempo note.** Tempo Timesheets writes to the standard **Jira worklogs**, so this report reads logged time from the issue `worklog` / `timespent` fields via the Atlassian MCP — no separate Tempo token is needed in the normal case. If your Tempo instance is configured *not* to sync to Jira worklogs, per-user logged time will be missing; you'd then need the Tempo REST API (`api.tempo.io`, a Tempo token) — out of scope here, noted as a limitation.

## Arguments

Parse `$ARGUMENTS` — **all optional**. A bare `/oc-ai-report` reports the **last 30 days** for **INTRD**.

- `--since YYYY-MM-DD` — start of the period (inclusive), matched against each record's `at`. **Default: 30 days before `--until`.**
- `--until YYYY-MM-DD` — end of the period (exclusive). **Default: tomorrow** (so today's records are included).
- `--project KEY` — Jira project. **Default: `INTRD`.**
- `--out PATH` — where to write the HTML report. **Default: `./docs/ai-usage-report.html`** (relative to the current directory; the `docs/` folder is created if missing).

Compute any missing date with the shell — `date -u +%Y-%m-%d` (today), `date -u -d 'tomorrow' +%Y-%m-%d`, `date -u -d '30 days ago' +%Y-%m-%d`; if `date -d` is unavailable, use Python `datetime`. Echo the resolved window back to the user (e.g. "Reporting INTRD, 2026-07-04 → 2026-08-03") so the defaults are visible.

## Task 1 — Build the JQL and fetch the tickets

Only Jira dates are JQL-filterable (the record's `at` lives *inside* the text field), so cast a slightly wide net on `updated` and let the aggregator do the precise `at` filtering. Writing the AI record updates the ticket, so `updated >= since` never drops an in-period record.

1. JQL:
   ```
   project = [PROJECT] AND cf[10745] IS NOT EMPTY AND updated >= "[SINCE]" ORDER BY updated DESC
   ```
2. Run `searchJiraIssuesUsingJql` with that JQL and **request these fields** (so one search returns everything — no per-ticket calls):
   `["summary","assignee","issuetype","resolutiondate","updated","timeoriginalestimate","timespent","worklog","issuelinks","customfield_10745","customfield_10613"]`
   - **Paginate** until all pages are collected.
3. Collect all issues into a single JSON object `{ "issues": [ { "key": …, "fields": { … } }, … ] }` and write it to your session scratchpad as `tickets.json`. (If the search result is large and gets saved to a file, point the aggregator at that file instead — same shape.)

If no issues match, tell the user "No tickets with AI-metrics data found for [PROJECT] since [SINCE]" and stop.

## Task 2 — Run the aggregator

Write the script below to your scratchpad as `ai_report.py` and run it (Python 3 is available as `python`):

```bash
python "<SCRATCHPAD>/ai_report.py" --input "<SCRATCHPAD>/tickets.json" --since [SINCE] --until [UNTIL]
```

It prints a Markdown report: per area (`backend`/`frontend`/`qa`) → per date → per user → a ticket table, then a **Totals by area** table. Display it to the user verbatim.

### `ai_report.py`

```python
#!/usr/bin/env python3
"""Aggregate AI-usage across Jira tickets into a report: area -> date -> user -> ticket,
augmented per ticket with original estimate, Tempo-logged time, and linked-bug count."""
import argparse, json
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]

def recover_json(val):
    """The 'AI metrics' field may be a plain string OR an ADF doc; return the JSON text."""
    if val is None: return None
    if isinstance(val, str): return val
    if isinstance(val, dict):                 # ADF — concatenate every text node (code block / paragraph)
        out = []
        def walk(n):
            if isinstance(n, dict):
                if n.get("type") == "text" and isinstance(n.get("text"), str): out.append(n["text"])
                for c in n.get("content") or []: walk(c)
            elif isinstance(n, list):
                for c in n: walk(c)
        walk(val)
        return "".join(out)
    return None

def hours(seconds): return round((seconds or 0) / 3600, 1)

def bug_count(issuelinks):
    n = 0
    for lk in issuelinks or []:
        for side in ("inwardIssue", "outwardIssue"):
            li = lk.get(side)
            if li and (((li.get("fields") or {}).get("issuetype") or {}).get("name", "").lower() == "bug"):
                n += 1
    return n

def worklog_by_user(worklog):
    per = defaultdict(int)
    for w in (worklog or {}).get("worklogs") or []:
        per[(w.get("author") or {}).get("accountId")] += w.get("timeSpentSeconds", 0) or 0
    return per

def num(x): return x if isinstance(x, (int, float)) else 0

def gain_pct(est, logged):
    """Time gain = (estimate - logged) / estimate. Positive = under estimate (time saved)."""
    return round((est - logged) / est * 100) if est else None

def gain_str(g):
    return "–" if g is None else (f"+{g}%" if g >= 0 else f"{g}%")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--since"); ap.add_argument("--until")
    a = ap.parse_args()
    data = json.load(open(a.input, encoding="utf-8"))
    # accept {issues:[...]}, a bare list, or the MCP {issues:{nodes:[...]}} shape
    issues = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(issues, dict): issues = issues.get("nodes", [])

    rows = []      # one flat row per (ticket, developer) AI record
    warnings = []
    for iss in issues:
        key = iss.get("key"); f = iss.get("fields", {}) or {}
        raw = recover_json(f.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append(f"{key}: AI-metrics JSON unparseable — skipped"); continue
        est_h = hours(f.get("timeoriginalestimate"))
        logged_total_h = hours(f.get("timespent"))
        bugs = bug_count(f.get("issuelinks"))
        wl = worklog_by_user(f.get("worklog"))
        summary = (f.get("summary") or "")[:44]
        if (f.get("worklog") or {}).get("total", 0) > len((f.get("worklog") or {}).get("worklogs") or []):
            warnings.append(f"{key}: worklog list truncated by Jira — per-user logged time may be partial")
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]
            name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if a.since and at and at < a.since: continue
            if a.until and at and at >= a.until: continue
            logged = hours(wl.get(acc)) if acc in wl else logged_total_h   # per-user if Jira has it, else ticket total
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key, "summary": summary,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("turns")), "est": est_h, "logged": logged, "bugs": bugs})

    out = []; P = out.append
    P(f"# AI-usage report — records with `at` in [{a.since or '…'} … {a.until or '…'})\n")
    if not rows:
        P("_No AI-usage records in this window._"); print("\n".join(out)); return
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else "–"

    # ---- 1) Summary by user ----
    users = {}
    for r in rows:
        u = users.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
             "contrib": [], "retain": [], "rework": [], "utAdd": 0, "utMod": 0, "pmTests": 0,
             "turns": 0, "est": 0.0, "logged": 0.0, "bugs": 0, "seen": set()})
        u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
        u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
        u["utAdd"] += r["utAdd"]; u["utMod"] += r["utMod"]; u["pmTests"] += r["pmTests"]; u["turns"] += r["turns"]
        if r["key"] not in u["seen"]:   # est/logged/bugs are ticket-wide -> once per (user, ticket)
            u["seen"].add(r["key"]); u["est"] += r["est"]; u["logged"] += r["logged"]; u["bugs"] += r["bugs"]

    P("## Summary by user\n")
    P("| User | Area | Tickets | Contrib | Retain | Rework | U.tests +/~ | P.tests | Prompts | Est h | Logged h | Time gain | Bugs |")
    P("|---|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|")
    for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
        P(f"| {u['name']} | {'/'.join(sorted(u['areas']))} | {len(u['tickets'])} | {avg(u['contrib'])}% | "
          f"{avg(u['retain'])}% | {avg(u['rework'])}% | {u['utAdd']}/{u['utMod']} | {u['pmTests']} | {u['turns']} | "
          f"{round(u['est'],1)} | {round(u['logged'],1)} | {gain_str(gain_pct(u['est'], u['logged']))} | {u['bugs']} |")

    # ---- 2) Detail per user, by ticket ----
    P("\n## Detail per user")
    by_user = defaultdict(list)
    for r in rows: by_user[r["acc"]].append(r)
    for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
        P(f"\n### {u['name']} ({'/'.join(sorted(u['areas']))})\n")
        P("| Ticket | Date | Summary | Contrib | Retain | Rework | U.tests +/~ | P.tests | Prompts | Est h | Logged h | Time gain | Bugs |")
        P("|---|---|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|")
        for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
            P(f"| {r['key']} | {r['at']} | {r['summary']} | {r['contrib']}% | {r['retain']}% | {r['rework']}% | "
              f"{r['utAdd']}/{r['utMod']} | {r['pmTests']} | {r['turns']} | {r['est']} | {r['logged']} | "
              f"{gain_str(gain_pct(r['est'], r['logged']))} | {r['bugs']} |")

    # ---- 3) Totals by area ----
    areas = {ar: {"tickets": set(), "contrib": [], "retain": [], "utAdd": 0, "utMod": 0, "pmTests": 0,
                  "turns": 0, "est": 0.0, "logged": 0.0, "bugs": 0, "seen": set()} for ar in AREAS}
    for r in rows:
        g = areas[r["area"]]
        g["tickets"].add(r["key"]); g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        g["utAdd"] += r["utAdd"]; g["utMod"] += r["utMod"]; g["pmTests"] += r["pmTests"]; g["turns"] += r["turns"]
        if r["key"] not in g["seen"]:
            g["seen"].add(r["key"]); g["est"] += r["est"]; g["logged"] += r["logged"]; g["bugs"] += r["bugs"]
    P("\n## Totals by area\n")
    P("| Area | Tickets | Avg contrib | Avg retain | U.tests +/~ | P.tests | Prompts | Est h | Logged h | Time gain | Bugs |")
    P("|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|")
    for ar in AREAS:
        g = areas[ar]
        if not g["tickets"]: continue
        P(f"| {ar.capitalize()} | {len(g['tickets'])} | {avg(g['contrib'])}% | {avg(g['retain'])}% | "
          f"{g['utAdd']}/{g['utMod']} | {g['pmTests']} | {g['turns']} | {round(g['est'],1)} | "
          f"{round(g['logged'],1)} | {gain_str(gain_pct(g['est'], g['logged']))} | {g['bugs']} |")
    if warnings:
        P("\n## Notes")
        for w in warnings[:20]: P(f"- {w}")
    print("\n".join(out))

if __name__ == "__main__":
    main()
```

## Task 3 — Write the HTML report

Also render a **self-contained, styled HTML file** from the same `tickets.json`. Write the script below to your scratchpad as `ai_report_html.py` and run it, pointing `--out` at the resolved output path (default `./docs/ai-usage-report.html`):

```bash
python "<SCRATCHPAD>/ai_report_html.py" --input "<SCRATCHPAD>/tickets.json" \
  --since [SINCE] --until [UNTIL] --project [PROJECT] --out "./docs/ai-usage-report.html"
```

The page is theme-aware (light/dark), leads with KPI cards, then the three sections mirroring the Markdown (summary by user → detail per user → totals by area). It embeds all CSS — no external assets — so it opens straight from disk. Tell the user the absolute path and that they can open it in a browser (Windows: `start "" "<path>"`).

### `ai_report_html.py`

```python
#!/usr/bin/env python3
"""Render the AI-usage report as a self-contained, styled HTML file."""
import argparse, json, html
from collections import defaultdict

AREAS = ["backend", "frontend", "qa"]

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
        walk(val)
        return "".join(out)
    return None

def hours(s): return round((s or 0) / 3600, 1)
def num(x): return x if isinstance(x, (int, float)) else 0

def bug_count(links):
    n = 0
    for lk in links or []:
        for side in ("inwardIssue", "outwardIssue"):
            li = lk.get(side)
            if li and (((li.get("fields") or {}).get("issuetype") or {}).get("name", "").lower() == "bug"): n += 1
    return n

def worklog_by_user(wl):
    per = defaultdict(int)
    for w in (wl or {}).get("worklogs") or []:
        per[(w.get("author") or {}).get("accountId")] += w.get("timeSpentSeconds", 0) or 0
    return per

def gain_pct(est, logged): return round((est - logged) / est * 100) if est else None
def gain_str(g): return "—" if g is None else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_cls(g): return "" if g is None else ("pos" if g >= 0 else "neg")

def e(x): return html.escape(str(x))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--out", required=True)
    ap.add_argument("--project", default="INTRD")
    a = ap.parse_args()
    data = json.load(open(a.input, encoding="utf-8"))
    issues = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(issues, dict): issues = issues.get("nodes", [])

    rows, warnings = [], []
    for iss in issues:
        key = iss.get("key"); f = iss.get("fields", {}) or {}
        raw = recover_json(f.get("customfield_10745"))
        if not raw: continue
        try: doc = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append(f"{key}: AI-metrics JSON unparseable — skipped"); continue
        est_h = hours(f.get("timeoriginalestimate")); logged_total_h = hours(f.get("timespent"))
        bugs = bug_count(f.get("issuelinks")); wl = worklog_by_user(f.get("worklog"))
        summary = (f.get("summary") or "")[:60]
        if (f.get("worklog") or {}).get("total", 0) > len((f.get("worklog") or {}).get("worklogs") or []):
            warnings.append(f"{key}: worklog list truncated by Jira — per-user logged time may be partial")
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]
            name = parts[2] if len(parts) > 2 else acc
            if domain not in AREAS: continue
            at = rec.get("at", "")
            if a.since and at and at < a.since: continue
            if a.until and at and at >= a.until: continue
            logged = hours(wl.get(acc)) if acc in wl else logged_total_h
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key, "summary": summary,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("turns")), "est": est_h, "logged": logged, "bugs": bugs})

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None
    pct = lambda v: "—" if v is None else f"{v}%"

    users = {}
    for r in rows:
        u = users.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
             "contrib": [], "retain": [], "rework": [], "utAdd": 0, "utMod": 0, "pmTests": 0,
             "turns": 0, "est": 0.0, "logged": 0.0, "bugs": 0, "seen": set()})
        u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
        u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
        u["utAdd"] += r["utAdd"]; u["utMod"] += r["utMod"]; u["pmTests"] += r["pmTests"]; u["turns"] += r["turns"]
        if r["key"] not in u["seen"]:
            u["seen"].add(r["key"]); u["est"] += r["est"]; u["logged"] += r["logged"]; u["bugs"] += r["bugs"]
    by_user = defaultdict(list)
    for r in rows: by_user[r["acc"]].append(r)

    areas = {ar: {"tickets": set(), "contrib": [], "retain": [], "utAdd": 0, "utMod": 0, "pmTests": 0,
                  "turns": 0, "est": 0.0, "logged": 0.0, "bugs": 0, "seen": set()} for ar in AREAS}
    for r in rows:
        g = areas[r["area"]]
        g["tickets"].add(r["key"]); g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        g["utAdd"] += r["utAdd"]; g["utMod"] += r["utMod"]; g["pmTests"] += r["pmTests"]; g["turns"] += r["turns"]
        if r["key"] not in g["seen"]:
            g["seen"].add(r["key"]); g["est"] += r["est"]; g["logged"] += r["logged"]; g["bugs"] += r["bugs"]

    HEAD = ["Contrib","Retain","Rework","U.tests +/~","P.tests","Prompts","Est h","Logged h","Time gain","Bugs"]
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
                           ("Prompts", sum(u["turns"] for u in users.values())),
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
              f'<td class="r {gain_cls(g)}">{gain_str(g)}</td><td class="r">{u["bugs"]}</td></tr>')
        W("</tbody></table></div>")

        W("<h2>Detail per user</h2>")
        for acc, u in sorted(users.items(), key=lambda kv: kv[1]["name"].lower()):
            W(f'<h3>{e(u["name"])} <span class="tag">{e("/".join(sorted(u["areas"])))}</span></h3>')
            W('<div class="tw"><table><thead><tr><th>Ticket</th><th>Date</th><th>Summary</th>'
              + "".join(f'<th class="r">{e(h)}</th>' for h in HEAD) + "</tr></thead><tbody>")
            for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
                g = gain_pct(r["est"], r["logged"])
                W(f'<tr><td class="key">{e(r["key"])}</td><td>{e(r["at"])}</td><td>{e(r["summary"])}</td>'
                  f'<td class="r">{r["contrib"]}%</td><td class="r">{r["retain"]}%</td>'
                  f'<td class="r">{r["rework"]}%</td><td class="r">{r["utAdd"]}/{r["utMod"]}</td>'
                  f'<td class="r">{r["pmTests"]}</td><td class="r">{r["turns"]}</td>'
                  f'<td class="r">{r["est"]}</td><td class="r">{r["logged"]}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_str(g)}</td><td class="r">{r["bugs"]}</td></tr>')
            W("</tbody></table></div>")

        W("<h2>Totals by area</h2>")
        AH = ["Avg contrib","Avg retain","U.tests +/~","P.tests","Prompts","Est h","Logged h","Time gain","Bugs"]
        W('<div class="tw"><table><thead><tr><th>Area</th><th class="r">Tickets</th>'
          + "".join(f'<th class="r">{e(h)}</th>' for h in AH) + "</tr></thead><tbody>")
        for ar in AREAS:
            g = areas[ar]
            if not g["tickets"]: continue
            gp = gain_pct(g["est"], g["logged"])
            W(f'<tr><td class="name">{e(ar.capitalize())}</td><td class="r">{len(g["tickets"])}</td>'
              f'<td class="r">{pct(avg(g["contrib"]))}</td><td class="r">{pct(avg(g["retain"]))}</td>'
              f'<td class="r">{g["utAdd"]}/{g["utMod"]}</td><td class="r">{g["pmTests"]}</td>'
              f'<td class="r">{g["turns"]}</td><td class="r">{round(g["est"],1)}</td>'
              f'<td class="r">{round(g["logged"],1)}</td><td class="r {gain_cls(gp)}">{gain_str(gp)}</td>'
              f'<td class="r">{g["bugs"]}</td></tr>')
        W("</tbody></table></div>")

    if warnings:
        W("<h2>Notes</h2><ul class='notes'>")
        for w in warnings[:20]: W(f"<li>{e(w)}</li>")
        W("</ul>")
    W('<p class="foot">Time gain = (estimate − logged) / estimate; positive = under estimate. '
      'Logged time falls back to ticket-total <code>timespent</code> when Tempo worklogs are authored by the app account. '
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
.wrap {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
h3 {{ font-size:1rem; margin:1.4rem 0 .5rem; }}
.meta {{ color:var(--muted); margin:0 0 1.25rem; }}
.meta code, .foot code {{ background:var(--head); padding:.05rem .3rem; border-radius:4px; }}
.tag {{ font-size:.72rem; font-weight:600; color:var(--accent); border:1px solid var(--accent);
  border-radius:999px; padding:.05rem .5rem; vertical-align:middle; }}
.cards {{ display:flex; flex-wrap:wrap; gap:.75rem; margin:.5rem 0 1rem; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.8rem 1rem;
  min-width:130px; flex:1; }}
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
.notes {{ color:var(--muted); }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{body}
</div></body></html>"""
    import os
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"Wrote {a.out} ({len(doc)} bytes, {len(rows)} records)")

if __name__ == "__main__":
    main()
```

## Task 4 — Present (and optionally visualise)

- Show the Markdown report and the path to the HTML file.
- Optionally offer a richer **dashboard Artifact** (bar charts: contribution/retention per area & developer, estimate-vs-logged, bug counts) — build it only if the user asks, and see the `dataviz` skill before drawing charts.

## Notes & limitations

- **Areas come from the record `domain`** (`backend`/`frontend`/`qa`). A ticket worked by more than one area appears under each — that is intended (each area's contribution is separate). In **Totals**, a ticket's *estimate* and *bug count* are counted **once per area** (they are ticket-wide), while *logged time* is attributed **per user** from worklog authors where available.
- **Date = the AI record's `at`** (the day the metric was measured/confirmed). The JQL `updated >=` window is only a pre-filter; precise period membership is decided by `at` in the aggregator.
- **Original estimate** = Jira `timeoriginalestimate`; **logged time** = Jira/Tempo worklogs, shown in **hours** (Jira's own d/h view uses 8h/day). **Time gain** = `(estimate − logged) / estimate` — positive means the ticket took **less** than estimated (time saved); `–` when there is no estimate.
- **Tempo caveat (important):** Tempo Timesheets writes its worklogs with **author = the Tempo app account**, *not* the developer. So per-user attribution from Jira worklog authors usually fails, and the report falls back to the **ticket-total** `timespent` for "Logged h" (accurate per ticket, but not split per developer). For true per-user logged time, use the **Tempo REST API** (`api.tempo.io`, a Tempo token). If the inline `worklog` list is truncated, per-user time may also be partial — flagged in Notes.
- **Bugs** = linked issues whose type is `Bug` (either link direction). This counts *linked* bugs; if your team relates bugs by a specific link type (e.g. "is caused by") or via subtasks, adjust `bug_count()` accordingly.
- **Read-only** — this command never writes to Jira, Bitbucket, or git.
- The AI records are **latest-only per developer×domain**, so the report reflects the most recent measurement per person per ticket, not a full history.

## Examples

```bash
# Monthly report for INTRD
/oc-ai-report --since 2026-07-01 --until 2026-08-01

# A specific sprint window, another project
/oc-ai-report --since 2026-07-14 --until 2026-07-28 --project ABC
```

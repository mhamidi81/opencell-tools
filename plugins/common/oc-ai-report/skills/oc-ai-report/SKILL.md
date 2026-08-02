---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period, split by area (backend / frontend / QA) and grouped by date → user → ticket, augmented per ticket with the original estimate, Tempo-logged time, and the number of linked bugs. Reads the "AI metrics" JSON field from Jira; read-only.
argument-hint: "--since YYYY-MM-DD --until YYYY-MM-DD [--project INTRD]"
---

## Purpose

Aggregate the machine-readable **AI-usage records** that `/oc-be-calculate-ai-use` (and the future frontend / QA equivalents) write to the **"AI metrics"** field (`customfield_10745`), across many tickets over a time window, into one report:

- **Three areas** — `backend`, `frontend`, `qa` (from each record's `domain`).
- **Grouped by date → user → ticket** within each area.
- Each ticket row also shows **original estimate**, **time logged in Tempo**, and the **number of bugs** raised against the ticket.

This command is **read-only** — it only queries Jira. It needs **no** Bitbucket token, **no** git, and **no** repo checkout; it can run from any directory.

## Access

Requires the **Atlassian MCP** (the official `atlassian` / claude.ai Atlassian Rovo connector), site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`. If it is not connected, tell the user to run `/mcp` and connect it, then stop.

> **Tempo note.** Tempo Timesheets writes to the standard **Jira worklogs**, so this report reads logged time from the issue `worklog` / `timespent` fields via the Atlassian MCP — no separate Tempo token is needed in the normal case. If your Tempo instance is configured *not* to sync to Jira worklogs, per-user logged time will be missing; you'd then need the Tempo REST API (`api.tempo.io`, a Tempo token) — out of scope here, noted as a limitation.

## Arguments

Parse `$ARGUMENTS`:

- `--since YYYY-MM-DD` (required) — start of the period (inclusive), matched against each record's `at`.
- `--until YYYY-MM-DD` (required) — end of the period (exclusive).
- `--project KEY` — Jira project (default `INTRD`).

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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--since"); ap.add_argument("--until")
    a = ap.parse_args()
    data = json.load(open(a.input, encoding="utf-8"))
    # accept {issues:[...]}, a bare list, or the MCP {issues:{nodes:[...]}} shape
    issues = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(issues, dict): issues = issues.get("nodes", [])

    tree = {ar: defaultdict(lambda: defaultdict(list)) for ar in AREAS}   # area -> at -> name -> rows
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
        if len(f.get("worklog") or {}) and (f.get("worklog") or {}).get("total", 0) > len((f.get("worklog") or {}).get("worklogs") or []):
            warnings.append(f"{key}: worklog list truncated by Jira — per-user logged time may be partial")
        for rkey, rec in (doc.get("records") or {}).items():
            parts = rkey.split("/", 2)
            if len(parts) < 2: continue
            domain, acc = parts[0], parts[1]
            name = parts[2] if len(parts) > 2 else acc
            if domain not in tree: continue
            at = rec.get("at", "")
            if a.since and at and at < a.since: continue
            if a.until and at and at >= a.until: continue
            tree[domain][at][name].append({
                "key": key, "summary": summary, "rec": rec, "est_h": est_h,
                "logged_user_h": (hours(wl.get(acc)) if acc in wl else None),
                "logged_total_h": logged_total_h, "bugs": bugs,
            })

    out = []
    P = out.append
    P(f"# AI-usage report — records with `at` in [{a.since or '…'} … {a.until or '…'})\n")
    grand = {ar: {"tickets": set(), "contrib": [], "retain": [], "utAdd": 0, "utMod": 0,
                  "pmTests": 0, "turns": 0, "est": 0.0, "logged": 0.0, "bugs": 0,
                  "counted": set()} for ar in AREAS}

    for area in AREAS:
        if not tree[area]: continue
        P(f"## {area.capitalize()}\n")
        for at in sorted(tree[area]):
            P(f"### {at or '(no date)'}\n")
            for name in sorted(tree[area][at]):
                P(f"**{name}**\n")
                P("| Ticket | Summary | Contrib | Retain | Rework | Tests +/~ | Cases | Prompts | Est h | Logged h | Bugs |")
                P("|---|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|")
                for r in tree[area][at][name]:
                    rc = r["rec"]
                    logged = r["logged_user_h"] if r["logged_user_h"] is not None else r["logged_total_h"]
                    P(f"| {r['key']} | {r['summary']} | {rc.get('contrib','–')}% | {rc.get('retain','–')}% | "
                      f"{rc.get('rework','–')}% | {rc.get('utAdd',0)}/{rc.get('utMod',0)} | {rc.get('pmTests',0)} | "
                      f"{rc.get('turns','–')} | {r['est_h']} | {logged} | {r['bugs']} |")
                    g = grand[area]
                    g["tickets"].add(r["key"])
                    g["contrib"].append(num(rc.get("contrib"))); g["retain"].append(num(rc.get("retain")))
                    g["utAdd"] += num(rc.get("utAdd")); g["utMod"] += num(rc.get("utMod"))
                    g["pmTests"] += num(rc.get("pmTests")); g["turns"] += num(rc.get("turns"))
                    if r["logged_user_h"] is not None: g["logged"] += r["logged_user_h"]
                    # est/bugs are ticket-wide -> count once per ticket per area
                    if r["key"] not in g["counted"]:
                        g["counted"].add(r["key"]); g["est"] += r["est_h"]; g["bugs"] += r["bugs"]
                        if r["logged_user_h"] is None: g["logged"] += r["logged_total_h"]
                P("")

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else "–"
    P("## Totals by area\n")
    P("| Area | Tickets | Avg contrib | Avg retain | Tests +/~ | Cases | Prompts | Est h | Logged h | Bugs |")
    P("|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|")
    for area in AREAS:
        g = grand[area]
        if not g["tickets"]: continue
        P(f"| {area.capitalize()} | {len(g['tickets'])} | {avg(g['contrib'])}% | {avg(g['retain'])}% | "
          f"{g['utAdd']}/{g['utMod']} | {g['pmTests']} | {g['turns']} | {round(g['est'],1)} | "
          f"{round(g['logged'],1)} | {g['bugs']} |")
    if warnings:
        P("\n## Notes")
        for w in warnings[:20]: P(f"- {w}")
    print("\n".join(out))

if __name__ == "__main__":
    main()
```

## Task 3 — Present (and optionally visualise)

- Show the Markdown report.
- Offer a **dashboard Artifact** (bar charts: contribution/retention per area & developer, estimate-vs-logged, bug counts). Build it only if the user asks — see the `dataviz` skill before drawing charts. It is a self-contained HTML page fed by the same aggregated numbers.

## Notes & limitations

- **Areas come from the record `domain`** (`backend`/`frontend`/`qa`). A ticket worked by more than one area appears under each — that is intended (each area's contribution is separate). In **Totals**, a ticket's *estimate* and *bug count* are counted **once per area** (they are ticket-wide), while *logged time* is attributed **per user** from worklog authors where available.
- **Date = the AI record's `at`** (the day the metric was measured/confirmed). The JQL `updated >=` window is only a pre-filter; precise period membership is decided by `at` in the aggregator.
- **Original estimate** = Jira `timeoriginalestimate`; **logged time** = Jira/Tempo worklogs (`worklog` per author, else the `timespent` aggregate) — shown in **hours** (Jira's own d/h view uses 8h/day). If the `worklog` list is truncated (Jira returns a capped number inline), per-user time may be partial — flagged in Notes; use the worklog endpoint or Tempo API for exhaustive per-user logs.
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

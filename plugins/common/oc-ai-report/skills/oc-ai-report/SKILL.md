---
name: oc-ai-report
description: Produce a cross-ticket AI-usage report over a period, split by area (backend / frontend / QA) and grouped by date → user → ticket, augmented per ticket with the original estimate, Tempo-logged time, and the number of linked bugs. Reads the "AI metrics" JSON field from Jira; read-only.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD]"
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

## Task 3 — Present (and optionally visualise)

- Show the Markdown report.
- Offer a **dashboard Artifact** (bar charts: contribution/retention per area & developer, estimate-vs-logged, bug counts). Build it only if the user asks — see the `dataviz` skill before drawing charts. It is a self-contained HTML page fed by the same aggregated numbers.

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

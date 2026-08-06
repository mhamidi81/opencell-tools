---
name: oc-time-report
description: Produce an estimation-vs-logged-hours report over a period, independent of the AI-usage JSON. Tempo-worklog driven — one row per developer x ticket with ticket type, area (from the developer roster), title, Architect estimate, Dev-lead estimate, logged hours, bug hours, time gain (without/with bugs) and child-bug count. Prints Markdown and writes a styled, date-stamped HTML file and a CSV to ./docs/. Reads Jira (Atlassian MCP) + Tempo (TEMPO_API_TOKEN).
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--project INTRD] [--out PATH] [--csv PATH]"
---

## Purpose

A team **estimation-vs-actual** report. Unlike `/oc-ai-report`, this one is **not** tied to the AI-usage JSON field — it is driven by **Tempo worklogs**: for every developer who logged time on a ticket in the window, it produces one row:

> **Developer · Ticket · Type · Area · Title · A. Est h · DL. Est h · Logged h · Bug h · Time gain (w/o · w bugs) · Bugs**

- **Area** comes from the **developer roster** below (area is a property of the person), not the ticket.
- **A. Est h** (Architect) — the Story's per-area estimate custom fields (days ×8), else the ticket's own estimate.
- **DL. Est h** (Dev-lead) — the ticket's estimation field: for a **Story**, the sum of that area's child **sub-task** estimates (sub-bugs excluded); for a **Bug/Enabler**, the ticket's own estimate.
- **Logged h** — the developer's Tempo hours on the ticket + its **non-bug** sub-tasks (rolled up to the parent).
- **Bug h** — the developer's Tempo hours on the ticket's child **Bug/Sub-bug** sub-tasks.
- **Time gain** — `(A.Est − Logged)/A.Est` and `(A.Est − (Logged+Bug h))/A.Est`, shown `without / with` bug hours.
- **Bugs** — count of the ticket's child **Bug/Sub-bug** sub-issues; **only for Story / Enabler** tickets (a Bug ticket's own row shows 0 and all its time is Logged, not Bug h).

Output: Markdown in-session, plus a styled **HTML** file and a **CSV** of the detail rows, both date-stamped in `./docs/`.

## Access

- **Atlassian MCP** (site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`) for Jira reads. If not connected, tell the user to run `/mcp` and stop.
- **Tempo** via `TEMPO_API_TOKEN` (each developer's own token, *Tempo → Settings → API keys*, worklog **read** scope). This report **requires** Tempo — logged hours are its whole point. The token is read from the environment, never passed on the command line.

## Arguments

Parse `$ARGUMENTS` — all optional. Bare `/oc-time-report` = **last 30 days**, project **INTRD**.

- `--since YYYY-MM-DD` — start (inclusive). Default: 30 days before `--until`.
- `--until YYYY-MM-DD` — end (exclusive). Default: tomorrow.
- `--project KEY` — Jira project. Default `INTRD`.
- `--out PATH` — HTML output. Default `./docs/time-report-<TODAY>.html`.
- `--csv PATH` — CSV output. Default `./docs/time-report-<TODAY>.csv`.

Compute dates with `date -u +%Y-%m-%d` etc.; echo the resolved window back to the user.

## Developer roster (name → area)

Area is per developer. Resolve each name to a Jira **accountId** with `lookupJiraAccountId` (names below may differ slightly from the Jira display name — use the closest match, and warn on any you cannot resolve). Write the resolved map to `devmap.json` as `{ "<accountId>": {"name": "<display>", "area": "backend|frontend|qa"} }`.

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

For each roster name call `lookupJiraAccountId`; build `devmap.json`. Keep only successfully resolved developers; list any unresolved names in the report's Notes. Collect the set of resolved accountIds as `ACCTS` (used to filter Tempo).

## Task 2 — Fetch Tempo worklogs for the window (Pass T)

Write `fetch_tempo_all.py` (below) to scratchpad and run it. It pages `GET https://api.tempo.io/4/worklogs?from=<SINCE>&to=<UNTIL-1day>` (Tempo `to` is inclusive; pass the last in-window day), keeps only worklogs whose `author.accountId` is in `ACCTS`, and writes:
- `tempo.json` — `{ "<issueId>": { "<accountId>": seconds } }`
- `worklog_ids.txt` — the distinct worklogged **issue ids**, comma-separated.

```bash
python "<SCRATCHPAD>/fetch_tempo_all.py" --from [SINCE] --to [UNTIL] --accounts "<acc1,acc2,...>" \
  --out "<SCRATCHPAD>/tempo.json" --ids-out "<SCRATCHPAD>/worklog_ids.txt"
```

If Tempo returns nothing, tell the user and stop.

## Task 3 — Fetch ticket metadata (Jira)

The rows are at **parent-ticket** granularity, so we need each worklogged issue plus its parent chain and the parents' full sub-task lists.

1. **Worklogged issues** — `searchJiraIssuesUsingJql` `key in (<worklog_ids as keys>)` — but Tempo gives numeric ids; instead query by id: `issue in (<ids>)` is not valid, so use `id in (<ids>)` via JQL `id in (12345,...)` (Jira accepts numeric ids in `id in (...)`). Fields: `["summary","issuetype","components","timeoriginalestimate","parent","customfield_10157","customfield_10158","customfield_10189"]`. Batch ≤ ~80 ids. Collect nodes.
2. **Parents** — from those nodes, collect every `fields.parent.key` not already fetched; fetch them (same fields) so every rolled-up ticket is present.
3. **All sub-tasks of the tickets** — for the set of parent-ticket keys (the union of top-level worklogged issues and the parents from step 2), fetch `parent in (<ticketKeys>)` (same fields) so Dev-lead estimate and bug counts see every sub-task, not only worklogged ones.

Merge all nodes into one `issues.json` (`{issues:{nodes:[…]}}`; dedupe by key). Keep the numeric `id` on each node (the aggregator joins Tempo by id).

> On this project the estimate custom fields are `customfield_10157` = *Architect estimate back*, `customfield_10158` = *front*, `customfield_10189` = *QA estimate* (days).

## Task 4 — Aggregate & render

Write `time_report.py` (below) and run it:

```bash
python "<SCRATCHPAD>/time_report.py" --tempo "<SCRATCHPAD>/tempo.json" --issues "<SCRATCHPAD>/issues.json" \
  --devmap "<SCRATCHPAD>/devmap.json" --since [SINCE] --until [UNTIL] --project [PROJECT] \
  --md "<SCRATCHPAD>/report.md" --out "./docs/time-report-[TODAY].html" --csv "./docs/time-report-[TODAY].csv"
```

Show the Markdown (`report.md`) to the user and report the HTML + CSV paths.

### `fetch_tempo_all.py`

```python
#!/usr/bin/env python3
"""Fetch all Tempo worklogs in a window and roll up to {issueId: {accountId: seconds}},
keeping only the given author accountIds. Reads TEMPO_API_TOKEN from the environment."""
import argparse, json, os, sys, urllib.request, urllib.error

BASE = "https://api.tempo.io/4"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)   # exclusive end (we query to=to-1day is caller's job; here inclusive)
    ap.add_argument("--accounts", default="")
    ap.add_argument("--out", required=True); ap.add_argument("--ids-out", required=True)
    a = ap.parse_args()
    token = os.environ.get("TEMPO_API_TOKEN")
    if not token:
        sys.stderr.write("TEMPO_API_TOKEN not set — cannot build a time report.\n"); sys.exit(2)
    keep = {x.strip() for x in a.accounts.split(",") if x.strip()}
    out = {}; n = 0
    url = f"{BASE}/worklogs?from={a.frm}&to={a.to}&limit=1000"
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"Tempo HTTP {ex.code}: {ex.read()[:300]}\n"); sys.exit(3)
        for w in data.get("results") or []:
            acc = (w.get("author") or {}).get("accountId")
            if keep and acc not in keep: continue
            iid = str((w.get("issue") or {}).get("id"))
            if not iid or iid == "None": continue
            out.setdefault(iid, {})
            out[iid][acc] = out[iid].get(acc, 0) + (w.get("timeSpentSeconds") or 0)
            n += 1
        url = (data.get("metadata") or {}).get("next")
    json.dump(out, open(a.out, "w"))
    open(a.ids_out, "w").write(",".join(sorted(out.keys())))
    sys.stderr.write(f"Tempo: {n} worklogs kept across {len(out)} issues.\n")

if __name__ == "__main__":
    main()
```

### `time_report.py`

```python
#!/usr/bin/env python3
"""Estimation-vs-logged report. Rows = (developer, parent-ticket) from Tempo worklogs.
Area from the developer roster; A/DL estimates, bug count & bug hours from Jira metadata."""
import argparse, json, re, html, csv, os
from collections import defaultdict

COMP_AREA = {"backend": "backend", "frontend": "frontend", "testing": "qa"}
_TAG = re.compile(r"\[\s*(back|front|test)", re.I)
AREA_EST_FIELD = {"backend": "customfield_10157", "frontend": "customfield_10158", "qa": "customfield_10189"}
DAY_HOURS = 8
BUG_TYPES = {"bug", "sub-bug"}
TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Bug", "enabler": "Enabler"}

def nodes(data):
    iss = data.get("issues", data) if isinstance(data, dict) else data
    if isinstance(iss, dict): iss = iss.get("nodes", [])
    return iss or []

def hours(s): return round((s or 0) / 3600, 1)
def is_bug(f): return ((f.get("issuetype") or {}).get("name") or "").lower() in BUG_TYPES
def ticket_type(f): 
    n = (f.get("issuetype") or {}).get("name") or ""
    return TYPE_MAP.get(n.lower(), n or "?")

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
        return round(v * DAY_HOURS, 1) if isinstance(v, (int, float)) else 0.0
    return hours(f.get("timeoriginalestimate"))

def gain_pct(est, logged): return round((est - logged) / est * 100) if est else None
def gain_str(g): return "-" if g is None else (f"+{g}%" if g >= 0 else f"{g}%")
def gain_two(est, logged, bug):
    return f"{gain_str(gain_pct(est, logged))} / {gain_str(gain_pct(est, logged + bug))}"
def e(x): return html.escape(str(x))

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

    by_id = {str(n.get("id")): n for n in ns}
    by_key = {n.get("key"): n for n in ns}
    children = defaultdict(list)
    for n in ns:
        pk = ((n.get("fields") or {}).get("parent") or {}).get("key")
        if pk: children[pk].append(n)

    # accumulate (acc, ticketKey) -> logged / bugLogged seconds
    acc_rows = defaultdict(lambda: {"logged": 0.0, "bugLogged": 0.0})
    warn = []
    for iid, per in tempo.items():
        node = by_id.get(str(iid))
        if not node:
            continue  # metadata for this worklogged issue was not fetched
        nf = node.get("fields") or {}
        pk = (nf.get("parent") or {}).get("key")
        is_subtask_bug = bool(pk) and is_bug(nf)
        tkey = pk if (pk and pk in by_key) else node.get("key")
        for acc, sec in per.items():
            if acc not in devmap: continue
            row = acc_rows[(acc, tkey)]
            if is_subtask_bug: row["bugLogged"] += sec
            else: row["logged"] += sec

    rows = []
    for (acc, tkey), agg in acc_rows.items():
        if a.project and not str(tkey).startswith(a.project + "-"): continue  # keep only the target project
        tnode = by_key.get(tkey)
        if not tnode: continue
        tf = tnode.get("fields") or {}
        ttype = ticket_type(tf); area = devmap[acc]["area"]
        a_est = area_estimate_h(tf, area)
        # Dev-lead estimate
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
        # bug count: child Bug/Sub-bug of the ticket, US/Enabler only
        bugs = 0
        if ttype in ("US", "Enabler"):
            bugs = sum(1 for c in children.get(tkey, []) if is_bug(c.get("fields") or {}))
        logged = hours(agg["logged"]); bug_logged = hours(agg["bugLogged"])
        rows.append({"acc": acc, "dev": devmap[acc]["name"], "area": area, "key": tkey,
                     "ttype": ttype, "title": (tf.get("summary") or "")[:70],
                     "aEst": a_est, "dlEst": dl_est, "logged": logged, "bugLogged": bug_logged, "bugs": bugs})

    rows.sort(key=lambda r: (r["area"], r["dev"].lower(), r["key"]))

    # ---------- Markdown ----------
    md = []; P = md.append
    P(f"# Estimation vs logged — {a.project}, [{a.since or '…'} … {a.until or '…'})\n")
    if not rows:
        P("_No logged time for the roster in this window._")
    else:
        # Totals by area
        AR = defaultdict(lambda: {"devs": set(), "tickets": set(), "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "bugLogged": 0.0, "bugs": 0})
        seen_tik = defaultdict(set)
        for r in rows:
            g = AR[r["area"]]; g["devs"].add(r["acc"]); g["tickets"].add(r["key"])
            g["logged"] += r["logged"]; g["bugLogged"] += r["bugLogged"]
            if r["key"] not in seen_tik[r["area"]]:
                seen_tik[r["area"]].add(r["key"]); g["aEst"] += r["aEst"]; g["dlEst"] += r["dlEst"]; g["bugs"] += r["bugs"]
        P("## Totals by area\n")
        P("| Area | Devs | Tickets | A. Est h | DL. Est h | Logged h | Bug h | Time gain | Bugs |")
        P("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
        for ar in ("backend", "frontend", "qa"):
            if ar not in AR: continue
            g = AR[ar]
            P(f"| {ar.capitalize()} | {len(g['devs'])} | {len(g['tickets'])} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
              f"{round(g['logged'],1)} | {round(g['bugLogged'],1)} | {gain_two(g['aEst'], g['logged'], g['bugLogged'])} | {g['bugs']} |")
        # Summary by developer
        DV = defaultdict(lambda: {"area": "", "tickets": set(), "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "bugLogged": 0.0, "bugs": 0})
        for r in rows:
            g = DV[r["dev"]]; g["area"] = r["area"]; g["tickets"].add(r["key"])
            g["aEst"] += r["aEst"]; g["dlEst"] += r["dlEst"]; g["logged"] += r["logged"]; g["bugLogged"] += r["bugLogged"]; g["bugs"] += r["bugs"]
        P("\n## Summary by developer\n")
        P("| Developer | Area | Tickets | A. Est h | DL. Est h | Logged h | Bug h | Time gain | Bugs |")
        P("|---|---|--:|--:|--:|--:|--:|--:|--:|")
        for dev in sorted(DV, key=str.lower):
            g = DV[dev]
            P(f"| {dev} | {g['area']} | {len(g['tickets'])} | {round(g['aEst'],1)} | {round(g['dlEst'],1)} | "
              f"{round(g['logged'],1)} | {round(g['bugLogged'],1)} | {gain_two(g['aEst'], g['logged'], g['bugLogged'])} | {g['bugs']} |")
        # Detail
        P("\n## Detail (developer x ticket)\n")
        P("| Developer | Ticket | Type | Area | Title | A. Est h | DL. Est h | Logged h | Bug h | Time gain | Bugs |")
        P("|---|---|---|---|---|--:|--:|--:|--:|--:|--:|")
        for r in rows:
            P(f"| {r['dev']} | {r['key']} | {r['ttype']} | {r['area']} | {r['title']} | {r['aEst']} | {r['dlEst']} | "
              f"{r['logged']} | {r['bugLogged']} | {gain_two(r['aEst'], r['logged'], r['bugLogged'])} | {r['bugs']} |")
    if warn:
        P("\n## Notes")
        for w in warn[:30]: P(f"- {w}")
    md_text = "\n".join(md)
    if a.md: open(a.md, "w", encoding="utf-8").write(md_text)
    print(md_text)

    # ---------- CSV (detail) ----------
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Developer", "Ticket", "Type", "Area", "Title", "A. Est h", "DL. Est h",
                        "Logged h", "Bug h", "Time gain % (no bugs)", "Time gain % (with bugs)", "Bugs"])
            for r in rows:
                w.writerow([r["dev"], r["key"], r["ttype"], r["area"], r["title"], r["aEst"], r["dlEst"],
                            r["logged"], r["bugLogged"], gain_pct(r["aEst"], r["logged"]),
                            gain_pct(r["aEst"], r["logged"] + r["bugLogged"]), r["bugs"]])

    # ---------- HTML ----------
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    def cell(v): return "" if v is None else v
    B = []; W = B.append
    W("<h1>Estimation vs logged hours</h1>")
    W(f'<p class="meta">Project <b>{e(a.project)}</b> &middot; [{e(a.since or "…")} … {e(a.until or "…")}) &middot; {len(rows)} rows</p>')
    if not rows:
        W('<p>No logged time for the roster in this window.</p>')
    else:
        W("<h2>Detail (developer &times; ticket)</h2>")
        head = ["Developer","Ticket","Type","Area","Title","A. Est h","DL. Est h","Logged h","Bug h","Time gain","Bugs"]
        left = {"Developer","Ticket","Type","Area","Title"}
        W('<div class="tw"><table><thead><tr>' + "".join(f'<th class="{ "" if h in left else "r" }">{e(h)}</th>' for h in head) + "</tr></thead><tbody>")
        for r in rows:
            W(f'<tr><td>{e(r["dev"])}</td><td class="key">{e(r["key"])}</td><td>{e(r["ttype"])}</td><td>{e(r["area"])}</td>'
              f'<td>{e(r["title"])}</td><td class="r">{r["aEst"]}</td><td class="r">{r["dlEst"]}</td>'
              f'<td class="r">{r["logged"]}</td><td class="r">{r["bugLogged"]}</td>'
              f'<td class="r">{gain_two(r["aEst"], r["logged"], r["bugLogged"])}</td><td class="r">{r["bugs"]}</td></tr>')
        W("</tbody></table></div>")
    W('<p class="foot">Rows = developer &times; ticket from Tempo worklogs. Area from the developer roster. '
      'A. Est = Architect (per-area estimate custom fields, days&times;8, else ticket estimate); DL. Est = Dev-lead '
      '(Story: sum of child sub-task estimates per area; Bug/Enabler: ticket estimate). Logged = dev hours on the ticket '
      '+ non-bug sub-tasks; Bug h = dev hours on child Bug/Sub-bugs. Time gain = (A.Est&minus;Logged)/A.Est shown '
      'without / with bug hours. Bugs = child Bug/Sub-bug count (Story/Enabler only). Generated by <code>/oc-time-report</code>.</p>')
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
.wrap {{ max-width:1200px; margin:0 auto; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }}
h2 {{ font-size:1.15rem; margin:2rem 0 .6rem; padding-bottom:.35rem; border-bottom:2px solid var(--line); }}
.meta {{ color:var(--muted); margin:0 0 1.25rem; }}
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ padding:.5rem .7rem; text-align:left; white-space:nowrap; border-bottom:1px solid var(--line); }}
thead th {{ background:var(--head); font-weight:600; position:sticky; top:0; }}
tbody tr:nth-child(even) {{ background:var(--zebra); }}
.r {{ text-align:right; }}
.key {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--accent); font-weight:600; }}
.foot {{ color:var(--muted); font-size:.8rem; margin-top:2rem; border-top:1px solid var(--line); padding-top:1rem; }}
</style></head><body><div class="wrap">
{body}
</div></body></html>"""
    open(a.out, "w", encoding="utf-8").write(doc)

if __name__ == "__main__":
    main()
```

## Notes & limitations

- **Tempo token visibility (important).** A personal `TEMPO_API_TOKEN` only returns the worklogs that token's owner is permitted to see — on this instance a token scoped to one team (e.g. backend) returns **only that team's** worklogs, so developers from other areas silently produce **zero rows**. Always report which areas actually appeared, and warn if a roster area is entirely missing. For full-team coverage use a token with organisation-wide worklog-view permission, or run once per team and merge.
- **Point-in-time.** Logged hours reflect the Tempo state when you run it. It requires `TEMPO_API_TOKEN`.
- **Area is per developer** (from the roster), not the ticket — a backend dev's rows are all `backend` even on a cross-area story.
- **Roll-up.** A developer's worklogs on a Story's non-bug sub-tasks fold into that Story's Logged h; worklogs on its Bug/Sub-bug sub-tasks fold into Bug h. A top-level Bug the developer logged on is its own row (all time = Logged h, Bugs = 0).
- **Estimates.** A. Est needs the per-area estimate custom fields on the Story; DL. Est needs child sub-task estimates (Story) or the ticket estimate (Bug/Enabler). Rows for tickets with no estimate show `0` / `–` time gain.
- **Read-only** — the command never writes to Jira; the only outbound call is the read-only Tempo fetch.

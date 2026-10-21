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
DATE_SRC = {"test": "first sent to test (Ready for Test / In Test)",
            "postdev": "first moved to a post-dev status (never sent to test)",
            "resolved": "resolution date (no test / post-dev transition)",
            "worklog": "last worklog (still in development)"}

def ticket_date(f, wlast=""):
    """The ticket's date for range-filtering & grouping, YYYY-MM-DD, and its source: the date it was
    FIRST sent to test (testDate, from the status changelog — see jira_fetch_dates.py), else the last
    worklog date on the ticket + its sub-issues (still in development). Never `updated`."""
    d = (f.get("testDate") or "")[:10]
    if d: return d, f.get("dateSrc") or "test"
    if "dateSrc" not in f and f.get("resolutiondate"):     # issues.json from an older fetch
        return f["resolutiondate"][:10], "resolved"
    return (wlast or "")[:10], ("worklog" if wlast else "")

def area_of(f):
    for c in f.get("components") or []:
        ar = COMP_AREA.get((c.get("name") or "").strip().lower())
        if ar: return ar
    m = _TAG.search(f.get("summary") or "")
    if m: return {"back": "backend", "front": "frontend", "test": "qa"}[m.group(1).lower()]
    return None

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
    """AccountIds that authored an AI-metrics record on THIS issue (customfield_10745,
    opencell.ai-usage JSON). Record keys are 'domain/accountId/name'; the accountId (middle
    segment) matches the roster. A worklog on this issue by one of these accounts is AI-assisted."""
    raw = _cf_text(f.get("customfield_10745")); accs = set()
    if raw and raw.strip():
        try: doc = json.loads(raw)
        except json.JSONDecodeError: doc = None
        for rk in ((doc or {}).get("records") or {}):
            p = rk.split("/", 2)
            if len(p) >= 2 and p[0] in AREAS and p[1]: accs.add(p[1])
    return accs

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

def version_options(fixvers):
    """Group the Fix Version/s picklist: a numeric version like 17.2.1 yields a MAJOR group
    (base "17" -> label "17.x") and a MAJOR.MINOR group (base "17.2" -> label "17.2.x"); the
    filter matches a version that equals the base or starts with base+".". Non-numeric names are
    kept as their own exact option. Returns [(value, label)] sorted by version, names last.
    (The per-ticket Fix ver column still shows each ticket's complete version number.)"""
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
    opts = [(b, bases[b]) for b in sorted(bases, key=keyf)]
    opts += [(v, v) for v in sorted(names)]
    return opts

def build_ticket_rows(all_nodes, tempo, devmap, project, wdates=None, since=None, until=None):
    """Rows are PARENT tickets whose ticket date (first sent to test, see ticket_date) is in
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
    # Each per-dev seconds value is split into a TWO-ELEMENT stream [ai_secs, nonai_secs]: a worklog
    # is AI-assisted when its author holds an AI-metrics record on the exact issue it is booked on.
    def _add(box, acc, sec, is_ai): box[acc][0 if is_ai else 1] += sec
    tk = defaultdict(lambda: {"devLogged": defaultdict(lambda: [0.0, 0.0]), "subbugs": {}, "date": ""})
    for iid, per in tempo.items():
        node = by_id.get(str(iid))
        if not node: continue
        nf = node.get("fields") or {}
        ai_accs = ai_accounts(nf)                      # accounts with an AI record on THIS issue
        pk = (nf.get("parent") or {}).get("key")
        st = is_subtask(nf)
        tkey = pk if (st and pk and pk in by_key) else node.get("key")
        d = wdates.get(str(iid), "")
        if d and d > tk[tkey]["date"]: tk[tkey]["date"] = d
        if st and is_bug(nf):
            # a sub-bug is judged on its OWN AI record only (independent of the parent)
            b = tk[tkey]["subbugs"].setdefault(str(iid), {"perdev": defaultdict(lambda: [0.0, 0.0])})
            for acc, sec in per.items():
                if acc in devmap: _add(b["perdev"], acc, sec, acc in ai_accs)
                else: unknown[acc] += sec
        else:
            # non-bug worklog: on the parent, or on a non-bug sub-task (which rolls up to the parent).
            # A US's dev work is logged on its sub-tasks, so the PARENT's AI-record accounts propagate
            # down to those sub-tasks — a developer with an AI record on the US has their sub-task
            # hours counted as AI too (not just hours booked directly on the parent).
            eff_ai = ai_accs
            if st and pk and pk in by_key:
                eff_ai = ai_accs | ai_accounts(by_key[pk].get("fields") or {})
            for acc, sec in per.items():
                if acc in devmap: _add(tk[tkey]["devLogged"], acc, sec, acc in eff_ai)
                else: unknown[acc] += sec

    rows = []
    for tkey, agg in tk.items():
        if project and not any(str(tkey).startswith(q.strip() + "-") for q in str(project).split(",") if q.strip()): continue
        tnode = by_key.get(tkey)
        if not tnode: continue
        tf = tnode.get("fields") or {}
        if not agg["devLogged"] and not agg["subbugs"]: continue
        tdate, tsrc = ticket_date(tf, agg["date"])    # first sent to test, else last worklog
        if since and (not tdate or tdate < since): continue
        if until and (not tdate or tdate >= until): continue
        ttype = ticket_type(tf); status = status_of(tf); final = is_final(ttype, status)
        pa = area_of(tf)

        # sub-bugs attributed by the FIXER's roster area (dev-centric, like Logged h): a developer's
        # sub-bug-fixing hours count toward their area's Sub-bug h and toward being that area's main
        # dev; a sub-bug counts once per area that worked on it. (Nothing is dropped for lacking a
        # component.) Each area's sub-bug hours are split into AI / non-AI streams.
        area_sub_ai = {ar: 0.0 for ar in AREAS}; area_sub_no = {ar: 0.0 for ar in AREAS}
        area_bug_ct = {ar: 0 for ar in AREAS}
        sub_dev = defaultdict(lambda: defaultdict(float))   # total (AI+non), for main-dev ranking
        archpr_logged = 0.0; archpr_devs = {}
        for b in agg["subbugs"].values():
            touched = set()
            for acc, (sai, sno) in b["perdev"].items():
                sec = sai + sno
                if devmap[acc]["area"] == "overhead":   # ARCHI/PO/DEVOPS/CONSULTANT -> overhead, not an area
                    archpr_logged += sec; archpr_devs[devmap[acc]["name"]] = archpr_devs.get(devmap[acc]["name"], 0.0) + sec
                    continue
                ar = devmap[acc]["area"]; area_sub_ai[ar] += sai; area_sub_no[ar] += sno; sub_dev[ar][acc] += sec; touched.add(ar)
            for ar in touched: area_bug_ct[ar] += 1

        # main developer per area = the area's roster dev with the most TOTAL work on the ticket
        # (non-bug logged + their own sub-bug-fixing hours) — so a real bug-fixer outranks someone
        # who only did a token review/touch on the parent.
        by_area_dev = defaultdict(dict)
        for acc, (sai, sno) in agg["devLogged"].items():
            if devmap[acc]["area"] == "overhead": continue   # overhead people are never an area main dev
            by_area_dev[devmap[acc]["area"]][acc] = by_area_dev[devmap[acc]["area"]].get(acc, 0) + sai + sno
        for ar in AREAS:
            for acc, sec in sub_dev.get(ar, {}).items():
                by_area_dev[ar][acc] = by_area_dev[ar].get(acc, 0) + sec
        main = {ar: max(d, key=lambda a: d[a]) for ar, d in by_area_dev.items() if d}

        # attribute each developer's NON-BUG logged hours (AI / non-AI): own area, except overhead
        # people (ARCHI/PO/DEVOPS/CONSULTANT/blank) whose hours go to the ticket-overhead bucket.
        area_log_ai = {ar: 0.0 for ar in AREAS}; area_log_no = {ar: 0.0 for ar in AREAS}
        for acc, (sai, sno) in agg["devLogged"].items():
            ar = devmap[acc]["area"]
            if ar == "overhead":
                archpr_logged += sai + sno; archpr_devs[devmap[acc]["name"]] = archpr_devs.get(devmap[acc]["name"], 0.0) + sai + sno
            else:
                area_log_ai[ar] += sai; area_log_no[ar] += sno

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

        areas_out = {}
        for ar in AREAS:
            log_ai = hours(area_log_ai[ar]); log_no = hours(area_log_no[ar]); log_h = round(log_ai + log_no, 1)
            sub_ai = hours(area_sub_ai[ar]); sub_no = hours(area_sub_no[ar]); sub_h = round(sub_ai + sub_no, 1)
            areas_out[ar] = {"main": devmap[main[ar]]["name"] if ar in main else "",
                             "aEst": area_aest[ar], "dlEst": area_dlest[ar],
                             "logged": log_h, "loggedAI": log_ai, "loggedNo": log_no,
                             "subBug": sub_h, "subBugAI": sub_ai, "subBugNo": sub_no,
                             "totalDev": round(log_h + sub_h, 1), "bugs": area_bug_ct[ar]}
        archpr_h = hours(archpr_logged)
        total_logged = round(sum(areas_out[ar]["logged"] for ar in AREAS) + archpr_h, 1)
        total_dev = round(sum(areas_out[ar]["totalDev"] for ar in AREAS) + archpr_h, 1)
        date = tdate; month = (date or "")[:7] or "no-date"
        rows.append({"key": tkey, "project": str(tkey).split("-")[0], "fixVersions": tf.get("fixVersions") or [],
                     "ttype": ttype, "title": (tf.get("summary") or "")[:60],
                     "status": status, "final": final, "date": date, "dateSrc": tsrc, "month": month, "areas": areas_out,
                     "archprH": archpr_h,
                     "archprDevs": [(n, hours(archpr_devs[n])) for n in sorted(archpr_devs, key=lambda n: -archpr_devs[n])],
                     "totalLogged": total_logged, "totalDev": total_dev,
                     "aiAny": any((areas_out[ar]["loggedAI"] or areas_out[ar]["subBugAI"]) for ar in AREAS),
                     "bugsTotal": sum(area_bug_ct[ar] for ar in AREAS)})
    rows.sort(key=lambda r: (r["date"], r["totalLogged"]), reverse=True)   # newest ticket-date first
    return rows, unknown

# ---------- per-area totals (across tickets) ----------
def area_totals(rows):
    # aE/aL/aB (Arch) & dE/dL/dB (DL) are the gain basis: summed over only tickets carrying that
    # estimate, so unestimated tickets' logged hours don't inflate the aggregate gain.
    tot = {ar: {"tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "subBug": 0.0, "bugs": 0,
                "loggedAI": 0.0, "loggedNo": 0.0, "subBugAI": 0.0, "subBugNo": 0.0,
                "aE": 0.0, "aL": 0.0, "aB": 0.0, "dE": 0.0, "dL": 0.0, "dB": 0.0} for ar in AREAS}
    archpr = 0.0; grand_log = 0.0
    for r in rows:
        for ar in AREAS:
            a = r["areas"][ar]
            if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                g = tot[ar]; g["tickets"] += 1
                for k in ("aEst", "dlEst", "logged", "subBug", "bugs", "loggedAI", "loggedNo", "subBugAI", "subBugNo"): g[k] += a[k]
                if a["aEst"] >= EST_MIN: g["aE"] += a["aEst"]; g["aL"] += a["logged"]; g["aB"] += a["subBug"]
                if a["dlEst"] >= EST_MIN: g["dE"] += a["dlEst"]; g["dL"] += a["logged"]; g["dB"] += a["subBug"]
        archpr += r["archprH"]; grand_log += r["totalLogged"]
    return tot, round(archpr, 1), round(grand_log, 1)

def months_of(rows):
    return sorted({r["month"] for r in rows}, reverse=True)

# ---------- shared renderers (reused for the overall view and per month) ----------
def pct_ai(ai_h, tot_h): return f"{round(ai_h / tot_h * 100)}%" if tot_h else "–"   # AI share of an area's dev hours
def md_totals_lines(rows):
    tot, archpr_tot, grand_log = area_totals(rows)   # all values in hours; shown as days below
    def pl(v): return f"{round(v / grand_log * 100)}%" if grand_log else "–"   # % of total logged h
    out = ["| Area | Tickets | A. Est d | DL. Est d | Total dev d | % Logged | % AI | Logged d | Log AI d | Log non d | Sub-bug d | SB AI d | SB non d | Arch gain | DL gain | Sub-bugs |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for ar in AREAS:
        g = tot[ar]
        out.append(f"| {AREA_LABEL[ar]} | {g['tickets']} | {days(g['aEst'])} | {days(g['dlEst'])} | "
                   f"{days(g['logged'] + g['subBug'])} | {pl(g['logged'])} | {pct_ai(g['loggedAI'] + g['subBugAI'], g['logged'] + g['subBug'])} | "
                   f"{days(g['logged'])} | {days(g['loggedAI'])} | {days(g['loggedNo'])} | "
                   f"{days(g['subBug'])} | {days(g['subBugAI'])} | {days(g['subBugNo'])} | "
                   f"{gain_two(g['aE'], g['aL'], g['aB'])} | {gain_two(g['dE'], g['dL'], g['dB'])} | {g['bugs']} |")
    out.append(f"| Overhead | – | – | – | {days(archpr_tot)} | {pl(archpr_tot)} | – | {days(archpr_tot)} | – | – | – | – | – | – | – | – |")
    t_sub_h = sum(tot[ar]["subBug"] for ar in AREAS)
    t_log_ai = sum(tot[ar]["loggedAI"] for ar in AREAS); t_log_no = sum(tot[ar]["loggedNo"] for ar in AREAS)
    t_sub_ai = sum(tot[ar]["subBugAI"] for ar in AREAS); t_sub_no = sum(tot[ar]["subBugNo"] for ar in AREAS)
    t_ai_h = sum(tot[ar]["loggedAI"] + tot[ar]["subBugAI"] for ar in AREAS)
    t_aest = days(sum(tot[ar]["aEst"] for ar in AREAS)); t_dlest = days(sum(tot[ar]["dlEst"] for ar in AREAS))
    t_sub = days(t_sub_h); t_bugs = sum(tot[ar]["bugs"] for ar in AREAS)
    grand_dev = days(grand_log + t_sub_h)   # Total dev = all logged (areas + Overhead) + all sub-bug
    t_area_dev = sum(tot[ar]["logged"] + tot[ar]["subBug"] for ar in AREAS)
    out.append(f"| **Total** | | {t_aest} | {t_dlest} | **{grand_dev}** | 100% | {pct_ai(t_ai_h, t_area_dev)} | "
               f"**{days(grand_log)}** | {days(t_log_ai)} | {days(t_log_no)} | "
               f"{t_sub} | {days(t_sub_ai)} | {days(t_sub_no)} | | | {t_bugs} |")
    return out

def gspan1(est, lb):   # single with-bug gain, coloured
    g = gain_pct(est, lb); c = gain_cls(g)
    return f'<span class="{c}">{gain_str(g)}</span>' if c else gain_str(g)

def html_totals_table(rows, tab="all", month="all"):
    # One row per area. Logged is split into AI / non-AI streams (a worklog is AI when its author holds
    # an AI-metrics record on the exact issue); % AI is the AI share of the area's dev hours (logged +
    # sub-bug). Arch/DL gain are single with-sub-bug gains on the estimated-tickets basis
    # (aEst/dlEst >= EST_MIN) so unestimated tickets' logged hours don't inflate them. (JS mirrors this.)
    def z(): return {"tickets": 0, "aEst": 0.0, "dlEst": 0.0, "logged": 0.0, "subBug": 0.0, "bugs": 0,
                     "loggedAI": 0.0, "loggedNo": 0.0, "subBugAI": 0.0, "subBugNo": 0.0,
                     "aE": 0.0, "aL": 0.0, "aB": 0.0, "dE": 0.0, "dL": 0.0, "dB": 0.0}
    tot = {ar: z() for ar in AREAS}
    archpr_tot = 0.0; grand_log = 0.0
    for r in rows:
        for ar in AREAS:
            a = r["areas"][ar]
            if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                g = tot[ar]; g["tickets"] += 1
                for k in ("aEst", "dlEst", "logged", "subBug", "bugs", "loggedAI", "loggedNo", "subBugAI", "subBugNo"): g[k] += a[k]
                if a["aEst"] >= EST_MIN: g["aE"] += a["aEst"]; g["aL"] += a["logged"]; g["aB"] += a["subBug"]
                if a["dlEst"] >= EST_MIN: g["dE"] += a["dlEst"]; g["dL"] += a["logged"]; g["dB"] += a["subBug"]
        archpr_tot += r["archprH"]; grand_log += r["totalLogged"]
    archpr_tot = round(archpr_tot, 1); grand_log = round(grand_log, 1)
    def pl(v): return f"{round(v / grand_log * 100)}%" if grand_log else "&ndash;"   # % of total logged
    def pctsub(logged, sub):
        den = logged + sub; return f"{round(sub / den * 100)}%" if den else "&ndash;"
    def pai(g):
        den = g["logged"] + g["subBug"]; return f"{round((g['loggedAI'] + g['subBugAI']) / den * 100)}%" if den else "&ndash;"
    h = [f"<div class=\"tw\" data-totals data-tab=\"{e(tab)}\" data-month=\"{e(month)}\"><table><thead><tr>"
         "<th>Area</th><th>Project</th><th class='r'>Tickets</th><th class='r'>A. Est d</th><th class='r'>DL. Est d</th>"
         "<th class='r'>Total dev d</th><th class='r'>%</th><th class='r'>% AI</th><th class='r'>Logged d</th><th class='r'>Log AI d</th><th class='r'>Log non d</th>"
         "<th class='r'>Sub-bug d</th><th class='r'>SB AI d</th><th class='r'>SB non d</th><th class='r'>% Sub-bug</th>"
         "<th class='r'>Arch gain</th><th class='r'>DL gain</th><th class='r'>Sub-bugs</th></tr></thead><tbody>"]
    for ar in AREAS:
        g = tot[ar]
        if not g["tickets"]: continue
        h.append(f"<tr><td class='name'>{AREA_LABEL[ar]}</td><td class='proj'>All</td><td class='r'>{g['tickets']}</td>"
                 f"<td class='r'>{days(g['aEst'])}</td><td class='r'>{days(g['dlEst'])}</td>"
                 f"<td class='r'>{days(g['logged']+g['subBug'])}</td><td class='r'>{pl(g['logged'])}</td><td class='r aih'>{pai(g)}</td><td class='r'>{days(g['logged'])}</td>"
                 f"<td class='r aih'>{days(g['loggedAI'])}</td><td class='r'>{days(g['loggedNo'])}</td>"
                 f"<td class='r'>{days(g['subBug'])}</td><td class='r aih'>{days(g['subBugAI'])}</td><td class='r'>{days(g['subBugNo'])}</td>"
                 f"<td class='r'>{pctsub(g['logged'], g['subBug'])}</td>"
                 f"<td class='r'>{gspan1(g['aE'], g['aL'] + g['aB'])} <span class='sm'>({g['tickets']})</span></td>"
                 f"<td class='r'>{gspan1(g['dE'], g['dL'] + g['dB'])}</td><td class='r'>{g['bugs']}</td></tr>")
    h.append(f"<tr><td class='name'>Overhead</td><td class='proj'>All</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>{days(archpr_tot)}</td><td class='r'>{pl(archpr_tot)}</td><td class='r'>&ndash;</td><td class='r'>{days(archpr_tot)}</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td>"
             f"<td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td><td class='r'>&ndash;</td></tr>")
    t_aest = sum(tot[ar]["aEst"] for ar in AREAS); t_dlest = sum(tot[ar]["dlEst"] for ar in AREAS)
    t_sub_h = sum(tot[ar]["subBug"] for ar in AREAS); t_log = sum(tot[ar]["logged"] for ar in AREAS)
    t_log_ai = sum(tot[ar]["loggedAI"] for ar in AREAS); t_log_no = sum(tot[ar]["loggedNo"] for ar in AREAS)
    t_sub_ai = sum(tot[ar]["subBugAI"] for ar in AREAS); t_sub_no = sum(tot[ar]["subBugNo"] for ar in AREAS)
    t_ai_h = sum(tot[ar]["loggedAI"] + tot[ar]["subBugAI"] for ar in AREAS); t_area_dev = t_log + t_sub_h
    t_bugs = sum(tot[ar]["bugs"] for ar in AREAS)
    grand_dev = days(grand_log + t_sub_h)   # Total dev = all logged (areas + Overhead) + all sub-bug
    t_aest_d = days(t_aest)
    tot_gain = gspan1(t_aest, grand_log + t_sub_h)   # Total row Arch gain = (A.Est - Total dev)/A.Est, i.e. -(Total dev/A.Est-1)
    tot_pai = f"{round(t_ai_h / t_area_dev * 100)}%" if t_area_dev else "&ndash;"
    h.append(f"<tr class='tot'><td class='name'>Total</td><td class='proj'>All</td><td></td>"
             f"<td class='r'>{t_aest_d}</td><td class='r'>{days(t_dlest)}</td>"
             f"<td class='r'>{grand_dev}</td><td class='r'>100%</td><td class='r aih'>{tot_pai}</td><td class='r'>{days(grand_log)}</td>"
             f"<td class='r aih'>{days(t_log_ai)}</td><td class='r'>{days(t_log_no)}</td>"
             f"<td class='r'>{days(t_sub_h)}</td><td class='r aih'>{days(t_sub_ai)}</td><td class='r'>{days(t_sub_no)}</td>"
             f"<td class='r'>{pctsub(t_log, t_sub_h)}</td>"
             f"<td class='r'>{tot_gain}</td><td></td><td class='r'>{t_bugs}</td></tr>")
    h.append("</tbody></table></div>")
    return "".join(h)

MG_COLS = [("backend", "Backend"), ("frontend", "Frontend"), ("qa", "QA"), ("overhead", "Overhead")]
def html_month_gain_table(rows, tab="all"):
    """Month-by-month Arch gain (with sub-bugs) per area, plus Overhead; each area cell is the gain
    with its ticket count and its AI share of dev hours in ( ). data-monthgain lets the project
    filter rebuild it."""
    months = sorted({r["month"] for r in rows}, reverse=True)
    h = [f'<div class="tw" data-monthgain data-tab="{e(tab)}"><table><thead><tr><th>Month</th><th class="r">Overall gain</th>'
         + "".join(f'<th class="r">{e(lbl)}</th>' for _, lbl in MG_COLS) + "</tr></thead><tbody>"]
    for m in months:
        mr = [r for r in rows if r["month"] == m]
        # Overall gain = (total Arch estimate - total dev) / total Arch estimate for the month; total dev
        # = all logged (areas + Overhead) + all sub-bug. Uses every ticket's A.Est (not the estimated-basis).
        m_aest = sum(r["areas"][ar]["aEst"] for r in mr for ar in AREAS)
        m_dev = sum(r["totalDev"] for r in mr)
        h.append(f'<tr><td class="name"><a href="#tot-{e(tab)}-{e(m)}">{e(m)}</a></td>'
                 f'<td class="r">{gspan1(m_aest, m_dev)}</td>')
        for ar, _ in MG_COLS:
            if ar == "overhead":
                cnt = sum(1 for r in mr if r["archprH"])
                oh = sum(r["archprH"] for r in mr); mtot = m_dev
                val = f'{round(oh / mtot * 100)}% <span class="sm">({cnt})</span>' if mtot else "&ndash;"
                h.append(f'<td class="r">{val}</td>'); continue
            est = log = bug = 0.0; cnt = 0; ai_h = 0.0; dev_h = 0.0
            for r in mr:
                a = r["areas"][ar]
                if a["logged"] or a["subBug"] or a["aEst"] or a["dlEst"]:
                    cnt += 1
                    ai_h += a["loggedAI"] + a["subBugAI"]; dev_h += a["logged"] + a["subBug"]
                    if a["aEst"] >= EST_MIN:   # gain basis: only tickets carrying an Architect estimate
                        est += a["aEst"]; log += a["logged"]; bug += a["subBug"]
            if not cnt:
                h.append('<td class="r">&ndash;</td>'); continue
            g = gain_pct(est, log + bug); pai = f"{round(ai_h / dev_h * 100)}%" if dev_h else "&ndash;"
            h.append(f'<td class="r {gain_cls(g)}">{gain_str(g)} <span class="sm">({cnt} &middot; AI {pai})</span></td>')
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)

MATRIX_SUB = ["Main dev", "A.Est d", "DL.Est d", "Tot dev d", "Logged (AI·non)", "Sub-bug (AI·non)", "Arch gain", "DL gain", "#SB"]
def html_matrix_head():
    head1 = ['<th rowspan="2">Ticket</th><th rowspan="2">Date</th><th rowspan="2">Type</th><th rowspan="2">Fix ver</th><th rowspan="2">Title</th>'
             '<th rowspan="2">Status</th><th rowspan="2" class="c">F</th>'
             '<th rowspan="2" class="c gaincol">Arch gain B/F/Q &middot; OH%<br><span class="sm">w/ bugs</span></th>'
             '<th rowspan="2" class="c gaincol">Logged+bug B/F/Q/OH<br><span class="sm">days</span></th>'
             '<th rowspan="2" class="r gaincol">Total logged d</th>'
             '<th rowspan="2" class="c gaincol">Overall arch gain<br><span class="sm">A.Est / Total dev</span></th>']
    for ar in AREAS:
        head1.append(f'<th colspan="{len(MATRIX_SUB)}" class="grp {ar}">{AREA_LABEL[ar]}</th>')
    head1.append('<th rowspan="2" class="r">Overhead d</th><th rowspan="2" class="r">Overhead %</th><th rowspan="2">Overhead people</th>')
    head2 = []
    for ar in AREAS:
        for i, s in enumerate(MATRIX_SUB):
            cls = "" if s == "Main dev" else ("c" if "·" in s else "r")
            head2.append(f'<th class="{cls}{" ledge" if i == 0 else ""}">{e(s)}</th>')
    return '<thead><tr>' + "".join(head1) + "</tr><tr>" + "".join(head2) + "</tr></thead>"

def html_matrix_body(rows):
    out = []
    for r in rows:
        fv = r.get("fixVersions") or []
        tds = [f'<td class="key"><a href="https://opencellsoft.atlassian.net/browse/{e(r["key"])}" target="_blank" rel="noopener">{e(r["key"])}</a></td>'
               f'<td class="sm" title="{e(DATE_SRC.get(r.get("dateSrc"), ""))}">{e(r["date"] or "–")}{"" if r.get("dateSrc") in ("test", None, "") else "*"}</td>'
               f'<td>{e(r["ttype"])}</td><td class="sm">{e(", ".join(fv)) if fv else "&ndash;"}</td><td class="ti">{e(r["title"])}</td><td>{e(r["status"])}</td>'
               f'<td class="c">{"<span class=fin>T</span>" if r["final"] else ""}</td>']
        # single column: back / front / QA Architect gain, considering sub-bugs (est vs logged+sub-bug)
        AG_LBL = {"backend": "B", "frontend": "F", "qa": "Q"}
        ag_parts = []
        for ar in AREAS:
            x = r["areas"][ar]
            ag_parts.append(f'{AG_LBL[ar]}&nbsp;{gain_span(gain_pct(x["aEst"], x["logged"] + x["subBug"]))}')
        oh_pct = round(r["archprH"] / r["totalDev"] * 100) if r["totalDev"] else None   # overhead share of ticket's total logged (incl. sub-bugs)
        ag_parts.append(f'OH&nbsp;{oh_pct}%' if oh_pct is not None else 'OH&nbsp;&ndash;')
        tds.append(f'<td class="c gaincol sm">{" ".join(ag_parts)}</td>')
        # total logged incl. sub-bug, per area + overhead (days)
        lb_parts = [f'{AG_LBL[ar]}&nbsp;{days(r["areas"][ar]["logged"] + r["areas"][ar]["subBug"])}' for ar in AREAS]
        lb_parts.append(f'OH&nbsp;{days(r["archprH"])}')
        tds.append(f'<td class="c gaincol sm">{" ".join(lb_parts)}</td>')
        # Total logged d (full logged incl. sub-bugs + overhead = Jira aggregate) and the Overall arch gain
        # = (accumulated Arch estimate - total dev) / accumulated Arch estimate, over all areas incl. overhead
        tot_aest = sum(r["areas"][ar]["aEst"] for ar in AREAS)
        tds.append(f'<td class="r tot gaincol">{days(r["totalDev"])}</td>'
                   f'<td class="c gaincol">{gain_span(gain_pct(tot_aest, r["totalDev"]))}</td>')
        for ar in AREAS:
            x = r["areas"][ar]; blank = not (x["logged"] or x["subBug"] or x["aEst"] or x["dlEst"] or x["main"])
            if blank:
                tds.append(f'<td class="ledge dim area-{ar}" colspan="{len(MATRIX_SUB)}">&ndash;</td>'); continue
            tds.append(f'<td class="name ledge area-{ar}">{e(x["main"])}</td>'
                       f'<td class="r area-{ar}">{days(x["aEst"])}</td><td class="r area-{ar}">{days(x["dlEst"])}</td>'
                       f'<td class="r area-{ar}">{days(x["totalDev"])}</td>'
                       f'<td class="c area-{ar}"><span class="aih">{days(x["loggedAI"])}</span> &middot; {days(x["loggedNo"])}</td>'
                       f'<td class="c area-{ar}"><span class="aih">{days(x["subBugAI"])}</span> &middot; {days(x["subBugNo"])}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["aEst"], x["logged"], x["subBug"])}</td>'
                       f'<td class="r area-{ar}">{gain_two_html(x["dlEst"], x["logged"], x["subBug"])}</td><td class="r area-{ar}">{x["bugs"]}</td>')
        people = ", ".join(f'{e(n)} {days(h)}d' for n, h in r["archprDevs"])
        oh_pct = round(r["archprH"] / r["totalDev"] * 100) if r["totalDev"] else None   # overhead share of ticket's total logged (incl. sub-bugs)
        tds.append(f'<td class="r">{days(r["archprH"]) if r["archprH"] else "&ndash;"}</td>'
                   f'<td class="r">{str(oh_pct) + "%" if oh_pct is not None else "&ndash;"}</td>'
                   f'<td class="sm">{people if people else "&ndash;"}</td>')
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
    w('<p class="bm">Arch gain (with sub-bugs) by month &mdash; ticket count &amp; AI share of dev hours in ( )</p>')
    w(html_month_gain_table(rs, tab))
    w('<p class="bm">By month</p>')
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details id="tot-{e(tab)}-{e(m)}" data-mtab="{e(tab)}" data-mon="{e(m)}"{op}><summary>{e(m)} '
          f'<span class="cnt">(<a href="#mtx-{e(tab)}-{e(m)}"><span class="mc">{len(mr)}</span> tickets</a>)</span></summary>{html_totals_table(mr, tab, m)}</details>')
    w("<h2>Per ticket &mdash; per-area columns</h2>")
    for i, m in enumerate(ms):
        mr = [r for r in rs if r["month"] == m]; op = " open" if i == 0 else ""
        w(f'<details id="mtx-{e(tab)}-{e(m)}" data-mtab="{e(tab)}" data-mon="{e(m)}"{op}><summary>{e(m)} <span class="cnt">(<span class="mc">{len(mr)}</span> tickets)</span></summary>'
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
            recs.append({"dev": x["main"], "area": ar, "month": r["month"],
                         "ai": (x["loggedAI"] + x["subBugAI"]) > 0,   # AI-assisted = this US-area logged any AI hours
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
             'Generated by <code>/oc-reports:oc-time-report</code>.</p>')
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
  function z(){ return {tickets:0,aEst:0,dlEst:0,logged:0,subBug:0,bugs:0,loggedAI:0,loggedNo:0,subBugAI:0,subBugNo:0,
    aE:0,aL:0,aB:0,dE:0,dL:0,dB:0}; }
  function g1(est,lb){ return gspan(gp(est,lb)); }   // single with-bug gain, coloured
  // area array layout: [0 aEst,1 dlEst,2 logged,3 subBug,4 bugs,5 loggedAI,6 loggedNo,7 subBugAI,8 subBugNo]

  function agg(rows){
    var A={backend:z(),frontend:z(),qa:z()}, oh=0, grand=0;
    for(var i=0;i<rows.length;i++){ var r=rows[i];
      for(var ar in AK){ var a=r[AK[ar]];
        if(a[2]||a[3]||a[0]||a[1]){ var g=A[ar]; g.tickets++; g.aEst+=a[0]; g.dlEst+=a[1]; g.logged+=a[2]; g.subBug+=a[3]; g.bugs+=a[4]; }
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
          g.loggedAI+=a[5]; g.loggedNo+=a[6]; g.subBugAI+=a[7]; g.subBugNo+=a[8];
          if(a[0]>=EST_MIN){ g.aE+=a[0]; g.aL+=a[2]; g.aB+=a[3]; }
          if(a[1]>=EST_MIN){ g.dE+=a[1]; g.dL+=a[2]; g.dB+=a[3]; } }
      }
      oh+=r.oh; grand+=r.be[2]+r.fe[2]+r.qa[2]+r.oh;
    }
    function psub(lg,sb){ var den=lg+sb; return den?Math.round(sb/den*100)+'%':'&ndash;'; }
    function pai(g){ var den=g.logged+g.subBug; return den?Math.round((g.loggedAI+g.subBugAI)/den*100)+'%':'&ndash;'; }
    var out='';
    ['backend','frontend','qa'].forEach(function(ar){ var g=A[ar]; if(!g.tickets) return;
      out+='<tr><td class="name">'+LABEL[ar]+'</td><td class="proj">'+projLabel+'</td><td class="r">'+g.tickets+'</td>'
        +'<td class="r">'+d(g.aEst)+'</td><td class="r">'+d(g.dlEst)+'</td><td class="r">'+d(g.logged+g.subBug)+'</td>'
        +'<td class="r">'+pl(g.logged,grand)+'</td><td class="r aih">'+pai(g)+'</td><td class="r">'+d(g.logged)+'</td>'
        +'<td class="r aih">'+d(g.loggedAI)+'</td><td class="r">'+d(g.loggedNo)+'</td>'
        +'<td class="r">'+d(g.subBug)+'</td><td class="r aih">'+d(g.subBugAI)+'</td><td class="r">'+d(g.subBugNo)+'</td><td class="r">'+psub(g.logged,g.subBug)+'</td>'
        +'<td class="r">'+g1(g.aE,g.aL+g.aB)+' <span class="sm">('+g.tickets+')</span></td>'
        +'<td class="r">'+g1(g.dE,g.dL+g.dB)+'</td><td class="r">'+g.bugs+'</td></tr>';
    });
    out+='<tr><td class="name">Overhead</td><td class="proj">'+projLabel+'</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td>'
      +'<td class="r">'+d(oh)+'</td><td class="r">'+pl(oh,grand)+'</td><td class="r">&ndash;</td><td class="r">'+d(oh)+'</td><td class="r">&ndash;</td><td class="r">&ndash;</td>'
      +'<td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td><td class="r">&ndash;</td></tr>';
    var tA=0,tD=0,tsub=0,tlog=0,tbugs=0,tlai=0,tlno=0,tais=0,tsbai=0,tsbno=0;
    ['backend','frontend','qa'].forEach(function(ar){ var g=A[ar]; tA+=g.aEst; tD+=g.dlEst; tsub+=g.subBug; tlog+=g.logged; tbugs+=g.bugs; tlai+=g.loggedAI; tlno+=g.loggedNo; tais+=g.loggedAI+g.subBugAI; tsbai+=g.subBugAI; tsbno+=g.subBugNo; });
    var totg = g1(tA, grand+tsub);   // Total row Arch gain = (A.Est - Total dev)/A.Est
    var tArea=tlog+tsub, totpai = tArea?Math.round(tais/tArea*100)+'%':'&ndash;';
    out+='<tr class="tot"><td class="name">Total</td><td class="proj">'+projLabel+'</td><td></td><td class="r">'+d(tA)+'</td><td class="r">'+d(tD)+'</td>'
      +'<td class="r">'+d(grand+tsub)+'</td><td class="r">'+(grand?'100%':'&ndash;')+'</td><td class="r aih">'+totpai+'</td><td class="r">'+d(grand)+'</td>'
      +'<td class="r aih">'+d(tlai)+'</td><td class="r">'+d(tlno)+'</td>'
      +'<td class="r">'+d(tsub)+'</td><td class="r aih">'+d(tsbai)+'</td><td class="r">'+d(tsbno)+'</td><td class="r">'+psub(tlog,tsub)+'</td>'
      +'<td class="r">'+totg+'</td><td></td><td class="r">'+tbugs+'</td></tr>';
    return out;
  }

  var MGCOLS=['backend','frontend','qa','overhead'];
  function monthGainBody(rows, tab){
    var bym={}, order=[];
    for(var i=0;i<rows.length;i++){ var m=rows[i].m; if(!(m in bym)){ bym[m]=[]; order.push(m); } bym[m].push(rows[i]); }
    order.sort(function(a,b){ return a<b?1:(a>b?-1:0); });
    var out='';
    for(var k=0;k<order.length;k++){ var m=order[k], mr=bym[m];
      var maest=0, mdev=0;   // Overall gain = (total Arch est - total dev)/total Arch est for the month
      for(var q=0;q<mr.length;q++){ var rr=mr[q];
        maest += rr.be[0]+rr.fe[0]+rr.qa[0];
        mdev += rr.be[2]+rr.fe[2]+rr.qa[2]+rr.oh + rr.be[3]+rr.fe[3]+rr.qa[3]; }
      var og=gp(maest, mdev), ogc=(og===null||Math.abs(og)>CAP)?'':(og>=0?'pos':'neg');
      out+='<tr><td class="name"><a href="#tot-'+tab+'-'+m+'">'+m+'</a></td><td class="r '+ogc+'">'+gs(og)+'</td>';
      for(var ci=0;ci<MGCOLS.length;ci++){ var ar=MGCOLS[ci];
        if(ar==='overhead'){ var oc=0, oh=0, mtot=mdev;   // overhead share of the month's total dev (incl. sub-bugs)
          for(var j=0;j<mr.length;j++){ if(mr[j].oh) oc++; oh+=mr[j].oh; }
          out+='<td class="r">'+(mtot?(Math.round(oh/mtot*100)+'% <span class="sm">('+oc+')</span>'):'&ndash;')+'</td>'; continue; }
        var est=0,log=0,bug=0,c=0,aih=0,devh=0;
        for(var j=0;j<mr.length;j++){ var a=mr[j][AK[ar]];
          if(a[2]||a[3]||a[0]||a[1]){ c++; aih+=a[5]+a[7]; devh+=a[2]+a[3]; if(a[0]>=EST_MIN){ est+=a[0]; log+=a[2]; bug+=a[3]; } } }
        if(!c){ out+='<td class="r">&ndash;</td>'; continue; }
        var g=gp(est,log+bug), cls=(g===null||Math.abs(g)>CAP)?'':(g>=0?'pos':'neg'), pai=devh?Math.round(aih/devh*100)+'%':'&ndash;';
        out+='<td class="r '+cls+'">'+gs(g)+' <span class="sm">('+c+' &middot; AI '+pai+')</span></td>';
      }
      out+='</tr>';
    }
    return out;
  }
  // Fix-version filter is GROUPED: fx is a base like "17" (=> 17.x) or "17.2" (=> 17.2.x); a ticket
  // matches when any of its fix versions equals that base or starts with it + "." (a non-numeric name
  // is its own exact option). fx==='all' matches everything.
  function vHit(v, fx){ return v===fx || v.indexOf(fx+'.')===0; }
  function fvMatch(r, fx){ if(fx==='all') return true; if(!r.fv) return false;
    for(var i=0;i<r.fv.length;i++){ if(vHit(r.fv[i], fx)) return true; } return false; }
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
      var tb=div.querySelector('tbody'); if(tb) tb.innerHTML=monthGainBody(ROWS.filter(function(r){ return F(r,tab); }), tab);
    });
    document.querySelectorAll('[data-grand]').forEach(function(p){
      var t=agg(ROWS.filter(function(r){ return F(r,p.getAttribute('data-tab')); })), tsub=t.A.backend.subBug+t.A.frontend.subBug+t.A.qa.subBug;
      p.innerHTML='<b>Total across all groups:</b> '+d(t.grand)+' d logged + '+d(tsub)+' d sub-bug = <b>'+d(t.grand+tsub)+' d</b> total dev <span class="sm">(1 d = '+DAY+' h)</span>';
    });
    document.querySelectorAll('tr[data-project]').forEach(function(tr){
      var okp=(proj==='all'||tr.getAttribute('data-project')===proj);
      var okf=(fx==='all'); if(!okf){ var vs=(tr.getAttribute('data-fixv')||'').split('|');
        for(var vi=0;vi<vs.length;vi++){ if(vs[vi] && vHit(vs[vi], fx)){ okf=true; break; } } }
      tr.style.display = (okp && okf) ? '' : 'none';
    });
    // per-month blocks (Totals-by-month and the per-ticket matrix): update the ticket count and hide
    // any month with no matching tickets under the active project/version filter.
    document.querySelectorAll('details[data-mon]').forEach(function(dt){
      var mt=dt.getAttribute('data-mtab'), mo=dt.getAttribute('data-mon');
      var n=ROWS.filter(function(r){ return F(r,mt,mo); }).length;
      var mc=dt.querySelector('summary .mc'); if(mc) mc.textContent=n;
      dt.style.display = n ? '' : 'none';
    });
    var TABS={'tab-all':'all','tab-us':'us','tab-usfinal':'usfinal','tab-bugfinal':'bugfinal','tab-other':'other'};
    for(var id in TABS){ var lab=document.querySelector('label[for="'+id+'"] .cnt'); if(!lab) continue;
      lab.textContent='('+ROWS.filter(function(r){ return F(r,TABS[id]); }).length+')';
    }
  }
  var ps=document.getElementById('projfilter'), fs=document.getElementById('fixvfilter');
  if(ps) ps.addEventListener('change', apply);
  if(fs) fs.addEventListener('change', apply);
  // clicking a month link (Arch-gain-by-month date, or a "N tickets" count) opens the target <details>
  document.addEventListener('click', function(ev){
    var t=ev.target, a=null;
    while(t && t!==document){ if(t.tagName==='A'){ a=t; break; } t=t.parentNode; }
    if(!a) return; var href=a.getAttribute('href')||'';
    if(href.indexOf('#tot-')!==0 && href.indexOf('#mtx-')!==0) return;
    var el=document.getElementById(href.slice(1)); var p=el;
    while(p){ if(p.tagName==='DETAILS') p.open=true; p=p.parentNode; }
  });
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
        P("> **Log AI d / Log non d** split each area's logged days into AI-assisted and non-AI streams; a worklog is "
          "AI-assisted when its author holds an AI-metrics record covering the issue (a US's record also covers its "
          "non-bug sub-tasks; a sub-bug uses its own record). **% AI** = (Log AI + Sub-bug AI) / (Logged + Sub-bug) for the area.\n")
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
                  f"{cell('backend')} | {cell('frontend')} | {cell('qa')} | {days(r['archprH']) or '–'} | {people} | {days(r['totalDev'])} |")
    md_text = "\n".join(md)
    if a.md: open(a.md, "w", encoding="utf-8").write(md_text)
    print(md_text)

    # ---------- CSV (full per-area matrix, flattened) ----------
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)) or ".", exist_ok=True)
        percol = ["Main dev", "A. Est d", "DL. Est d", "Total dev d", "Logged d", "Logged AI d", "Logged non-AI d",
                  "Sub-bug d", "Sub-bug AI d", "Sub-bug non-AI d",
                  "Arch gain (w bug)", "Arch gain (no bug)", "DL gain (w bug)", "DL gain (no bug)", "Sub-bugs"]
        header = ["Ticket", "Date", "Date source", "Month", "Type", "Title", "Status", "Final"]
        for ar in AREAS: header += [f"{AREA_LABEL[ar]} {c}" for c in percol]
        header += ["Overhead logged d", "Overhead %", "Overhead devs", "Total logged d"]
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh); w.writerow(header)
            for r in rows:
                row = [r["key"], r["date"], r.get("dateSrc") or "", r["month"], r["ttype"], r["title"], r["status"], "T" if r["final"] else ""]
                for ar in AREAS:
                    x = r["areas"][ar]
                    row += [x["main"], days(x["aEst"]), days(x["dlEst"]), days(x["totalDev"]),
                            days(x["logged"]), days(x["loggedAI"]), days(x["loggedNo"]),
                            days(x["subBug"]), days(x["subBugAI"]), days(x["subBugNo"]),
                            gain_cell(x["aEst"], x["logged"] + x["subBug"]), gain_cell(x["aEst"], x["logged"]),
                            gain_cell(x["dlEst"], x["logged"] + x["subBug"]), gain_cell(x["dlEst"], x["logged"]),
                            x["bugs"]]
                row += [days(r["archprH"]), (round(r["archprH"] / r["totalDev"] * 100) if r["totalDev"] else ""),
                        "; ".join(f"{n} {days(h)}d" for n, h in r["archprDevs"]), days(r["totalDev"])]
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
        vopts = version_options(fixvers)
        W('<div class="filterbar"><label><b>Project filter:</b> <select id="projfilter">'
          '<option value="all">All projects</option>'
          + "".join(f'<option value="{e(p)}">{e(p)}</option>' for p in projects)
          + '</select></label> &nbsp; <label><b>Fix version:</b> <select id="fixvfilter">'
          '<option value="all">All versions</option>'
          + "".join(f'<option value="{e(val)}">{e(lbl)}</option>' for val, lbl in vopts)
          + '</select></label> <span class="sm">versions are grouped (e.g. 17.x, 17.2.x) &mdash; selecting one matches every ticket in that release line; the per-ticket Fix ver column shows each ticket\'s full version. Totals, by-month counts and rows recompute live.</span></div>')
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
        def _av(a):   # [aEst, dlEst, logged, subBug, bugs, loggedAI, loggedNo, subBugAI, subBugNo]
            return [a["aEst"], a["dlEst"], a["logged"], a["subBug"], a["bugs"],
                    a["loggedAI"], a["loggedNo"], a["subBugAI"], a["subBugNo"]]
        rowdata = [{"k": r["key"], "p": r["project"], "fv": r.get("fixVersions") or [], "m": r["month"], "t": r["ttype"], "f": 1 if r["final"] else 0,
                    "oh": r["archprH"],
                    "be": _av(r["areas"]["backend"]), "fe": _av(r["areas"]["frontend"]), "qa": _av(r["areas"]["qa"])}
                   for r in rows]
        W('<script id="rowdata" type="application/json">' + _json.dumps(rowdata, separators=(",", ":")) + '</script>')
        W(PROJECT_FILTER_JS)
    W('<div class="foot"><p><b>Field guide.</b> Every time figure is in <b>days</b> (1 d = 8 h). A ticket is in scope when its '
      '<b>date</b> is in the window; all worklogs on it and its sub-issues then count (all-time). '
      'The <b>date</b> is when the ticket was <b>first sent to test</b> (its first transition into <i>Ready for Test</i> or <i>In Test</i>, from the Jira status history). '
      'A ticket that never went to test uses its first move into a post-dev status (<i>Need sync (after dev)</i>, <i>Ready for Sprint Review</i>, <i>Done</i>, &hellip;), else its resolution date, '
      'and one still in development uses its last worklog date; these fallbacks are marked <b>*</b> (hover the date for its source). '
      'Jira&rsquo;s <i>updated</i> date is never used, because any edit moves it. '
      'Two picklists at the top &mdash; <b>Project</b> and <b>Fix version</b> &mdash; live-filter every table and the per-ticket rows; <b>Fix version</b> is grouped by release line (e.g. <b>17.x</b>, <b>17.2.x</b>), and both filters also recompute the <b>by-month</b> tables and their ticket counts, hiding months with no matching tickets. The per-ticket <b>Fix ver</b> column always shows each ticket\'s complete version number.</p>'
      '<p><b>Totals by area</b> (first table; one row per area, then Overhead and Total): '
      '<b>Project</b> = the active project filter. '
      '<b>Tickets</b> = tickets the area worked. '
      '<b>A. Est d</b> = Architect estimate &mdash; strictly the per-area estimate custom field (back/front/QA), no fallback. '
      '<b>DL. Est d</b> = Dev-lead estimate &mdash; the ticket Original Estimate (a US sums that area\'s child sub-task estimates). '
      '<b>Total dev d</b> = Logged + Sub-bug. '
      '<b>%</b> = the area\'s (or Overhead\'s) share of total logged. '
      '<b>% AI</b> (right after it) = all AI-assisted hours &divide; the area\'s total dev = (Log AI + Sub-bug AI) &divide; (Logged + Sub-bug). '
      '<b>Logged d</b> = non-bug days booked by the area\'s developers, then split into two streams: '
      '<b>Log AI d</b> and <b>Log non d</b>. A worklog is <b>AI-assisted</b> when its author holds an AI-metrics record covering the issue it is booked on: a US\'s record covers the author\'s hours on the US <i>and its non-bug sub-tasks</i> (a US\'s dev work is booked on sub-tasks), while a <b>sub-bug</b> is judged on its own record only &mdash; so a US recorded for a developer shows their sub-task hours as AI, and a separately-recorded sub-bug shows its own hours as AI. '
      '<b>Sub-bug d</b> = days the area logged fixing the ticket\'s child Bug/Sub-bug sub-issues, split into <b>SB AI d</b> and <b>SB non d</b> (a sub-bug\'s hours are AI when it carries its own AI record). '
      '<b>% Sub-bug</b> = Sub-bug &divide; (Logged + Sub-bug) for the area. '
      '<b>Arch gain</b> and <b>DL gain</b> = the single <i>with-sub-bug</i> gain, each with the area\'s ticket count in ( ). Gain = (Est &minus; (Logged + Sub-bug)) / Est, computed over <b>only the tickets that carry that estimate</b>; green positive (under estimate), red negative, "-" when meaningless. '
      '<b>Sub-bugs</b> = count of child Bug/Sub-bug sub-issues the area worked. The <b>Overhead</b> row is Architect / PO / DevOps / Consultant / management time (no estimate); the <b>Total</b> row sums all areas + Overhead.</p>'
      '<p><b>Arch gain by month</b> (next table): rows are months; columns <b>Overall gain</b>, then Backend / Frontend / QA / Overhead. <b>Overall gain</b> = (total Arch estimate &minus; total dev) / total Arch estimate for the month &mdash; i.e. total dev &divide; total Arch est expressed as a gain, over every ticket (total dev = all logged incl. Overhead + all sub-bug). Each area cell is that area\'s with-sub-bug Architect gain, with its ticket count and its AI share of dev hours in ( ); the <b>Overhead</b> cell is overhead\'s share of that month\'s total logged.</p>'
      '<p><b>Per ticket</b> (matrix, grouped by month): '
      '<b>Ticket &middot; Date &middot; Type &middot; Fix ver</b> (Jira Fix Version/s, all shown) <b>&middot; Title &middot; Status &middot; F</b> (T = terminal status for the type). '
      '<b>Arch gain B/F/Q &middot; OH%</b> = each area\'s with-sub-bug Architect gain (B/F/Q) plus <b>OH%</b> = overhead\'s share of the ticket\'s total logged. '
      '<b>Logged+bug B/F/Q/OH</b> = total logged incl. sub-bugs per area and the overhead total. '
      '<b>Total logged d</b> (right before the Backend section) = the ticket\'s <b>full logged time</b> &mdash; all areas\' logged + all sub-bug + overhead (equals Jira\'s aggregate logged time when every worklog author is on the roster). '
      '<b>Overall arch gain</b> (right after it) = (accumulated Arch estimate &minus; Total logged) / accumulated Arch estimate &mdash; the whole ticket\'s Architect gain including overhead, i.e. total dev &divide; total A.Est as a gain. '
      'Then per area: <b>Main dev</b> (top contributor by dev-logged + own sub-bug hours), <b>A.Est / DL.Est / Tot dev</b> (days), '
      '<b>Logged (AI&middot;non)</b> and <b>Sub-bug (AI&middot;non)</b> each showing the AI stream (accent colour) then the non-AI stream in days, <b>Arch gain</b> and <b>DL gain</b> (shown <i>with / without</i> sub-bugs here), and <b>#SB</b> (sub-bug count). '
      'Closing columns: <b>Overhead d</b> (overhead time on the ticket), <b>Overhead %</b> (its share of the ticket\'s total logged incl. sub-bugs) and <b>Overhead people</b> (each contributor with their days). '
      'Generated by <code>/oc-reports:oc-time-report</code>.</p></div>')
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
.aih {{ color:var(--accent); font-weight:600; }}
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

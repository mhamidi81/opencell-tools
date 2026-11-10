#!/usr/bin/env python3
"""AI-usage report. AI metrics grouped by record domain. Estimate hours come from per-area
Architect/QA estimate custom fields on the Story (days x8), else the ticket's own estimate
(sub-issue estimates are never summed). Sub-bug counts and bug-logged hours come from Bug/Sub-bug
sub-issues, per area. Aggregate gains use only the rows that carry the matching estimate. Logged hours are
the record author's own Tempo hours across the whole US (parent + its non-bug sub-tasks; sub-tasks/sub-bugs
carrying their own AI record are separate rows, excluded from the parent rollup) -> Jira worklog -> ticket total.
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
def days(h): return round((h or 0) / DAY_HOURS, 1)   # Totals-by-area shown in days (1 d = 8 h)
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

TYPE_MAP = {"story": "US", "bug": "Bug", "sub-bug": "Sub-bug", "enabler": "Enabler"}
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

def bug_has_time(c, tempo):
    """A sub-bug 'exists' only once time is logged on it (any author's Tempo worklog, else its own
    timespent). A sub-bug with zero logged time is not counted (matches the time report)."""
    tw = tempo.get(str(c.get("id"))) or {}
    if any((v or 0) > 0 for v in tw.values()): return True
    return hours((c.get("fields") or {}).get("timespent")) > 0

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
    p_bugs = {}; p_dl = {}; p_has_sub = {}; p_foreign_ct = {}; p_foreign_hr = {}; p_sub_nodes = {}
    included = {}   # recorded sub-bug key -> the parent US key whose Sub-bug h already counts its hours
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw_bugs = {ar: [] for ar in AREAS}; dl_by_area = {ar: 0.0 for ar in AREAS}
        pa = area_of(pf); saw_sub = False; rec_areas = record_domains(pf)
        sub_nodes = []   # non-bug sub-tasks WITHOUT their own AI record (their logged hours roll up to the US)
        for c in ch_by_parent.get(key, []):
            cf = c.get("fields", {}) or {}
            if is_bug(cf):
                # bugs: attributed by their OWN component/title only (no parent inheritance). A sub-bug
                # counts on its parent US once it has logged time (bug_has_time). If it also carries its
                # own AI record it still counts here (visibility), but its HOURS are kept on its own row
                # (bug_logged_h skips recorded sub-bugs) so nothing is double-counted (Case 2).
                bar = area_of(cf)
                if bar and bug_has_time(c, tempo): raw_bugs[bar].append(c)
            else:
                ar = area_of(cf) or pa         # non-bug sub-tasks still inherit the parent area for the DL estimate
                saw_sub = True
                if ar: dl_by_area[ar] += hours(cf.get("timeoriginalestimate"))
                # a sub-task carrying its own AI record is its own report row -> don't also roll it up here
                if not recover_json(cf.get("customfield_10745")): sub_nodes.append(c)
        # Only own-area sub-bugs drive an area's count & Sub-bug h. A sub-bug whose area has no
        # AI record on the ticket is NOT mixed into another area's numbers (this report measures
        # per-area AI impact, and each area is a different developer) — it is surfaced only as an
        # annotation "(front +1 7.8h)" on a record area's cell, carrying its count and total hours.
        bugs_by_area = {ar: list(raw_bugs[ar]) if ar in rec_areas else [] for ar in AREAS}
        for ar in AREAS:
            if ar in rec_areas:
                for b in raw_bugs[ar]:
                    bk = b.get("key")
                    if bk and recover_json((b.get("fields") or {}).get("customfield_10745")): included.setdefault(bk, key)
        fct = {ar: {} for ar in AREAS}; fhr = {ar: {} for ar in AREAS}
        fallback = pa if pa in rec_areas else (sorted(rec_areas)[0] if rec_areas else None)
        if fallback:
            for ar in AREAS:
                if ar in rec_areas or not raw_bugs[ar]: continue
                fct[fallback][ar] = fct[fallback].get(ar, 0) + len(raw_bugs[ar])
                fhr[fallback][ar] = round(fhr[fallback].get(ar, 0.0)
                    + sum(hours((b.get("fields") or {}).get("timespent")) for b in raw_bugs[ar]), 1)
        p_bugs[key] = bugs_by_area; p_dl[key] = dl_by_area; p_has_sub[key] = saw_sub
        p_foreign_ct[key] = fct; p_foreign_hr[key] = fhr; p_sub_nodes[key] = sub_nodes

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
            # Logged = the author's own Tempo hours across the US: the parent PLUS its non-bug sub-tasks
            # (a US's dev work is booked on its sub-tasks). Fall back to the parent Jira worklog / total
            # timespent only when Tempo has nothing for this author anywhere on the US.
            lg = 0.0; seen = False
            if acc in tw: lg += hours(tw.get(acc)); seen = True
            for c in p_sub_nodes[key]:
                ctw = tempo.get(str(c.get("id")), {})
                if acc in ctw: lg += hours(ctw.get(acc)); seen = True
            if seen: logged = round(lg, 1)
            elif acc in wl: logged = hours(wl.get(acc))
            else: logged = parent_logged
            rows.append({"area": domain, "at": at, "acc": acc, "name": name, "key": key,
                         "ttype": ttype, "summary": summary, "status": status, "final": final,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "aEst": round(a_est, 1), "dlEst": round(dl_est, 1),
                         "logged": round(logged, 1), "bugLogged": bug_logged,
                         "bugs": len(bug_nodes), "bugsForeign": foreign_ct, "bugsForeignH": foreign_hr,
                         "partOf": included.get(key)})   # set => hours already counted in that parent US
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
    agg_rows = [r for r in rows if not r.get("partOf")]   # aggregates exclude sub-bugs already counted in their US

    # ---- Totals by area (shown first) ----
    areas = {ar: {"contrib": [], "retain": [], "rows": [], **{k: 0 for k in SUM}} for ar in AREAS}
    for r in agg_rows:
        g = areas[r["area"]]; g["contrib"].append(r["contrib"]); g["retain"].append(r["retain"])
        g["rows"].append(r)
        for k in SUM: g[k] += r[k]
    P("## Totals by area (sum of detail rows; hours shown in days, 1 d = 8 h)\n")
    P("| Area | Rows | AI Contrib | Retain | Review phase | U.tests +/~ | P.tests | Requests | A. Est d | DL. Est d | Total dev d | Logged d | Sub-bug d | Arch gain | DL gain | Sub-bugs |")
    P("|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for ar in AREAS:
        g = areas[ar]
        if not g["contrib"]: continue
        P(f"| {ar.capitalize()} | {len(g['contrib'])} | {avg(g['contrib'])}% | {avg(g['retain'])}% | {avg([r['rework'] for r in g['rows']])}% | "
          f"{g['utAdd']}/{g['utMod']} | {g['pmTests']} | {g['turns']} | {days(g['aEst'])} | {days(g['dlEst'])} | "
          f"{days(g['logged'] + g['bugLogged'])} | {days(g['logged'])} | {days(g['bugLogged'])} | {gain_two(*gain_basis(g['rows'], 'aEst'))} | "
          f"{gain_two(*gain_basis(g['rows'], 'dlEst'))} | {bugs_label(g['bugs'], sum_foreign(g['rows']), sum_foreign_h(g['rows']))} |")

    # ---- Summary by user ----
    users = {}
    for r in agg_rows:
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
    users_all = {}   # Detail shows every record (incl. sub-bugs noted "part of US"), so use the full row set
    for r in rows:
        ua = users_all.setdefault(r["acc"], {"name": r["name"], "areas": set()})
        ua["name"] = r["name"]; ua["areas"].add(r["area"])
    for acc, u in sorted(users_all.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
        P(f"\n### {u['name']}\n")
        P("| Ticket | Date | Type | Area | Summary | Status | Final | AI Contrib | Retain | Review phase | U.tests +/~ | P.tests | Requests | A. Est h | DL. Est h | Total dev h | Logged h | Sub-bug h | Arch gain | DL gain | Sub-bugs |")
        P("|---|---|---|---|---|---|:--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for r in sorted(by_user[acc], key=lambda x: (x["at"], x["key"])):
            c = r['contrib']
            cc = f"**{c}%**" if isinstance(c, (int, float)) and c < 60 else f"{c}%"  # <60% flagged (red in HTML)
            summ = f"{r['summary']} _(part of {r['partOf']})_" if r.get("partOf") else r['summary']
            P(f"| [{r['key']}]({JIRA_BROWSE}{r['key']}) | {r['at']} | {r['ttype']} | {r['area']} | {summ} | {r['status']} | {'T' if r['final'] else ''} | {cc} | {r['retain']}% | {r['rework']}% | "
              f"{r['utAdd']}/{r['utMod']} | {r['pmTests']} | {r['turns']} | {r['aEst']} | {r['dlEst']} | {round(r['logged'] + r['bugLogged'],1)} | {r['logged']} | "
              f"{r['bugLogged']} | {gain_two(r['aEst'], r['logged'], r['bugLogged'])} | {gain_two(r['dlEst'], r['logged'], r['bugLogged'])} | {bugs_label(r['bugs'], r['bugsForeign'], r['bugsForeignH'])} |")
    print("\n".join(out))

if __name__ == "__main__":
    main()

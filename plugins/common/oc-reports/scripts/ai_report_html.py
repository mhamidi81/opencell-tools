#!/usr/bin/env python3
"""Render the AI-usage report as a self-contained, styled HTML file. AI metrics grouped by record
domain. Estimate hours from per-area Architect/QA estimate custom fields on the Story (days x8),
else the ticket's own estimate. Sub-bug counts & bug-logged hours from Bug/Sub-bug sub-issues, per area.
Aggregate gains use only the rows carrying that estimate; ticket keys link to Jira.
Logged hours = the record author's own Tempo hours across the whole US (parent + its non-bug sub-tasks;
sub-tasks/sub-bugs with their own AI record are separate rows, excluded from the parent rollup) -> Jira -> ticket total.
Totals = sum of detail rows."""
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
        bf = b.get("fields", {}) or {}
        bid = str(b.get("id"))
        tw = tempo.get(bid, {})
        total += hours(tw.get(acc)) if acc in tw else hours(bf.get("timespent"))
    return round(total, 1)

def bug_has_time(c, tempo):
    """A sub-bug 'exists' only once time is logged on it (any author's Tempo worklog, else its own
    timespent). A sub-bug with zero logged time is not counted (matches the time report)."""
    tw = tempo.get(str(c.get("id"))) or {}
    if any((v or 0) > 0 for v in tw.values()): return True
    return hours((c.get("fields") or {}).get("timespent")) > 0

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
def days(h): return round((h or 0) / DAY_HOURS, 1)   # Totals-by-area shown in days (1 d = 8 h)

def build_rows(parents, children, tempo, since, until):
    ch_by_parent = defaultdict(list)
    for c in children:
        cf = c.get("fields", {}) or {}
        pk = (cf.get("parent") or {}).get("key")
        if pk: ch_by_parent[pk].append(c)
    p_bugs = {}; p_dl = {}; p_has_sub = {}; p_foreign_ct = {}; p_foreign_hr = {}; p_sub_nodes = {}
    included = {}   # recorded sub-bug key -> the parent US key whose Sub-bug h already counts its hours
    for p in parents:
        key = p.get("key"); pf = p.get("fields", {}) or {}
        raw_bugs = {ar: [] for ar in AREAS}; dl_by_area = {ar: 0.0 for ar in AREAS}
        pa = area_of(pf); saw_sub = False; rec_areas = record_domains(pf)
        sub_nodes = []   # non-bug sub-tasks WITHOUT their own AI record (their logged hours roll up to the US)
        # Only the ticket's OWN child sub-issues (never issue links): Bug/Sub-bug -> count + Sub-bug h;
        # non-bug sub-tasks -> Dev-lead estimate (sub-bug estimates excluded).
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
        # a recorded sub-bug whose hours are folded into this US (its area has a record here) is marked
        # "included in <US>": it still gets its own row (own AI metrics), noted + excluded from aggregates.
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
                         "project": str(key).split("-")[0],
                         "ttype": ttype, "summary": summary, "status": status, "final": final,
                         "contrib": num(rec.get("contrib")), "retain": num(rec.get("retain")), "rework": num(rec.get("rework")),
                         "utAdd": num(rec.get("utAdd")), "utMod": num(rec.get("utMod")), "pmTests": num(rec.get("pmTests")),
                         "turns": num(rec.get("subReq") if rec.get("subReq") is not None else rec.get("turns")),
                         "aEst": round(a_est, 1), "dlEst": round(dl_est, 1), "logged": round(logged, 1),
                         "bugLogged": bug_logged_h(bug_nodes, acc, tempo),   # own-area only
                         "bugs": len(bug_nodes), "bugsForeign": foreign_ct, "bugsForeignH": foreign_hr,
                         "partOf": included.get(key)})   # set => this row's hours are already counted in that parent US
    return rows

CSV_COLS = [
    ("key", "Ticket"), ("at", "Date"), ("ttype", "Type"), ("area", "Area"),
    ("name", "User"), ("summary", "Summary"), ("status", "Status"), ("finalTxt", "Final status"),
    ("contrib", "AI Contrib %"), ("retain", "Retain %"), ("rework", "Review phase %"),
    ("utAdd", "U.tests added"), ("utMod", "U.tests modified"), ("pmTests", "P.tests"),
    ("turns", "Requests"), ("aEst", "A. Est d"), ("dlEst", "DL. Est d"),
    ("totalDev", "Total dev d"), ("logged", "Logged d"), ("bugLogged", "Sub-bug d"),
    ("gainBug", "Arch gain % (with bugs)"), ("gain", "Arch gain % (no bugs)"),
    ("gainDlBug", "DL gain % (with bugs)"), ("gainDl", "DL gain % (no bugs)"),
    ("bugs", "Sub-bugs"), ("bugsForeignTxt", "Sub-bugs (other areas)"),
    ("partOfTxt", "Part of US (hours counted there)"),
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
            r["partOfTxt"] = r.get("partOf") or ""
            r["totalDev"] = round(r["logged"] + r["bugLogged"], 1)
            r["gain"] = gain_cell(r["aEst"], r["logged"])            # gains are ratios (unit-independent)
            r["gainBug"] = gain_cell(r["aEst"], r["logged"] + r["bugLogged"])
            r["gainDl"] = gain_cell(r["dlEst"], r["logged"])
            r["gainDlBug"] = gain_cell(r["dlEst"], r["logged"] + r["bugLogged"])
            for k in ("aEst", "dlEst", "logged", "bugLogged", "totalDev"): r[k] = days(r[k])  # hour columns -> days
            w.writerow(["" if r.get(k) is None else r.get(k) for k, _ in CSV_COLS])
    print(f"Wrote {path} ({len(rows)} rows)")

AI_FILTER_JS = r"""<script>
(function(){
  var sel=document.getElementById('projfilter'), bar=document.getElementById('aitabbar');
  var cur={scope:'all', tab:'all'};
  function apply(){
    var ps=document.querySelectorAll('section.panel');
    for(var i=0;i<ps.length;i++){ var p=ps[i];
      p.style.display=(p.getAttribute('data-scope')===cur.scope && p.getAttribute('data-tab')===cur.tab)?'block':'none';
    }
    if(bar){ var bs=bar.querySelectorAll('button');
      for(var j=0;j<bs.length;j++){ var b=bs[j], t=b.getAttribute('data-tab');
        if(t===cur.tab) b.classList.add('active'); else b.classList.remove('active');
        var pnl=document.querySelector('section.panel[data-scope="'+cur.scope+'"][data-tab="'+t+'"]');
        var c=b.querySelector('.cnt'); if(c) c.textContent='('+(pnl?pnl.getAttribute('data-count'):'0')+')';
      }
    }
  }
  if(bar) bar.addEventListener('click', function(ev){ var b=ev.target.closest('button'); if(!b) return; cur.tab=b.getAttribute('data-tab'); apply(); });
  if(sel) sel.addEventListener('change', function(){ cur.scope=this.value; apply(); });
  // in-page links (Summary name -> By-user->month; month -> Detail) open the target <details>
  document.addEventListener('click', function(ev){
    var t=ev.target, a=null; while(t && t!==document){ if(t.tagName==='A'){ a=t; break; } t=t.parentNode; }
    if(!a) return; var href=a.getAttribute('href')||''; if(href.charAt(0)!=='#' || href.length<2) return;
    var el=document.getElementById(href.slice(1)); var p=el;
    while(p){ if(p.tagName==='DETAILS') p.open=true; p=p.parentNode; }
  });
  apply();
})();
</script>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--children"); ap.add_argument("--tempo")
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--out", required=True)
    ap.add_argument("--csv")   # optional: also write the ticket-detail rows as CSV
    ap.add_argument("--project", default="INTRD,MACRD")
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
        AH = ["Rows","Avg AI contrib","Avg retain","Avg review phase","U.tests +/~","P.tests","Requests","A. Est d","DL. Est d","Total dev d","Logged d","Sub-bug d","Arch gain","DL gain","Sub-bugs"]
        HEAD = ["AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est d","DL. Est d","Total dev d","Logged d","Sub-bug d","Arch gain","DL gain","Sub-bugs"]
        DHEAD = ["Ticket","Date","Type","Area","Summary","Status","Final","AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est d","DL. Est d","Total dev d","Logged d","Sub-bug d","Arch gain","DL gain","Sub-bugs"]
        _left = ("Ticket", "Date", "Type", "Area", "Summary", "Status"); _cent = ("Final",)

        # period grouping keys off the AI record's `at` date
        def month_of(at): return (at or "")[:7] or "no-date"

        def totals_area_html(rs):
            rs = [r for r in rs if not r.get("partOf")]   # recorded sub-bugs counted in their US are not re-summed
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
                  f'<td class="r">{g["turns"]}</td><td class="r">{days(g["aEst"])}</td><td class="r">{days(g["dlEst"])}</td>'
                  f'<td class="r">{days(g["logged"] + g["bugLogged"])}</td><td class="r">{days(g["logged"])}</td><td class="r">{days(g["bugLogged"])}</td>'
                  f'<td class="r {gain_cls(gp)}">{gain_two(*ba)}</td>'
                  f'<td class="r {gain_cls(gpd)}">{gain_two(*bd)}</td><td class="r">{e(bugs_label(g["bugs"], sum_foreign(g["rows"]), sum_foreign_h(g["rows"])))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        def summary_user_html(rs, pfx=""):
            rs = [r for r in rs if not r.get("partOf")]   # recorded sub-bugs counted in their US are not re-summed
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
                namecell = f'<a href="#{pfx}-um-{e(_acc)}">{e(u["name"])}</a>' if pfx else e(u["name"])
                h.append(f'<tr><td class="name">{namecell}</td><td>{e("/".join(sorted(u["areas"])))}</td>'
                  f'<td class="r">{len(u["tickets"])}</td>'
                  f'<td class="r{" low" if avg(u["contrib"]) < 60 else ""}">{pct(avg(u["contrib"]))}</td><td class="r">{pct(avg(u["retain"]))}</td>'
                  f'<td class="r">{pct(avg(u["rework"]))}</td><td class="r">{u["utAdd"]}/{u["utMod"]}</td>'
                  f'<td class="r">{u["pmTests"]}</td><td class="r">{u["turns"]}</td>'
                  f'<td class="r">{days(u["aEst"])}</td><td class="r">{days(u["dlEst"])}</td>'
                  f'<td class="r">{days(u["logged"] + u["bugLogged"])}</td><td class="r">{days(u["logged"])}</td>'
                  f'<td class="r">{days(u["bugLogged"])}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_two(*ba)}</td>'
                  f'<td class="r {gain_cls(gd)}">{gain_two(*bd)}</td><td class="r">{e(bugs_label(u["bugs"], sum_foreign(u["rows"]), sum_foreign_h(u["rows"])))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        MHEAD = ["Month","Tickets","AI Contrib","Retain","Review phase","U.tests +/~","P.tests","Requests","A. Est d","DL. Est d","Total dev d","Logged d","Sub-bug d","Arch gain","DL gain","Sub-bugs"]
        def user_month_html(user_rows, pfx="", acc=""):
            """One row per month for a single user (used under the per-user Summary groups)."""
            user_rows = [r for r in user_rows if not r.get("partOf")]   # exclude sub-bugs already counted in their US
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
                mcell = f'<a href="#{pfx}-det-{e(acc)}-{e(m)}">{e(m)}</a>' if pfx else e(m)
                h.append(f'<tr><td class="name">{mcell}</td><td class="r">{len({r["key"] for r in rs})}</td>'
                  f'<td class="r{" low" if avg(contrib) < 60 else ""}">{pct(avg(contrib))}</td>'
                  f'<td class="r">{pct(avg(retain))}</td><td class="r">{pct(avg(rework))}</td>'
                  f'<td class="r">{agg["utAdd"]}/{agg["utMod"]}</td><td class="r">{agg["pmTests"]}</td><td class="r">{agg["turns"]}</td>'
                  f'<td class="r">{days(agg["aEst"])}</td><td class="r">{days(agg["dlEst"])}</td>'
                  f'<td class="r">{days(agg["logged"] + agg["bugLogged"])}</td><td class="r">{days(agg["logged"])}</td>'
                  f'<td class="r">{days(agg["bugLogged"])}</td>'
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
                note = f' <span class="cnt">(part of {e(r["partOf"])})</span>' if r.get("partOf") else ""
                h.append(f'<tr><td class="key"><a href="{JIRA_BROWSE}{e(r["key"])}" target="_blank" rel="noopener">{e(r["key"])}</a></td><td>{e(r["at"])}</td><td>{e(r["ttype"])}</td><td>{e(r["area"])}</td>'
                  f'<td>{e(r["summary"])}{note}</td><td>{e(r["status"])}</td><td class="c">{finalcell}</td>'
                  f'<td class="r{" low" if low else ""}">{r["contrib"]}%</td><td class="r">{r["retain"]}%</td><td class="r">{r["rework"]}%</td>'
                  f'<td class="r">{r["utAdd"]}/{r["utMod"]}</td><td class="r">{r["pmTests"]}</td>'
                  f'<td class="r">{r["turns"]}</td><td class="r">{days(r["aEst"])}</td><td class="r">{days(r["dlEst"])}</td>'
                  f'<td class="r">{days(r["logged"] + r["bugLogged"])}</td><td class="r">{days(r["logged"])}</td>'
                  f'<td class="r">{days(r["bugLogged"])}</td>'
                  f'<td class="r {gain_cls(g)}">{gain_two(r["aEst"], r["logged"], r["bugLogged"])}</td>'
                  f'<td class="r {gain_cls(gd)}">{gain_two(r["dlEst"], r["logged"], r["bugLogged"])}</td><td class="r">{e(bugs_label(r["bugs"], r["bugsForeign"], r["bugsForeignH"]))}</td></tr>')
            h.append("</tbody></table></div>")
            return "".join(h)

        def render_body(rs, pfx=""):
            """Full report body (KPI cards + Totals + Summary + Detail) for a subset of rows."""
            if not rs:
                return '<p class="empty">No records of this ticket type in this window.</p>'
            # Aggregate sections exclude recorded sub-bugs already counted in their US (partOf); the Detail
            # section shows every record (those sub-bugs appear with a "part of <US>" note).
            agg_rs = [r for r in rs if not r.get("partOf")]
            users_x = {}
            for r in agg_rs:
                u = users_x.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set(),
                     "contrib": [], "retain": [], "rework": [], **{k: 0 for k in SUM}})
                u["name"] = r["name"]; u["areas"].add(r["area"]); u["tickets"].add(r["key"])
                u["contrib"].append(r["contrib"]); u["retain"].append(r["retain"]); u["rework"].append(r["rework"])
                for k in SUM: u[k] += r[k]
            users_all = {}   # for the Detail section (every record, incl. sub-bugs noted "part of US")
            for r in rs:
                ua = users_all.setdefault(r["acc"], {"name": r["name"], "areas": set(), "tickets": set()})
                ua["name"] = r["name"]; ua["areas"].add(r["area"]); ua["tickets"].add(r["key"])
            by_user_x = defaultdict(list)
            for r in rs: by_user_x[r["acc"]].append(r)
            latest_month = max((month_of(r["at"]) for r in rs), default=None)

            def month_details(section_rows, render_fn, idpfx=None):
                out = []
                for m in sorted({month_of(r["at"]) for r in section_rows}, reverse=True):
                    mr = [r for r in section_rows if month_of(r["at"]) == m]
                    op = " open" if m == latest_month else ""
                    idattr = f' id="{idpfx}-{e(m)}"' if idpfx else ''
                    out.append(f'<details{idattr}{op}><summary>{e(m)} <span class="cnt">({len(mr)} record(s))</span></summary>')
                    out.append(render_fn(mr)); out.append('</details>')
                return "".join(out)

            h = []; w = h.append
            allc = [r["contrib"] for r in agg_rs]; allr = [r["retain"] for r in agg_rs]
            tot_aest = sum(u["aEst"] for u in users_x.values()); tot_dlest = sum(u["dlEst"] for u in users_x.values())
            tot_log = sum(u["logged"] for u in users_x.values()); tot_bug = sum(u["bugLogged"] for u in users_x.values())
            card_a = gain_basis(agg_rs, "aEst"); card_d = gain_basis(agg_rs, "dlEst")  # gains skip unestimated + partOf rows
            w('<div class="cards">')
            for label, val in [("Avg contribution", pct(avg(allc))), ("Avg retention", pct(avg(allr))),
                               ("Requests", sum(u["turns"] for u in users_x.values())),
                               ("Est d (A / DL)", f"{days(tot_aest)} / {days(tot_dlest)}"),
                               ("Logged d (w/o / w bugs)", f"{days(tot_log)} / {days(tot_log+tot_bug)}"),
                               ("Arch gain (w / w/o bugs)", gain_two(*card_a)),
                               ("DL gain (w / w/o bugs)", gain_two(*card_d))]:
                w(f'<div class="card"><div class="v">{e(val)}</div><div class="l">{e(label)}</div></div>')
            w('</div>')
            # Totals by area (overall, then expandable by month)
            w("<h2>Totals by area <span class=\"sub\">(sum of detail rows; hours in days, 1 d = 8 h)</span></h2>")
            w(totals_area_html(rs)); w('<p class="bm">By month</p>'); w(month_details(agg_rs, totals_area_html))
            # Summary by user (overall, then expandable per user -> month)
            w("<h2>Summary by user</h2>")
            w(summary_user_html(rs, pfx)); w('<p class="bm">By user &rarr; month</p>')
            for acc, u in sorted(users_x.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
                ur = by_user_x[acc]; ac = avg([r["contrib"] for r in ur])
                w(f'<details id="{pfx}-um-{e(acc)}"><summary>{e(u["name"])} '
                  f'<span class="cnt">({len(u["tickets"])} ticket(s), avg contrib {pct(ac)})</span></summary>')
                w(user_month_html(ur, pfx, acc)); w('</details>')
            # Detail per user (grouped by month) — every record, incl. sub-bugs noted "part of <US>"
            w("<h2>Detail per user</h2>")
            for acc, u in sorted(users_all.items(), key=lambda kv: ("/".join(sorted(kv[1]["areas"])), kv[1]["name"].lower())):
                w(f'<h3 id="{pfx}-user-{e(acc)}">{e(u["name"])}</h3>'); w(month_details(by_user_x[acc], detail_table_html, f"{pfx}-det-{e(acc)}"))
            return "".join(h)

        # Ticket-type tabs (JS) + project-scope filter (JS). Each project scope gets its own set of
        # 5 fully server-rendered tab panels (correct aggregates per project); JS shows one at a time.
        def subsets(rs):
            return [("all", "All", rs),
                    ("us", "User Stories (All)", [r for r in rs if r["ttype"] == "US"]),
                    ("usfinal", "User Stories (Final)", [r for r in rs if r["ttype"] == "US" and r["final"]]),
                    ("bugfinal", "Bugs (final)", [r for r in rs if r["ttype"] == "Bug" and r["final"]]),
                    ("other", "Bugs and others", [r for r in rs if r["ttype"] != "US"])]
        projects = sorted({r["project"] for r in rows})
        W('<div class="filterbar"><label><b>Project filter:</b> <select id="projfilter">'
          '<option value="all">All projects</option>'
          + "".join(f'<option value="{e(p)}">{e(p)}</option>' for p in projects)
          + '</select></label> <span class="sub">filters the whole report by Jira project.</span></div>')
        W('<div class="tabbar" id="aitabbar">'
          + "".join(f'<button type="button" data-tab="{tk}"{" class=\"active\"" if tk == "all" else ""}>{e(lbl)} <span class="cnt"></span></button>'
                    for tk, lbl, _ in subsets(rows))
          + '</div>')
        for scope, srows in [("all", rows)] + [(p, [r for r in rows if r["project"] == p]) for p in projects]:
            for tk, lbl, sub in subsets(srows):
                W(f'<section class="panel" data-scope="{e(scope)}" data-tab="{tk}" data-count="{len(sub)}">'
                  f'{render_body(sub, scope + "-" + tk)}</section>')
        W(AI_FILTER_JS)
    W('<p class="foot">AI metrics are recorded per developer per ticket by <code>/oc-be-calculate-ai-use</code> and grouped here by record domain (backend / frontend / QA). '
      '<b>AI Contrib</b> = share of the delivered work that came from AI (Claude Code); '
      '<b>Retain</b> = share of the AI\'s output that survived to the final code (higher is better); '
      '<b>Review phase</b> = of the AI-authored lines, the share written during the review-and-fix phase (main context, after the reviewer) rather than the sub-agent\'s first pass (from <code>reviewer_rework_pct</code>) &mdash; a timing split, <i>not</i> a redo/discard rate, so it is unrelated to Contrib&minus;Retain; '
      '<b>U.tests +/~</b> = unit tests added / modified; '
      '<b>P.tests</b> = Postman assertion test cases exercised; '
      '<b>Requests</b> = substantive developer&harr;AI interactions in the session. '
      'The area aggregates show the average AI Contrib / Retain / Review phase and the summed counts. '
      '<b>A. Est d</b> (Architect) per area from the estimate '
      'custom fields (days &times;8), else the ticket estimate; <b>DL. Est d</b> (Dev-lead) from the ticket estimation '
      'field &mdash; a User Story sums its child sub-task estimates per area (sub-bugs excluded), a Bug/Enabler uses its '
      'own estimate. <b>Sub-bugs</b> = count of the area\'s <b>own</b> child Bug/Sub-bug sub-issues (by their component) <b>that have logged time</b> (a sub-bug with no logged hours does not count), with <b>Sub-bug d</b> (days logged on them). '
      'This report measures per-area AI impact (a different developer per area), so a cross-area sub-bug is <b>not</b> mixed into another area\'s numbers: '
      'a sub-bug whose component is a different area (when that area has no AI record on the ticket) is shown only as an annotation, e.g. '
      '<b>2 (front +1 7.8h)</b> &mdash; 2 own-area sub-bugs, plus 1 frontend sub-bug totalling 7.8h that is counted under frontend, not here. '
      '<b>Logged d</b> = days booked on the ticket (1 d = 8 h) per user (Tempo per-user &rarr; Jira worklog &rarr; ticket total); '
      '<b>Total dev d</b> = Logged d + Sub-bug d (all development effort). <b>Arch gain</b> = (A.Est&minus;Logged)/A.Est and '
      '<b>DL gain</b> = (DL.Est&minus;Logged)/DL.Est, each shown <b>with / without</b> bug hours; a dash (&mdash;) marks a '
      'meaningless gain &mdash; a placeholder estimate (&le;0.5h), no logged time, or a magnitude beyond &plusmn;1000%. '
      'In every aggregate row (area, user, month, KPI card) the gain is computed over <b>only the tickets that carry '
      'that estimate</b> &mdash; an unestimated ticket contributes neither its estimate nor its logged hours &mdash; so '
      'the gain can be based on fewer tickets than the Est d / Logged d columns beside it. Ticket keys link to Jira. '
      'In the detail tables, <b>Status</b> is the ticket\'s Jira status and <b>Final</b> (T) marks a terminal status for its type '
      '(Bug: Done/Invalid; US: Ready for Sprint review / Need documentation / Ready for release / Released; others: Done); '
      '<b>AI Contrib</b> below 60% is shown in <span class="low">red</span>. '
      'Generated by <code>/oc-reports:oc-ai-report</code>.</p>')
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
.filterbar {{ margin:1.25rem 0 .25rem; }}
.filterbar select {{ padding:.3rem .55rem; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--fg); font:inherit; }}
.filterbar .sub {{ color:var(--muted); font-size:.8rem; }}
.tabbar {{ display:flex; flex-wrap:wrap; gap:.25rem; border-bottom:2px solid var(--line); margin:.5rem 0 0; }}
.tabbar button {{ padding:.5rem 1rem; cursor:pointer; color:var(--muted); font-weight:600; font:inherit;
  background:none; border:1px solid transparent; border-bottom:none; border-radius:8px 8px 0 0; margin-bottom:-2px; }}
.tabbar button .cnt {{ font-weight:400; }}
.tabbar button.active {{ color:var(--fg); background:var(--card); border-color:var(--line); border-bottom:2px solid var(--card); }}
.panel {{ display:none; padding-top:.5rem; }}
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

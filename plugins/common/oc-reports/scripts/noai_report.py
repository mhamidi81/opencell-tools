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
DATE_SRC = {"test": "first sent to test (Ready for Test / In Test)",
            "postdev": "first moved to a post-dev status (never sent to test)",
            "resolved": "resolution date (no test / post-dev transition)",
            "worklog": "last worklog (still in development)"}
def ticket_date(f, wlast=""):
    """(YYYY-MM-DD, source): FIRST sent to test (testDate from the status changelog, see
    jira_fetch_dates.py), else the last worklog date. Never `updated` (any edit moves it)."""
    d = (f.get("testDate") or "")[:10]
    if d: return d, f.get("dateSrc") or "test"
    if "dateSrc" not in f and f.get("resolutiondate"):     # issues.json from an older fetch
        return f["resolutiondate"][:10], "resolved"
    return (wlast or "")[:10], ("worklog" if wlast else "")
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

def build_units(ns, tempo, devmap, cutoff, wdates=None):
    by_id = {str(n.get("id")): n for n in ns}
    by_key = {n.get("key"): n for n in ns}

    # Accumulate hours per OWNER x area, split AI/non-AI. Owner = the ticket the hours belong to:
    #   non-bug sub-task -> its parent US (rolled up); sub-bug or any non-sub-task issue -> itself.
    owners = defaultdict(lambda: {ar: {"ai": 0.0, "no": 0.0, "dev": defaultdict(float)} for ar in AREAS})
    wlast = defaultdict(str)                                # owner -> last worklog date (date fallback)
    wdates = wdates or {}
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
        wd = wdates.get(str(iid), "")
        if wd > wlast[owner]: wlast[owner] = wd
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
        date, dsrc = ticket_date(f, wlast.get(owner, ""))
        if not date or date < cutoff: continue
        tp = ttype_of(f); fv = f.get("fixVersions") or []
        is_us = tp == "US"; isb = tp in ("Bug", "Sub-bug")
        usf = is_us and status.lower() == "ready for sprint review"
        bugf = isb and status.lower() == "done"
        for ar in AREAS:
            o = data[ar]; lg = o["ai"] + o["no"]
            if lg <= 0: continue
            main = max(o["dev"], key=lambda a: o["dev"][a]) if o["dev"] else None
            units.append({"k": owner, "p": owner.split("-")[0], "fv": fv, "m": date[:7], "date": date, "ds": dsrc,
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
  var DSRC={test:'first sent to test (Ready for Test / In Test)',postdev:'first moved to a post-dev status (never sent to test)',resolved:'resolution date (no test / post-dev transition)',worklog:'last worklog (still in development)'};
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
            +'<td class="sm" title="'+esc(DSRC[u.ds]||'')+'">'+u.date+(u.ds&&u.ds!=='test'?'*':'')+'</td><td>'+esc(u.t)+'</td><td class="sm">'+(u.fv.length?esc(u.fv.join(', ')):'&ndash;')+'</td>'
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
    ap.add_argument("--dates")                              # {issueId: latest worklog date} (date fallback)
    ap.add_argument("--project", default="INTRD,MACRD,PRT730"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ns = nodes(json.load(open(a.issues, encoding="utf-8")))
    tempo = json.load(open(a.tempo, encoding="utf-8"))
    devmap = json.load(open(a.devmap, encoding="utf-8"))
    wdates = json.load(open(a.dates, encoding="utf-8")) if a.dates and os.path.exists(a.dates) else {}
    units, status_seen = build_units(ns, tempo, devmap, a.cutoff, wdates)
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
           'Sub-tasks roll into their parent US; sub-bugs are separate rows; overhead (PO/Archi/DevOps/Consultant) is excluded. All times in days (1 d = 8 h). Ticket date = the date the ticket was <b>first sent to test</b> (first transition into <i>Ready for Test</i> or <i>In Test</i>, from the Jira status history); a ticket that never went to test uses its first move into a post-dev status (<i>Need sync (after dev)</i>, <i>Ready for Sprint Review</i>, <i>Done</i>, &hellip;), else its resolution date, else its last worklog date &mdash; these fallbacks are marked <b>*</b> (hover for the source). Jira&rsquo;s <i>updated</i> date is never used, because any edit moves it.</div>'
           '<script id="units" type="application/json">' + json.dumps(units, separators=(",", ":")) + '</script>'
           '<script>' + JS + '</script>'
           "</body></html>")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(doc)
    print(f"Wrote {a.out} ({len(doc)} bytes, {len(units)} units)")

if __name__ == "__main__":
    main()

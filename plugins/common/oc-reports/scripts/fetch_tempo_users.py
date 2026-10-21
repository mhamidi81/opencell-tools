import json, os, sys, urllib.request, urllib.error, urllib.parse, datetime
BASE = "https://api.tempo.io/4"

def fetch_user(acc, tok, frm, to):
    """Return ([(issueId, startDate, seconds), ...], http_status) for one user's worklogs in [frm, to]."""
    out = []
    url = f"{BASE}/worklogs/user/{urllib.parse.quote(acc, safe='')}?from={frm}&to={to}&limit=1000"
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: data = json.load(r)
        except urllib.error.HTTPError as ex:
            sys.stderr.write(f"  {acc}: HTTP {ex.code}\n"); return out, ex.code
        for w in data.get("results") or []:
            iid = str((w.get("issue") or {}).get("id"))
            if iid and iid != "None":
                out.append((iid, w.get("startDate") or "", w.get("timeSpentSeconds") or 0))
        url = (data.get("metadata") or {}).get("next")
    return out, 200

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--devmap", required=True); ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True); ap.add_argument("--out", required=True); ap.add_argument("--ids-out", required=True)
    ap.add_argument("--dates-out")               # optional: {issueId: latest worklog date}
    ap.add_argument("--cache")                    # persistent month-bucketed cache for incremental refresh
    ap.add_argument("--refresh-days", type=int, default=45)  # re-fetch this many days back (must exceed the ~1-month log window)
    a = ap.parse_args()
    tok = os.environ.get("TEMPO_API_TOKEN")
    if not tok: sys.stderr.write("no token\n"); sys.exit(1)
    dev = json.load(open(a.devmap, encoding="utf-8"))

    # Cache: {"buckets": {issueId: {accId: {"YYYY-MM": secs}}}, "lastDate": {issueId: "YYYY-MM-DD"}}.
    # Worklogs older than ~1 month are immutable (they can't be logged/edited that far back), so only the
    # recent months need re-fetching; older months are served straight from the cache.
    cache = {"buckets": {}, "lastDate": {}}
    if a.cache and os.path.exists(a.cache):
        try: cache = json.load(open(a.cache, encoding="utf-8"))
        except Exception: cache = {"buckets": {}, "lastDate": {}}
    buckets = cache.setdefault("buckets", {}); lastDate = cache.setdefault("lastDate", {})

    if a.cache and buckets:   # incremental: refresh only the recent (mutable) months
        cutoff = datetime.date.today() - datetime.timedelta(days=a.refresh_days)
        cutoff_month = cutoff.strftime("%Y-%m")
        eff_from = cutoff.replace(day=1).strftime("%Y-%m-%d")
        for accs in buckets.values():                      # drop recent months so the fresh pull fully replaces them
            for months in accs.values():
                for mk in [m for m in months if m >= cutoff_month]: del months[mk]
        sys.stderr.write(f"cache hit ({len(buckets)} issues): refreshing months >= {cutoff_month} (from {eff_from})\n")
    else:                     # cold cache: full fetch from --from
        eff_from = a.frm
        sys.stderr.write(f"no cache: full fetch from {eff_from}\n")

    for acc, info in dev.items():
        wls, code = fetch_user(acc, tok, eff_from, a.to)
        for iid, sd, sec in wls:
            mk = sd[:7] if sd else "0000-00"
            buckets.setdefault(iid, {}).setdefault(acc, {})
            buckets[iid][acc][mk] = buckets[iid][acc].get(mk, 0) + sec
            if sd and sd > lastDate.get(iid, ""): lastDate[iid] = sd
        sys.stderr.write(f"{info['area']:8} {info['name']:26} {len(wls):5} worklogs\n")

    if a.cache:
        os.makedirs(os.path.dirname(os.path.abspath(a.cache)) or ".", exist_ok=True)
        json.dump(cache, open(a.cache, "w"))
    # flatten month buckets -> tempo {issueId: {accId: secs}} (dropping issues/accounts that netted to 0)
    tempo = {}
    for iid, accs in buckets.items():
        for acc, months in accs.items():
            s = sum(months.values())
            if s: tempo.setdefault(iid, {})[acc] = s
    json.dump(tempo, open(a.out, "w"))
    open(a.ids_out, "w").write(",".join(tempo.keys()))
    if a.dates_out: json.dump(lastDate, open(a.dates_out, "w"))
    sys.stderr.write(f"TOTAL distinct worklogged issues: {len(tempo)}\n")

if __name__ == "__main__": main()

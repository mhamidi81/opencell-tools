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

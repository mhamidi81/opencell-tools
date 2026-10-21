#!/usr/bin/env python3
"""Fetch the AI-usage report's tickets via direct Jira Cloud REST (enhanced JQL search).
Pass A = tickets carrying an AI-metrics record; Pass B = their child sub-issues.
Honours `fields` (excludes description), paginates via nextPageToken. Auth: JIRA_EMAIL:JIRA_API_TOKEN."""
import os, sys, json, time, base64, argparse, urllib.request, urllib.error
BASE="https://opencellsoft.atlassian.net"
EMAIL=os.environ.get("JIRA_EMAIL") or "andrius.karpavicius@opencellsoft.com"
TOK=os.environ["JIRA_API_TOKEN"]
AUTH=base64.b64encode(f"{EMAIL}:{TOK}".encode()).decode()
FIELDS_A=["summary","assignee","issuetype","status","resolutiondate","updated","timeoriginalestimate",
          "timespent","worklog","components","customfield_10157","customfield_10158","customfield_10189",
          "customfield_10745","customfield_10613"]
FIELDS_B=["summary","issuetype","components","timeoriginalestimate","timespent","parent","customfield_10745"]

def post(path, body):
    for attempt in range(5):
        req=urllib.request.Request(BASE+path, data=json.dumps(body).encode(),
            headers={"Authorization":f"Basic {AUTH}","Accept":"application/json","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code in (429,503): time.sleep(2*(attempt+1)); continue
            sys.stderr.write(f"HTTP {ex.code}: {ex.read()[:200]}\n"); raise
    raise RuntimeError("retries exhausted")

def fetch_jql(jql, fields):
    nodes=[]; token=None
    while True:
        body={"jql":jql,"fields":fields,"maxResults":100}
        if token: body["nextPageToken"]=token
        d=post("/rest/api/3/search/jql", body)
        nodes+=d.get("issues") or []
        if d.get("isLast") or not d.get("nextPageToken"): break
        token=d["nextPageToken"]
    return nodes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--since", required=True); ap.add_argument("--project", default="INTRD,MACRD")
    ap.add_argument("--out-tickets", required=True); ap.add_argument("--out-children", required=True)
    a=ap.parse_args()
    projs=[x.strip() for x in a.project.split(",") if x.strip()]
    scope = "" if a.project.strip().lower() in ("all","*","") else f'project in ({", ".join(projs)}) AND '
    jqlA=f'{scope}cf[10745] IS NOT EMPTY AND updated >= "{a.since}" ORDER BY updated DESC'
    parents=fetch_jql(jqlA, FIELDS_A)
    json.dump({"issues":{"nodes":parents}}, open(a.out_tickets,"w",encoding="utf-8"))
    sys.stderr.write(f"Pass A: {len(parents)} tickets with AI records\n")
    keys=[n["key"] for n in parents]
    children=[]
    for i in range(0,len(keys),100):
        children+=fetch_jql("parent in ("+",".join(keys[i:i+100])+")", FIELDS_B)
    json.dump({"issues":{"nodes":children}}, open(a.out_children,"w",encoding="utf-8"))
    sys.stderr.write(f"Pass B: {len(children)} child sub-issues\n")

if __name__=="__main__": main()

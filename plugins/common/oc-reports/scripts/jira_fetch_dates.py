#!/usr/bin/env python3
"""Select report tickets by DATE via Jira Cloud REST enhanced JQL, then fetch their parents + all
sub-issues, and stamp each ticket with its "sent to test" date from the status changelog.
Writes issues.json. Auth: JIRA_EMAIL:JIRA_API_TOKEN.

Ticket date (fields.testDate / fields.dateSrc), from the status changelog:
  1. "test"     - FIRST transition into Ready for Test / In Test (first time dev handed it to test)
  2. "postdev"  - never tested: FIRST transition into a post-dev status (Need sync (after dev),
                  To Review by PO, Ready for Sprint Review, ..., Done/Resolved/Closed)
  3. "resolved" - no such transition: resolutiondate
  (none)        - still in development: the reports fall back to the LAST worklog date.
`updated` is never used: any edit (a comment, a classification field) moves it."""
import os, sys, json, time, base64, argparse, datetime, urllib.request, urllib.error
BASE="https://opencellsoft.atlassian.net"
EMAIL=os.environ.get("JIRA_EMAIL") or "andrius.karpavicius@opencellsoft.com"
TOK=os.environ["JIRA_API_TOKEN"]
AUTH=base64.b64encode(f"{EMAIL}:{TOK}".encode()).decode()
FIELDS=["summary","issuetype","status","components","timeoriginalestimate","timespent","parent",
        "resolutiondate","updated","aggregatetimespent","fixVersions",
        "customfield_10157","customfield_10158","customfield_10189","customfield_10745"]

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

def fetch_jql(jql):
    out=[]; token=None
    while True:
        body={"jql":jql,"fields":FIELDS,"maxResults":100}
        if token: body["nextPageToken"]=token
        d=post("/rest/api/3/search/jql", body)
        out+=d.get("issues") or []
        if d.get("isLast") or not d.get("nextPageToken"): break
        token=d["nextPageToken"]
    return out

def slim(n):
    f=n.get("fields") or {}; p=f.get("parent") or {}
    return {"id":n["id"],"key":n["key"],"fields":{
        "summary":f.get("summary"),"issuetype":{"name":(f.get("issuetype") or {}).get("name")},
        "status":{"name":(f.get("status") or {}).get("name")},"components":f.get("components") or [],
        "timeoriginalestimate":f.get("timeoriginalestimate"),"timespent":f.get("timespent"),
        "resolutiondate":f.get("resolutiondate"),"updated":f.get("updated"),
        "aggregatetimespent":f.get("aggregatetimespent"),
        "fixVersions":[v.get("name") for v in (f.get("fixVersions") or []) if v.get("name")],
        "parent":{"key":p.get("key")} if p.get("key") else None,
        "customfield_10157":f.get("customfield_10157"),"customfield_10158":f.get("customfield_10158"),
        "customfield_10189":f.get("customfield_10189"),"customfield_10745":f.get("customfield_10745")}}

TEST_STATUSES={"ready for test","in test"}
POSTDEV_STATUSES={"need sync (after dev)","to review by po","ready for sprint review","need documentation",
    "to review by customer","ready for release","released","done","resolved","closed"}
NODATE_TYPES={"sub-task","sub test execution"}     # roll up into the parent; never a row of their own

def status_changes(ids):
    """{issueId: [(epochMs, toStatusLower), ...]} for the given issue ids (bulk changelog, status only)."""
    out={}
    for b in batched(ids,1000):
        token=None
        while True:
            body={"issueIdsOrKeys":b,"fieldIds":["status"],"maxResults":10000}
            if token: body["nextPageToken"]=token
            d=post("/rest/api/3/changelog/bulkfetch", body)
            for il in d.get("issueChangeLogs") or []:
                lst=out.setdefault(str(il.get("issueId")),[])
                for h in il.get("changeHistories") or []:
                    ts=h.get("created")
                    if isinstance(ts,str): ts=datetime.datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()*1000
                    for it in h.get("items") or []:
                        if it.get("fieldId","status")=="status" and it.get("toString"):
                            lst.append((ts,it["toString"].strip().lower()))
            token=d.get("nextPageToken")
            if not token: break
    return out

def date_of(changes, resolutiondate):
    """(YYYY-MM-DD, source) per the rule in the module docstring; (None, None) when still in development."""
    ch=sorted(changes or [])
    for group,src in ((TEST_STATUSES,"test"),(POSTDEV_STATUSES,"postdev")):
        hit=[t for t,st in ch if st in group]
        if hit: return datetime.datetime.fromtimestamp(hit[0]/1000).strftime("%Y-%m-%d"), src
    if resolutiondate: return resolutiondate[:10], "resolved"
    return None, None

def batched(seq,n):
    for i in range(0,len(seq),n): yield seq[i:i+n]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--since", required=True); ap.add_argument("--until", required=True)
    ap.add_argument("--project", default="INTRD,MACRD,PRT730"); ap.add_argument("--out", required=True)
    a=ap.parse_args()
    PROJS=[x.strip() for x in a.project.split(",") if x.strip()]; PSTR=", ".join(PROJS)
    def in_scope(k): return any(str(k).startswith(q+"-") for q in PROJS)
    # Pass A/B: a SUPERSET of the tickets whose ticket-date can fall in the window — moved into a
    # test/post-dev status in it, resolved in it, or (still in development) worklogged in it.
    # The exact date is computed below from the changelog and filtered by the report.
    W=f'("{a.since}", "{a.until}")'
    chg=" OR ".join(f'status changed to "{s}" during {W}' for s in
        ["Ready for Test","In Test","Need sync (after dev)","To Review by PO","Ready for Sprint Review",
         "Need Documentation","To review by Customer","Ready for Release","Released","Done","Resolved","Closed"])
    jqlA=f'project in ({PSTR}) AND ({chg})'
    jqlB=f'project in ({PSTR}) AND ((resolutiondate >= "{a.since}" AND resolutiondate < "{a.until}") OR (worklogDate >= "{a.since}" AND worklogDate < "{a.until}"))'
    by_id={}
    for n in fetch_jql(jqlA)+fetch_jql(jqlB): by_id[str(n["id"])]=slim(n)
    sys.stderr.write(f"Pass A/B (date-selected): {len(by_id)} issues\n")
    by_key={v["key"]:v for v in by_id.values()}
    # Pass C: parents of any selected sub-issue not already present (so a subtask maps to its row)
    pkeys=sorted({(v["fields"].get("parent") or {}).get("key") for v in list(by_id.values())
                  if (v["fields"].get("parent") or {}).get("key") and (v["fields"]["parent"]["key"] not in by_key)})
    for b in batched(pkeys,100):
        for n in fetch_jql("key in ("+",".join(b)+")"):
            s=slim(n); by_id[str(n["id"])]=s; by_key[s["key"]]=s
    sys.stderr.write(f"Pass C (parents): +{len(pkeys)}, total {len(by_id)}\n")
    # Pass D: all sub-issues of the in-scope Story/Enabler parents (DL estimate, sub-bugs, roll-up)
    story_parents=sorted({v["key"] for v in list(by_id.values())
        if in_scope(v["key"]) and (v["fields"]["issuetype"]["name"] or "") in ("Story","Enabler")})
    seen=set(by_id)
    for i,b in enumerate(batched(story_parents,60)):
        for n in fetch_jql("parent in ("+",".join(b)+")"):
            if str(n["id"]) not in seen: s=slim(n); by_id[str(n["id"])]=s
        if i%10==0: sys.stderr.write(f"  subtask batch {i}: total {len(by_id)}\n")
    sys.stderr.write(f"Pass D done: total {len(by_id)} nodes\n")
    # Pass E: status changelog -> ticket date ("sent to test") for every ticket that can be a row
    ids=[i for i,v in by_id.items() if in_scope(v["key"])
         and (v["fields"]["issuetype"]["name"] or "").lower() not in NODATE_TYPES]
    changes=status_changes(ids); srcs={}
    for i in ids:
        f=by_id[i]["fields"]; f["testDate"],f["dateSrc"]=date_of(changes.get(i),f.get("resolutiondate"))
        srcs[f["dateSrc"]]=srcs.get(f["dateSrc"],0)+1
    sys.stderr.write(f"Pass E (changelog dates): {len(ids)} tickets, by source {srcs}\n")
    json.dump({"issues":{"nodes":list(by_id.values())}}, open(a.out,"w",encoding="utf-8"))
    inp=sum(1 for v in by_id.values() if in_scope(v["key"]))
    sys.stderr.write(f"WROTE {a.out}: {len(by_id)} total, {inp} in {PSTR}\n")

if __name__=="__main__": main()

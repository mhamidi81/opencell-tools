#!/usr/bin/env python3
"""Stage 1 of /oc-bug-root-causes: fetch a window's "Development issue" bugs.

Deterministic. The Root-cause filter is in the JQL, so nothing else is downloaded.
Area resolution is bug_fetch's, copied verbatim from /oc-bug-clusters, so the two
commands never split the same bug differently.

The Invalid/Declined/Duplicate filter of /oc-bug-clusters is deliberately NOT applied:
a bug whose root cause was set to "Development issue" has been triaged as a real defect.

Output: bugs.json, the full normalised records. The model never reads it; stage 2
turns it into the batch files the classifier reads.
"""
import argparse
import json
import sys
from urllib.parse import quote

from bug_fetch import area_of, areas_in_scope, excerpt, flatten_adf, resolve_window
from jira_client import BASE, JiraClient, JiraError, MissingToken

ROOT_CAUSE_FIELD = "customfield_10111"
ROOT_CAUSE_VALUE = "Development issue"
EXCERPT_LIMIT = 600
COMMENT_LIMIT = 400
COMMENT_COUNT = 3
NO_BUGS = 3

FIELDS = ["summary", "description", "issuetype", "status", "resolution", "components",
          "labels", "created", "assignee", "reporter", ROOT_CAUSE_FIELD]


def build_jql(projects, since, until):
    # "Sub-bug" is quoted defensively, as in /oc-bug-clusters.
    return (f'project in ({", ".join(projects)}) '
            f'AND issuetype in (Bug, "Sub-bug") '
            f'AND "Root cause" = "{ROOT_CAUSE_VALUE}" '
            f'AND created >= "{since}" AND created < "{until}" '
            f'ORDER BY created DESC')


def fetch_comments(client, key, count=COMMENT_COUNT, limit=COMMENT_LIMIT):
    """The newest `count` comments as 'Author: text', each trimmed to `limit` chars.
    Developers often explain the fix in a closing comment, which is why these are read."""
    page = client.get(f"/rest/api/3/issue/{quote(key)}/comment"
                      f"?orderBy=-created&maxResults={count}")
    out = []
    for comment in (page.get("comments") or [])[:count]:
        text = excerpt(flatten_adf(comment.get("body")), limit)
        if text:
            author = (comment.get("author") or {}).get("displayName") or "?"
            out.append(f"{author}: {text}")
    return out


def normalize(issue, comments):
    fields = issue.get("fields") or {}
    components = fields.get("components") or []
    status = fields.get("status") or {}
    key = issue.get("key")
    return {
        "key": key,
        "area": area_of(fields),
        "component": (components[0].get("name") if components else None),
        "summary": fields.get("summary") or "",
        "excerpt": excerpt(flatten_adf(fields.get("description")), EXCERPT_LIMIT),
        "comments": comments,
        "status": status.get("name"),
        "status_category": (status.get("statusCategory") or {}).get("key"),
        "created": (fields.get("created") or "")[:10],
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "labels": list(fields.get("labels") or []),
        "url": f"{BASE}/browse/{key}",
    }


def collect(client, jql, repo, warn=sys.stderr.write):
    """Fetch and normalise. Bugs of the area NOT in scope are excluded; bugs with no
    resolvable area are kept — the mistake still has a type when the area is unknown.
    A failed comment fetch costs that bug its comments, never its place in the run."""
    scope = areas_in_scope(repo)
    bugs, fetched, comment_failures = [], 0, 0
    for issue in client.search(jql, FIELDS):
        fetched += 1
        area = area_of(issue.get("fields") or {})
        if area is not None and area not in scope:
            continue
        try:
            comments = fetch_comments(client, issue["key"])
        except JiraError as ex:
            comment_failures += 1
            warn(f"WARNING: comments unavailable for {issue['key']}: {ex}\n")
            comments = []
        bugs.append(normalize(issue, comments))
    return {"repo": repo, "fetched": fetched, "comment_failures": comment_failures,
            "bugs": bugs}


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description='Fetch a window of "Development issue" bugs.')
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--repo", default="both", choices=["portal", "core", "both"])
    parser.add_argument("--out-bugs", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = client or JiraClient()
    except (MissingToken, ValueError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    projects = [p.strip() for p in args.project.split(",") if p.strip()]
    document = collect(client, build_jql(projects, since, until), args.repo)
    document["window"] = {"since": since, "until": until}
    document["projects"] = projects

    with open(args.out_bugs, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)

    bugs = document["bugs"]
    sys.stderr.write(
        f'Analysing {", ".join(projects)} "Development issue" bugs, {args.repo}, '
        f"{since} → {until}\n"
        f"  fetched {document['fetched']}, kept {len(bugs)} "
        f"({sum(1 for b in bugs if b['area'] is None)} with no resolvable area, "
        f"{document['comment_failures']} without comments)\n")
    if not bugs:
        sys.stderr.write(f"No Development issue bugs created in {since} → {until} "
                         f"for {', '.join(projects)}\n")
        return NO_BUGS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

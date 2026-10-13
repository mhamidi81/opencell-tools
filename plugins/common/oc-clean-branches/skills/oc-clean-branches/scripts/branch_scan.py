#!/usr/bin/env python3
"""Stage 1 of /oc-clean-branches: list stale branches and apply the five guards.

Read-only. Writes a plan JSON that branch_report.py renders and branch_delete.py
executes after the user has confirmed. Nothing here can delete anything.

Guards run cheapest first, and the expensive ones (Jira, then one or two Bitbucket
calls per branch) only on what survived. A branch records the FIRST rule that
excluded it. Every failure excludes (fail-safe): a guard that could not be evaluated
is never read as a pass.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import branch_rules as rules
from bitbucket_client import BitbucketClient, BitbucketError
from jira_client import JiraClient, JiraError

REPOS = {"portal": ["opencell-portal"], "core": ["opencell-core"],
         "both": ["opencell-portal", "opencell-core"]}
JIRA_BATCH = 50


def resolve_repos(value):
    return REPOS.get(value) or [slug.strip() for slug in value.split(",") if slug.strip()]


def lookup_tickets(jira, keys):
    """key -> {"type", "status"} or {"error"}. Batched search, then per-key GET for
    whatever the batch did not return (moved issues come back under their new key,
    and a JQL naming a non-existent key is rejected as a whole)."""
    found = {}
    keys = sorted(set(keys))
    for i in range(0, len(keys), JIRA_BATCH):
        batch = keys[i:i + JIRA_BATCH]
        try:
            for issue in jira.search(f"key in ({', '.join(batch)})", ["issuetype", "status"]):
                found[issue["key"]] = _ticket(issue)
        except JiraError:
            pass  # fall through to per-key lookups below
        for key in batch:
            if key in found:
                continue
            try:
                issue = jira.get(f"/rest/api/3/issue/{key}?fields=issuetype,status")
                found[key] = _ticket(issue)
            except JiraError as ex:
                found[key] = {"error": "ticket not found" if ex.status == 404 else str(ex)[:120]}
    return found


def _ticket(issue):
    fields = issue.get("fields") or {}
    return {"type": (fields.get("issuetype") or {}).get("name"),
            "status": (fields.get("status") or {}).get("name")}


def _get_or_none(bb, path):
    try:
        return bb.get(path)
    except BitbucketError as ex:
        if ex.status == 404:
            return None
        raise


def scan_repo(bb, jira, workspace, repo, before, recent_cutoff, target=None):
    base = f"/repositories/{workspace}/{repo}"
    meta = bb.get(base)
    main_branch = (meta.get("mainbranch") or {}).get("name")
    model = _get_or_none(bb, f"{base}/branching-model") or {}
    # R1 needs the restrictions. Unreadable (403 without admin) -> stop this repo:
    # a protected branch must never become deletable because we could not see it.
    restrictions = list(bb.paginate(f"{base}/branch-restrictions", {"pagelen": 100}))
    globs = rules.restriction_patterns(restrictions, model)

    branches = list(bb.paginate(f"{base}/refs/branches", {"pagelen": 100}))
    names = {b["name"] for b in branches}
    # develop/dev first: the branching model can lag behind (opencell-portal's still
    # names `backlog`), and those two are the branches tickets actually merge into.
    dev_branch = target or next((n for n in ("develop", "dev") if n in names), None) \
        or ((model.get("development") or {}).get("branch") or {}).get("name") or main_branch
    if dev_branch not in names:
        raise BitbucketError(f"target branch `{dev_branch}` does not exist in {repo}")

    open_prs = list(bb.paginate(f"{base}/pullrequests", {"state": "OPEN", "pagelen": 50}))
    in_open_pr = {}
    for pr in open_prs:
        for side in ("source", "destination"):
            name = ((pr.get(side) or {}).get("branch") or {}).get("name")
            if name:
                in_open_pr.setdefault(name, pr.get("id"))

    excluded, survivors = [], []
    candidates = 0
    for branch in branches:
        target_ = branch.get("target") or {}
        row = {"name": branch["name"], "hash": target_.get("hash"),
               "date": target_.get("date"),
               "author": ((target_.get("author") or {}).get("raw") or "").split("<")[0].strip(),
               "ticket": rules.ticket_key(branch["name"])}
        if not row["date"] or rules.parse_ts(row["date"]) >= before:
            continue
        candidates += 1
        reason = None
        if row["name"] in (main_branch, dev_branch):
            reason = ("R1", f"main / target branch `{row['name']}`")
        elif rules.structural_reason(row["name"]):
            reason = ("R1", rules.structural_reason(row["name"]))
        elif rules.restricted_by(row["name"], globs):
            reason = ("R1", f"branch restriction `{rules.restricted_by(row['name'], globs)}`")
        elif row["name"] in in_open_pr:
            reason = ("R2", f"open PR #{in_open_pr[row['name']]}")
        elif rules.parse_ts(row["date"]) >= recent_cutoff:
            reason = ("R4", f"last commit {row['date'][:10]}")
        elif not row["ticket"]:
            reason = ("R5", "no Jira key in the branch name")
        if reason:
            excluded.append({**row, "rule": reason[0], "reason": reason[1]})
        else:
            survivors.append(row)

    tickets = lookup_tickets(jira, [r["ticket"] for r in survivors]) if survivors else {}
    deletable = []
    for row in survivors:
        info = tickets.get(row["ticket"]) or {"error": "ticket not looked up"}
        row.update(issuetype=info.get("type"), status=info.get("status"))
        if info.get("error"):
            excluded.append({**row, "rule": "R5", "reason": f"{row['ticket']}: {info['error']}"})
            continue
        if not rules.type_allowed(info["type"]):
            excluded.append({**row, "rule": "R5", "reason": f"{row['ticket']} is a {info['type']}"})
            continue
        try:
            row["target"] = merge_target(bb, base, row["name"], names, dev_branch)
            ahead = bb.get(f"{base}/commits", {"include": row["hash"],
                                               "exclude": row["target"], "pagelen": 1})
        except BitbucketError as ex:
            excluded.append({**row, "rule": "ERR", "reason": str(ex)[:160]})
            continue
        if ahead.get("values"):
            excluded.append({**row, "rule": "R3",
                             "reason": f"has commits not in `{row['target']}`"})
            continue
        deletable.append(row)

    by_rule = {rule: sum(1 for r in excluded if r["rule"] == rule) for rule in rules.RULES}
    return {"repo": repo, "main_branch": main_branch, "dev_branch": dev_branch,
            "restriction_globs": globs, "total_branches": len(branches),
            "candidates": candidates, "excluded_by_rule": by_rule,
            "deletable": sorted(deletable, key=lambda r: r["date"]),
            "excluded": sorted(excluded, key=lambda r: (r["rule"], r["name"]))}


def merge_target(bb, base, name, names, dev_branch):
    """The branch's target is the destination of its latest MERGED PR, if that branch
    still exists; otherwise the development branch."""
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    page = bb.get(f"{base}/pullrequests", {"state": "MERGED", "pagelen": 1,
                                           "sort": "-updated_on",
                                           "q": f'source.branch.name="{escaped}"'})
    for pr in page.get("values") or []:
        dest = ((pr.get("destination") or {}).get("branch") or {}).get("name")
        if dest in names:
            return dest
    return dev_branch


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True, help="YYYY-MM-DD; tip commit strictly before")
    ap.add_argument("--repo", default="both", help="portal | core | both | slug[,slug]")
    ap.add_argument("--workspace", default="opencellsoft")
    ap.add_argument("--recent-days", type=int, default=30)
    ap.add_argument("--target", default=None, help="override the development branch")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    before = rules.day_start(args.before)
    now = datetime.now(timezone.utc)
    recent_cutoff = (now - timedelta(days=args.recent_days)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    try:
        bb, jira = BitbucketClient(), JiraClient()
    except (BitbucketError, JiraError) as ex:
        print(str(ex), file=sys.stderr)
        return 2

    plan = {"workspace": args.workspace, "generated_at": now.isoformat(timespec="seconds"),
            "before": args.before, "recent_days": args.recent_days,
            "recent_cutoff": recent_cutoff.date().isoformat(), "repos": [], "errors": []}
    for repo in resolve_repos(args.repo):
        try:
            result = scan_repo(bb, jira, args.workspace, repo, before, recent_cutoff, args.target)
        except (BitbucketError, JiraError, ValueError) as ex:
            plan["errors"].append({"repo": repo, "error": str(ex)[:300]})
            print(f"{repo}: SKIPPED — {ex}", file=sys.stderr)
            continue
        plan["repos"].append(result)
        print(f"{repo}: {result['total_branches']} branches, {result['candidates']} before "
              f"{args.before}, {len(result['deletable'])} deletable")
    with open(args.out, "w") as handle:
        json.dump(plan, handle, indent=2)
    return 0 if plan["repos"] else 1


if __name__ == "__main__":
    sys.exit(main())

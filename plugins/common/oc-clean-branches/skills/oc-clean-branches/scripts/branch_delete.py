#!/usr/bin/env python3
"""Stage 3 of /oc-clean-branches: delete the branches of a confirmed plan.

Run ONLY after the user explicitly confirmed the report. Two locks make a slip
harmless:

  --confirm N  must equal the plan's deletable total, so a plan that changed (or a
               mistyped number) deletes nothing at all.
  re-check     right before each DELETE the branch tip is re-read and the OPEN PRs
               re-fetched: a branch that moved or gained an open PR since the report
               is skipped, never deleted.

Every deleted branch is logged with its tip hash. R3 guaranteed that hash is reachable
from the target branch, so `git push origin <hash>:refs/heads/<name>` restores it.
"""
import argparse
import json
import sys
import urllib.parse

from bitbucket_client import BitbucketClient, BitbucketError

RED, RESET = "\033[1;31m", "\033[0m"


def open_pr_branches(bb, base):
    names = set()
    for pr in bb.paginate(f"{base}/pullrequests", {"state": "OPEN", "pagelen": 50}):
        for side in ("source", "destination"):
            name = ((pr.get(side) or {}).get("branch") or {}).get("name")
            if name:
                names.add(name)
    return names


def execute(bb, plan, confirm):
    total = sum(len(r["deletable"]) for r in plan["repos"])
    if confirm != total:
        raise SystemExit(f"--confirm {confirm} does not match the plan's {total} deletable "
                         "branch(es). Nothing was deleted.")
    results = []
    for repo in plan["repos"]:
        base = f"/repositories/{plan['workspace']}/{repo['repo']}"
        if not repo["deletable"]:
            continue
        busy = open_pr_branches(bb, base)
        for row in repo["deletable"]:
            entry = {"repo": repo["repo"], "name": row["name"], "hash": row["hash"]}
            try:
                path = f"{base}/refs/branches/" + urllib.parse.quote(row["name"], safe="/")
                current = bb.get(path)
                if (current.get("target") or {}).get("hash") != row["hash"]:
                    entry.update(status="skipped", reason="tip moved since the report")
                elif row["name"] in busy:
                    entry.update(status="skipped", reason="an open PR appeared since the report")
                else:
                    bb.delete_branch(plan["workspace"], repo["repo"], row["name"])
                    entry["status"] = "deleted"
            except BitbucketError as ex:
                if ex.status == 404:
                    entry.update(status="skipped", reason="already gone")
                else:
                    entry.update(status="failed", reason=str(ex)[:200])
            results.append(entry)
            print(f"{entry['status']:>8}  {repo['repo']}  {row['name']}"
                  + (f"  ({entry['reason']})" if entry.get("reason") else ""))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--confirm", type=int, required=True,
                    help="the deletable total the user confirmed")
    ap.add_argument("--log", required=True, help="JSON log of every deletion attempt")
    args = ap.parse_args(argv)
    with open(args.plan) as handle:
        plan = json.load(handle)
    try:
        bb = BitbucketClient()
    except BitbucketError as ex:
        print(str(ex), file=sys.stderr)
        return 2
    print(f"{RED}Deleting {args.confirm} branch(es) from Bitbucket — irreversible.{RESET}")
    results = execute(bb, plan, args.confirm)
    with open(args.log, "w") as handle:
        json.dump({"workspace": plan["workspace"], "results": results}, handle, indent=2)
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in ("deleted", "skipped", "failed")}
    print(f"deleted {counts['deleted']}, skipped {counts['skipped']}, failed {counts['failed']}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

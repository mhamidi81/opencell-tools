#!/usr/bin/env python3
"""Stage 1 of /oc-pr-rejection-rate: fetch a window of pull requests and their activity.

All network I/O lives here, so pr_classify.py can stay pure. The window anchors on
created_on: "of the PRs opened this week, X% were rejected" is a stable denominator,
where updated_on would let one PR count in several weeks.

Rejection is historical (see pr_classify), so each PR's activity feed is fetched too —
one extra call per PR. At 50-200 PRs per week per repository that is well inside
Bitbucket's 1000 requests/hour authenticated budget, and the calls are made in a small
thread pool.
"""
import argparse
import concurrent.futures
import json
import sys
from datetime import date, datetime, timedelta, timezone

from bitbucket_client import BitbucketClient, BitbucketError, MissingToken

DEFAULT_WORKSPACE = "opencellsoft"
DEFAULT_DAYS = 7
DEFAULT_WORKERS = 8
REPO_SLUG = {"portal": "opencell-portal", "core": "opencell-core"}
STATES = ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]

# Bitbucket's default list projection omits `draft` and `participants`. R3's
# current-flag mode and R2's participant fallback are both useless without them, so
# they are requested explicitly rather than hoped for.
FIELDS = ",".join([
    "next",
    "values.id", "values.title", "values.state", "values.created_on",
    "values.updated_on", "values.draft",
    "values.author.display_name",
    "values.links.html.href",
    "values.participants.state", "values.participants.approved",
])


def resolve_window(since=None, until=None, today=None):
    """Resolve the window to two ISO dates. `until` is exclusive, so today counts."""
    today = today or date.today()
    end = date.fromisoformat(until) if until else today + timedelta(days=1)
    start = date.fromisoformat(since) if since else end - timedelta(days=DEFAULT_DAYS)
    if start >= end:
        raise ValueError(f"--since ({start}) must be before --until ({end})")
    return start.isoformat(), end.isoformat()


def list_pull_requests(client, workspace, slug, since, until):
    path = f"/repositories/{workspace}/{slug}/pullrequests"
    params = {
        "state": STATES,
        "pagelen": 50,
        "sort": "-created_on",
        "fields": FIELDS,
        "q": f'created_on >= "{since}T00:00:00+00:00" '
             f'AND created_on < "{until}T00:00:00+00:00"',
    }
    return list(client.paginate(path, params))


def _entry_date(entry):
    """The timestamp of an activity entry, whatever kind it is.

    Verified against live Bitbucket data: an entry is
    `{"<kind>": {...}, "pull_request": {...}}`, where the sibling `pull_request` is
    the PR's own metadata rather than the event — and it comes FIRST in Bitbucket's
    key order. Taking whichever value happens to carry a timestamp would therefore
    read the wrong one the day that sibling gains a date, so it is skipped explicitly.

    Comments date themselves with `created_on` rather than `date`; accepting both
    keeps the sort genuinely chronological instead of bunching every comment at the
    end. Across a 340-entry live sample every `update` entry carried `date`, which is
    what R3 actually depends on.
    """
    for key, payload in entry.items():
        if key == "pull_request" or not isinstance(payload, dict):
            continue
        stamp = payload.get("date") or payload.get("created_on")
        if stamp:
            return stamp
    return ""


_UNDATED = datetime.min.replace(tzinfo=timezone.utc)


def _sort_key(entry):
    """Parse the timestamp rather than comparing ISO strings.

    Lexicographic comparison is only correct while every timestamp shares one UTC
    offset and one fractional-second width. A single `+02:00` entry reverses the
    two it sits between, and reversing a feed inverts R3 — a PR pushed back to
    draft reads as one merely opened as a draft — while the model still reports
    mode "activity". Undated entries sort last; the sort is stable, so ties keep
    the order the API gave them.
    """
    raw = _entry_date(entry)
    if not raw:
        return (1, _UNDATED)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return (1, _UNDATED)
    # A naive timestamp cannot be compared with an aware one; assume UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (0, parsed)


def sort_oldest_first(entries):
    """Normalise an activity feed to chronological order.

    pr_classify.draft_states treats the oldest retained entry as the PR's initial
    draft state, and Bitbucket's activity endpoint conventionally returns entries
    newest-first. Read in that order, a PR pushed back to draft is indistinguishable
    from one merely opened as a draft, and R3 silently reports zero.
    """
    return sorted(entries, key=_sort_key)


def fetch_activity(client, workspace, slug, pr_id):
    path = f"/repositories/{workspace}/{slug}/pullrequests/{pr_id}/activity"
    return sort_oldest_first(list(client.paginate(path, {"pagelen": 50})))


def fetch_repo(client, workspace, slug, since, until, workers=DEFAULT_WORKERS):
    prs = list_pull_requests(client, workspace, slug, since, until)

    def attach(pr):
        try:
            pr["activity"] = fetch_activity(client, workspace, slug, pr["id"])
            pr["warnings"] = []
        except BitbucketError as ex:
            # Never drop the PR: a missing activity feed costs R2 and R3 for this one
            # PR, but dropping it would shrink the denominator and flatter the rate.
            pr["activity"] = []
            pr["warnings"] = [f"activity fetch failed: {ex}"]
        return pr

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        attached = list(pool.map(attach, prs))
    return {"pull_requests": attached}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch a window of Bitbucket pull requests.")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--repo", default="both", choices=["portal", "core", "both"])
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = BitbucketClient()
    except (ValueError, MissingToken) as ex:
        print(str(ex), file=sys.stderr)
        return 2

    slugs = list(REPO_SLUG.values()) if args.repo == "both" else [REPO_SLUG[args.repo]]
    document = {"window": {"since": since, "until": until},
                "workspace": args.workspace, "repos": {}}
    try:
        for slug in slugs:
            document["repos"][slug] = fetch_repo(client, args.workspace, slug, since, until)
    except BitbucketError as ex:
        print(str(ex), file=sys.stderr)
        return 1

    with open(args.out, "w") as handle:
        json.dump(document, handle, indent=2)
    counts = ", ".join(f"{s}: {len(document['repos'][s]['pull_requests'])}" for s in slugs)
    print(f"window {since} -> {until} (exclusive); {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

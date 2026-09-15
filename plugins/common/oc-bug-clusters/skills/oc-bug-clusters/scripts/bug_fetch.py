#!/usr/bin/env python3
"""Stage 1-2 of /oc-bug-clusters: fetch a window of bugs and resolve their area.

Everything in this module is deterministic. The area decides which Enabler a bug
ends up under, so it must not move between two runs of the same window — that is
why it is Python and not an LLM judgement.

Two files come out:
  bugs.json           the full normalised records; never read into model context
  classify_input.jsonl  one compact line per classifiable bug; the only file the
                        model reads
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta

from jira_client import BASE, JiraClient, MissingToken

# Area token -> the Jira component that means it. The two vocabularies are kept
# apart deliberately: the token is ours, the component name is Jira's.
AREA_COMPONENT = {"portal": "Frontend", "core": "Backend"}
COMPONENT_AREA = {"frontend": "portal", "backend": "core"}

# The fallback signal. Must be bracketed AND leading — "fix [front] later" is prose,
# not a tag, and treating it as one would mis-file the bug.
TAG = re.compile(r"^\s*\[\s*(front|back)", re.I)
TAG_AREA = {"front": "portal", "back": "core"}

# Measured against live INTRD data (2025-09 → 2026-09): "Invalid" is a Jira
# STATUS here (416 bugs carry it), never a resolution; the resolution the team
# uses to reject a bug is "Declined" (13 of a 100-bug sample). Filtering on
# resolution alone would therefore drop almost nothing.
DROPPED_RESOLUTIONS = {"invalid", "duplicate", "declined"}
DROPPED_STATUSES = {"invalid"}
EXCERPT_LIMIT = 300
DEFAULT_DAYS = 30

FIELDS = ["summary", "description", "issuetype", "status", "resolution", "components",
          "labels", "created", "priority", "assignee", "reporter", "parent"]

# ADF nodes that imply a word boundary when flattened.
BLOCK_TYPES = {"paragraph", "heading", "listItem", "tableRow", "tableCell",
               "codeBlock", "blockquote", "panel", "rule", "hardBreak"}


def flatten_adf(node):
    """Flatten an ADF document to plain text. Returns '' for anything unparseable.

    A bug with an unreadable description must still be classifiable from its summary,
    so this never raises.

    A plain string is taken as-is: REST v3 returns ADF, but v2, exports and proxies
    hand back text or wiki markup, and returning "" for those would silently cost
    every bug its excerpt — the main classification signal after the summary.
    """
    if isinstance(node, str):
        return " ".join(node.split())

    parts = []

    def walk(n, depth=0):
        if depth > 50:
            return
        if isinstance(n, dict):
            if n.get("type") in BLOCK_TYPES:
                parts.append(" ")
            if n.get("type") == "text" and isinstance(n.get("text"), str):
                parts.append(n["text"])
            content = n.get("content")
            if isinstance(content, list):
                for child in content:
                    walk(child, depth + 1)
        elif isinstance(n, list):
            for child in n:
                walk(child, depth + 1)

    try:
        walk(node)
    except (TypeError, AttributeError, RecursionError, ValueError):
        return ""
    return " ".join("".join(parts).split())


def excerpt(text, limit=EXCERPT_LIMIT):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def area_of(fields):
    for component in fields.get("components") or []:
        area = COMPONENT_AREA.get((component.get("name") or "").strip().lower())
        if area:
            return area
    match = TAG.match(fields.get("summary") or "")
    if match:
        return TAG_AREA[match.group(1).lower()]
    return None


def is_real_defect(fields):
    """A bug the team accepted as a genuine defect.

    Checks BOTH fields: this Jira rejects a bug by moving it to the *status*
    Invalid, and separately records resolution Declined/Duplicate. Checking only
    one of the two lets rejected bugs into clusters.
    """
    resolution = (fields.get("resolution") or {}).get("name") or ""
    if resolution.strip().lower() in DROPPED_RESOLUTIONS:
        return False
    status = (fields.get("status") or {}).get("name") or ""
    return status.strip().lower() not in DROPPED_STATUSES


def resolve_window(since, until, today=None, days=DEFAULT_DAYS):
    """Resolve the half-open [since, until) window. `until` defaults to tomorrow so
    that bugs raised today are included."""
    today = today or date.today()
    end = date.fromisoformat(until) if until else today + timedelta(days=1)
    start = date.fromisoformat(since) if since else end - timedelta(days=days)
    if start >= end:
        raise ValueError(f"--since {start} must be before --until {end}")
    return start.isoformat(), end.isoformat()


def build_jql(projects, since, until):
    # "Sub-bug" is quoted: the hyphen breaks an unquoted JQL term.
    return (f'project in ({", ".join(projects)}) '
            f'AND issuetype in (Bug, "Sub-bug") '
            f'AND created >= "{since}" AND created < "{until}" '
            f'ORDER BY created DESC')


def _name(node):
    return (node or {}).get("name") or None


def _display(node):
    return (node or {}).get("displayName") or None


def normalize(issue):
    fields = issue.get("fields") or {}
    components = fields.get("components") or []
    status = fields.get("status") or {}
    return {
        "key": issue.get("key"),
        "area": area_of(fields),
        "component": _name(components[0]) if components else None,
        "summary": fields.get("summary") or "",
        "excerpt": excerpt(flatten_adf(fields.get("description"))),
        "issuetype": _name(fields.get("issuetype")),
        "status": _name(status),
        "status_category": ((status.get("statusCategory") or {}).get("key")) or None,
        "resolution": _name(fields.get("resolution")),
        "created": (fields.get("created") or "")[:10],
        "assignee": _display(fields.get("assignee")),
        "reporter": _display(fields.get("reporter")),
        "labels": list(fields.get("labels") or []),
        "priority": _name(fields.get("priority")),
        "parent": (fields.get("parent") or {}).get("key"),
        "url": f"{BASE}/browse/{issue.get('key')}",
    }


def areas_in_scope(repo):
    return {"portal": {"portal"}, "core": {"core"}, "both": {"portal", "core"}}[repo]


def collect(client, jql, repo):
    """Fetch, filter and normalise. Bugs of the area NOT in scope are excluded;
    bugs with no resolvable area are always kept, so the loss stays visible."""
    scope = areas_in_scope(repo)
    bugs, fetched, dropped = [], 0, 0
    for issue in client.search(jql, FIELDS):
        fetched += 1
        fields = issue.get("fields") or {}
        if not is_real_defect(fields):
            dropped += 1
            continue
        record = normalize(issue)
        if record["area"] is None or record["area"] in scope:
            bugs.append(record)
    return {"repo": repo, "fetched": fetched, "dropped_invalid": dropped, "bugs": bugs}


def classify_rows(document):
    """The compact lines the model reads. Unclassified bugs are not classified —
    they can never join a cluster, so spending context on them is waste."""
    return [{"key": b["key"], "summary": b["summary"], "excerpt": b["excerpt"],
             "component": b["component"], "labels": b["labels"]}
            for b in document["bugs"] if b["area"] is not None]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch and area-tag a window of Jira bugs.")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--repo", default="portal", choices=["portal", "core", "both"])
    parser.add_argument("--out-bugs", required=True)
    parser.add_argument("--out-classify", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = JiraClient()
    except (MissingToken, ValueError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    projects = [p.strip() for p in args.project.split(",") if p.strip()]
    document = collect(client, build_jql(projects, since, until), args.repo)
    document["window"] = {"since": since, "until": until}
    document["projects"] = projects

    with open(args.out_bugs, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    with open(args.out_classify, "w", encoding="utf-8") as handle:
        for row in classify_rows(document):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    kept = len(document["bugs"])
    unclassified = sum(1 for b in document["bugs"] if b["area"] is None)
    sys.stderr.write(
        f"Analysing {', '.join(projects)} bugs, {args.repo}, {since} → {until}\n"
        f"  fetched {document['fetched']}, dropped-invalid {document['dropped_invalid']}, "
        f"kept {kept} ({unclassified} with no resolvable area)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

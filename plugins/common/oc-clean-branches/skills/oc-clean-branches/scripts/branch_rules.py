#!/usr/bin/env python3
"""Pure guard rules for /oc-clean-branches. No I/O here, so every rule is unit-tested.

A branch older than --before is only a *candidate*. It is deleted only if it passes all
five guards, and every guard fails SAFE: anything that cannot be decided (no ticket key,
an unreadable ticket, a failed API call) excludes the branch rather than admitting it.

  R1 protected   structural name, version branch, or covered by a branch restriction
  R2 open-pr     source or destination of an OPEN pull request
  R3 unmerged    commits?include=<tip>&exclude=<target> still returns commits
  R4 recent      tip commit newer than today - --recent-days
  R5 ticket-type no ticket key, unreadable ticket, or type not Bug/Sub-bug/Task/Sub-task
"""
import fnmatch
import re
from datetime import datetime, timezone

RULES = {
    "R1": "protected / structural branch",
    "R2": "open pull request",
    "R3": "not fully merged into its target",
    "R4": "recent commit",
    "R5": "ticket missing or not Bug / Sub-bug / Task / Sub-task",
    "ERR": "a guard check failed (fail-safe)",
}

STRUCTURAL_NAMES = {"master", "main", "develop", "dev", "development", "production",
                    "staging", "integration"}
STRUCTURAL_PREFIXES = ("release/", "releases/", "release-", "support/")
# 19.0.x, 14.1.0, v15, 15.x, 19.0.x-hotfix are version lines, never ticket branches.
VERSION_RE = re.compile(r"^(v?\d+(\.(\d+|x))+|v\d+)([-_].*)?$", re.I)
TICKET_RE = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]+-\d+)(?!\d)")
ALLOWED_TYPES = {"bug", "subbug", "task", "subtask"}


def parse_ts(value):
    """Bitbucket and Jira timestamps -> aware UTC datetime."""
    text = value.strip().replace("Z", "+00:00")
    # Jira writes +0000 without a colon; fromisoformat accepts it from 3.11 only.
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def day_start(date_text):
    """YYYY-MM-DD -> 00:00 UTC of that day."""
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def structural_reason(name):
    """R1 by name alone. Returns a reason string, or None."""
    lower = name.lower()
    if lower in STRUCTURAL_NAMES:
        return f"structural branch `{name}`"
    if lower.startswith(STRUCTURAL_PREFIXES):
        return f"release / support branch `{name}`"
    if VERSION_RE.match(lower) or VERSION_RE.match(lower.rsplit("/", 1)[-1]):
        return f"version branch `{name}`"
    return None


def restriction_patterns(restrictions, model):
    """Resolve Bitbucket branch restrictions to fnmatch globs.

    A restriction is either a glob (`pattern`) or a branching-model branch type
    (`branch_type`: development, production, feature, release, ...). The model maps a
    type to a single branch name (development/production) or to a prefix.
    Raises ValueError when a branching-model restriction cannot be resolved: an
    unresolvable restriction must stop the repository, not be silently ignored.
    """
    model = model or {}
    prefixes = {t.get("kind"): t.get("prefix") for t in model.get("branch_types") or []}
    globs = set()
    for item in restrictions:
        kind = item.get("branch_match_kind") or "glob"
        if kind == "glob":
            if item.get("pattern"):
                globs.add(item["pattern"])
            continue
        btype = item.get("branch_type")
        if btype in ("development", "production"):
            branch = ((model.get(btype) or {}).get("branch") or {}).get("name") \
                or (model.get(btype) or {}).get("name")
            if not branch:
                raise ValueError(f"branch restriction on model type `{btype}` "
                                 "but the branching model names no such branch")
            globs.add(branch)
        elif prefixes.get(btype):
            globs.add(prefixes[btype] + "*")
        else:
            raise ValueError(f"branch restriction on model type `{btype}` "
                             "has no prefix in the branching model")
    return sorted(globs)


def restricted_by(name, globs):
    for glob in globs:
        if fnmatch.fnmatchcase(name, glob):
            return glob
    return None


def ticket_key(name):
    """First Jira key in the branch name: fix/INTRD-123-foo -> INTRD-123."""
    match = TICKET_RE.search(name.upper())
    return match.group(1) if match else None


def normalise_type(issuetype):
    return re.sub(r"[^a-z]", "", (issuetype or "").lower())


def type_allowed(issuetype):
    return normalise_type(issuetype) in ALLOWED_TYPES

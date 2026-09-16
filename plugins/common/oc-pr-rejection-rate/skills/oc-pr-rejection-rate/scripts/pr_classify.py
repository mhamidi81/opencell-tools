#!/usr/bin/env python3
"""Stage 2 of /oc-pr-rejection-rate: apply the three rejection rules.

Pure — JSON in, JSON out. No network, no clock, no environment. That boundary is what
lets the rules be tested offline, and the rules are the only thing that decides whether
the published percentage is right.

A PR is rejected if ANY rule fires, and it counts ONCE in the rejected total. The
per-reason counters are diagnostic and may sum past it; the report says so.

R1 and R2 read documented, stable fields. R3 does not: how Bitbucket represents a draft
transition is resolved at runtime into one of three declared modes, and the mode travels
with the model so a zero can never be misread as "nobody was re-drafted" when it means
"we could not tell". See the spec's section 4.
"""
import argparse
import json

REASONS = ("declined", "changes_requested", "redrafted")


def is_declined(pr):
    """R1 — the reviewer declined the PR outright."""
    return pr.get("state") == "DECLINED"


def had_changes_requested(pr):
    """R2 — changes were requested at any point.

    Deliberately historical. A reviewer who requests changes and later approves clears
    the participant flag, but the PR was still sent back; reading current state alone
    would lose most of the signal. The participant fallback only matters when the
    activity feed could not be read.
    """
    for entry in pr.get("activity") or []:
        if "changes_requested" in entry:
            return True
    return any(p.get("state") == "changes_requested" for p in pr.get("participants") or [])


def _coerce_draft(value):
    """Draft flags must be real booleans.

    Anything else — a JSON string, a nested object, a number — is a shape this
    code does not understand, and the honest answer is "no draft data", which
    degrades the detection mode. Coercing with bool() would instead report a
    confident zero for R3: bool("false") is True, so a feed using string values
    would score every PR as never re-drafted while the model still claimed mode
    "activity". That is the exact failure the mode mechanism exists to prevent.
    """
    return value if isinstance(value, bool) else None


def _entry_draft(payload):
    """The draft flag an update entry leaves behind, or None if it says nothing.

    Two shapes are accepted because Bitbucket's own is not contractual: an explicit
    `changes.draft` with old/new, and a plain `draft` snapshot boolean.
    """
    changes = payload.get("changes") or {}
    change = changes.get("draft")
    if isinstance(change, dict) and "new" in change:
        return _coerce_draft(change["new"])
    return _coerce_draft(payload.get("draft"))


def _entry_draft_old(payload):
    changes = payload.get("changes") or {}
    change = changes.get("draft")
    if not isinstance(change, dict):
        return None
    if "old" in change:
        old = _coerce_draft(change["old"])
        if old is not None:
            return old
    # A `changes` entry means the value CHANGED, so a missing or unreadable `old`
    # is still recoverable: for a boolean, the previous value is the negation.
    new = _coerce_draft(change.get("new"))
    return None if new is None else not new


def draft_states(activity):
    """The draft flag after each update entry, oldest first.

    Returns None when the feed carries no draft data at all — which is the signal that
    R3 must fall back to a coarser mode rather than silently report zero.
    """
    states = []
    for entry in activity or []:
        payload = entry.get("update")
        if payload is None:
            continue
        new = _entry_draft(payload)
        if new is None:
            continue
        if not states:
            old = _entry_draft_old(payload)
            if old is not None:
                states.append(old)
        states.append(new)
    return states or None


def was_redrafted(pr, mode):
    """R3 — the PR moved ready -> draft at least once.

    A PR opened as a draft and later made ready is ordinary work in progress, not a
    rejection, which is why the initial state is read rather than assumed.
    """
    if mode == "unavailable":
        return False
    if mode == "activity":
        states = draft_states(pr.get("activity"))
        if states is None:
            return False
        return any(not before and after for before, after in zip(states, states[1:]))
    if mode != "current-flag":
        # An unrecognised mode is not a value build_model ever produces; the safe
        # default for a rule that cannot be evaluated is False, not a silent True.
        return False
    # current-flag: the PR is a draft now and was worked on after it was opened. The
    # first update entry is the creation, so a lone entry proves nothing.
    updates = [e for e in pr.get("activity") or [] if "update" in e]
    return bool(pr.get("draft")) and len(updates) > 1


def detect_draft_mode(document):
    """Resolve, from the data actually returned, how R3 can be evaluated."""
    prs = [pr for repo in document.get("repos", {}).values()
           for pr in repo.get("pull_requests") or []]
    if any(draft_states(pr.get("activity")) is not None for pr in prs):
        return "activity"
    if any("draft" in pr for pr in prs):
        return "current-flag"
    return "unavailable"


def classify_pr(pr, mode):
    declined = is_declined(pr)
    changes = had_changes_requested(pr)
    # A PR whose activity feed failed to load cannot be judged under the exact
    # mode, whatever the rest of the document supports. Fall back to the coarse
    # proxy for this PR rather than reporting an un-evaluated rule as False, and
    # record the degradation so the CSV — the audit surface — shows it.
    activity_ok = not pr.get("warnings")
    pr_mode = "current-flag" if mode == "activity" and not activity_ok else mode
    redrafted = was_redrafted(pr, pr_mode)
    return {
        "id": pr.get("id"),
        "title": pr.get("title") or "",
        "author": (pr.get("author") or {}).get("display_name") or "",
        "created_on": pr.get("created_on") or "",
        "state": pr.get("state") or "",
        "url": ((pr.get("links") or {}).get("html") or {}).get("href") or "",
        "rejected": declined or changes or redrafted,
        "r_declined": declined,
        "r_changes_requested": changes,
        "r_redrafted": redrafted,
        "activity_ok": activity_ok,
    }


def _rate(rejected, total):
    """None, not 0.0, for an empty repository — the two mean different things."""
    return round(100.0 * rejected / total, 1) if total else None


def build_model(document):
    mode = detect_draft_mode(document)
    repos, warnings = {}, []
    grand_total = grand_rejected = 0
    for slug, payload in document.get("repos", {}).items():
        rows = [classify_pr(pr, mode) for pr in payload.get("pull_requests") or []]
        for pr in payload.get("pull_requests") or []:
            warnings.extend(f"{slug} PR {pr.get('id')}: {w}" for w in pr.get("warnings") or [])
        rejected = sum(1 for r in rows if r["rejected"])
        repos[slug] = {
            "total": len(rows),
            "rejected": rejected,
            "rate": _rate(rejected, len(rows)),
            "reasons": {reason: sum(1 for r in rows if r[f"r_{reason}"]) for reason in REASONS},
            "prs": rows,
        }
        grand_total += len(rows)
        grand_rejected += rejected
    return {
        "window": document.get("window", {}),
        "workspace": document.get("workspace", ""),
        "draft_detection": mode,
        "repos": repos,
        "totals": {"total": grand_total, "rejected": grand_rejected,
                   "rate": _rate(grand_rejected, grand_total)},
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply the rejection rules to a fetched document.")
    parser.add_argument("--document", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.document) as handle:
        model = build_model(json.load(handle))
    with open(args.out, "w") as handle:
        json.dump(model, handle, indent=2)
    print(f"draft detection mode: {model['draft_detection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

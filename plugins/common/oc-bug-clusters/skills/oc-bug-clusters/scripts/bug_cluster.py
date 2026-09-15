#!/usr/bin/env python3
"""Stage 4 of /oc-bug-clusters: bugs + subject assignments -> the cluster model.

No network, no rendering. The model is the one shape the Markdown/CSV/HTML
renderers and the Jira writer all read, so it is built once and asserted here.
"""
import re
from collections import Counter

from bug_fetch import AREA_COMPONENT

AREA_ORDER = ["portal", "core"]
SUBJECT_HEADING = re.compile(r"^## ([a-z0-9-]+)$", re.M)
TOP_LABELS = 3


class MissingAssignments(RuntimeError):
    """A classifiable bug came back with no subject.

    Raised rather than dropped: a silently missing bug is one that never reaches a
    cluster and never reaches the report, which is indistinguishable from a bug that
    genuinely had no peers.
    """

    def __init__(self, keys):
        self.keys = list(keys)
        shown = ", ".join(self.keys[:10])
        more = f" (+{len(self.keys) - 10} more)" if len(self.keys) > 10 else ""
        super().__init__(f"no subject assigned for: {shown}{more}")


def seeded_subjects(path):
    with open(path, encoding="utf-8") as handle:
        return SUBJECT_HEADING.findall(handle.read())


def _group(subject, bugs, seeded):
    bugs = sorted(bugs, key=lambda b: (b["created"], b["key"]), reverse=True)
    labels = Counter(label for b in bugs for label in b["labels"])
    dates = sorted(b["created"] for b in bugs if b["created"])
    closed = sum(1 for b in bugs if b["status_category"] == "done")
    return {
        "subject": subject,
        "count": len(bugs),
        "bugs": bugs,
        "open": len(bugs) - closed,
        "closed": closed,
        "labels": [[name, n] for name, n in labels.most_common(TOP_LABELS)],
        "first_created": dates[0] if dates else "",
        "last_created": dates[-1] if dates else "",
        "is_new": subject not in set(seeded),
    }


def build_model(document, assignments, min_cluster, seeded=()):
    bugs = document["bugs"]
    classifiable = [b for b in bugs if b["area"] is not None]
    missing = [b["key"] for b in classifiable if b["key"] not in assignments]
    if missing:
        raise MissingAssignments(missing)

    scope = [a for a in AREA_ORDER
             if a in {"portal": {"portal"}, "core": {"core"},
                      "both": {"portal", "core"}}[document["repo"]]]

    areas = {}
    for area in scope:
        mine = [b for b in classifiable if b["area"] == area]
        by_subject = {}
        for b in mine:
            by_subject.setdefault(assignments[b["key"]], []).append(b)
        groups = [_group(subject, members, seeded)
                  for subject, members in by_subject.items()]
        groups.sort(key=lambda g: (-g["count"], g["subject"]))
        clusters = [g for g in groups if g["count"] >= min_cluster]
        areas[area] = {
            "component": AREA_COMPONENT[area],
            "bugs": len(mine),
            "clustered_bugs": sum(g["count"] for g in clusters),
            "clusters": clusters,
            "near": [g for g in groups if g["count"] < min_cluster],
        }

    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "min_cluster": min_cluster,
        "fetched": document["fetched"],
        "dropped_invalid": document["dropped_invalid"],
        "kept": len(bugs),
        "areas": areas,
        "unclassified": sorted((b for b in bugs if b["area"] is None),
                               key=lambda b: b["key"]),
    }

#!/usr/bin/env python3
"""Stage 4 of /oc-bug-root-causes: assignments + evidence -> the ranking model -> reports.

No network. The classification is the only LLM judgement in the command, and it arrives
in several parts (one per sub-agent batch), so this module refuses to report on anything
it cannot account for: a missing key, a key outside the run, a key classified two ways,
or a coined category too small to be one. A silently missing bug would look exactly like
a category that did not happen.
"""
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
from collections import Counter
from datetime import date

from bug_fetch import areas_in_scope

INSUFFICIENT = "insufficient-evidence"
MIN_NEW = 5
CAUSE_LIMIT = 120
EXAMPLES = 5
AREA_ORDER = ["portal", "core"]
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
NEW_DEFINITION = "New category coined in this run — add it to references/dev-root-causes.md."


class AssignmentError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def load_taxonomy(path):
    """Ordered {name: definition}; the definition is the first paragraph under the heading."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    taxonomy = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        name = heading.strip()
        if not KEBAB.fullmatch(name):
            continue
        paragraph = body.strip().split("\n\n", 1)[0]
        taxonomy[name] = " ".join(paragraph.split())
    return taxonomy


def _shown(keys):
    keys = list(keys)
    more = f" (+{len(keys) - 10} more)" if len(keys) > 10 else ""
    return ", ".join(keys[:10]) + more


def merge_assignments(parts):
    merged, conflicts = {}, set()
    for part in parts:
        for key, value in part.items():
            if key in merged and merged[key] != value:
                conflicts.add(key)
            merged[key] = value
    if conflicts:
        raise AssignmentError([f"classified differently in two parts: {_shown(sorted(conflicts))}"])
    return merged


def validate(keys, assignments, taxonomy, min_new=MIN_NEW):
    """Raise AssignmentError listing every problem; return the new categories."""
    problems = []
    known = set(keys)
    missing = [k for k in keys if k not in assignments]
    if missing:
        problems.append(f"no category assigned for: {_shown(missing)}")
    outside = sorted(k for k in assignments if k not in known)
    if outside:
        problems.append(f"assignments for bugs not in this run: {_shown(outside)}")

    coined = Counter()
    for key in keys:
        if key not in assignments:
            continue
        entry = assignments[key]
        if not isinstance(entry, dict):
            problems.append(f"{key}: the assignment must be an object")
            continue
        category = entry.get("category")
        if not isinstance(category, str) or not KEBAB.fullmatch(category):
            problems.append(f"{key}: category must be lower-kebab-case, got {category!r}")
        elif category not in taxonomy:
            coined[category] += 1
        if entry.get("confidence") not in ("high", "low"):
            problems.append(f"{key}: confidence must be 'high' or 'low'")
        if not isinstance(entry.get("regression"), bool):
            problems.append(f"{key}: regression must be true or false")
        cause = entry.get("cause")
        if not isinstance(cause, str) or not cause.strip():
            problems.append(f"{key}: cause must be a non-empty line")

    for category, count in sorted(coined.items()):
        if count < min_new:
            problems.append(f"unknown category '{category}' on {count} bug(s): use a seeded "
                            f"category, or coin a new one only for >= {min_new} bugs")
    if problems:
        raise AssignmentError(problems)
    return sorted(coined)


def _merge(bugs, rows, assignments):
    evidence = {r["key"]: r for r in rows}
    merged = []
    for b in bugs:
        entry = assignments[b["key"]]
        row = evidence.get(b["key"]) or {}
        merged.append({**b, "category": entry["category"], "confidence": entry["confidence"],
                       "regression": entry["regression"],
                       "cause": entry["cause"].strip()[:CAUSE_LIMIT],
                       "evidence": row.get("evidence") or "jira",
                       "pr_url": row.get("pr_url")})
    return merged


def _examples(members):
    newest = sorted(members, key=lambda b: (b["created"], b["key"]), reverse=True)
    return sorted(newest, key=lambda b: b["evidence"] != "pr")[:EXAMPLES]


def ranking(bugs, taxonomy, new=()):
    total = len(bugs)
    groups = {}
    for b in bugs:
        groups.setdefault(b["category"], []).append(b)
    rows = []
    for category, members in groups.items():
        count = len(members)
        regressions = sum(1 for b in members if b["regression"])
        rows.append({
            "category": category,
            "definition": taxonomy.get(category, NEW_DEFINITION),
            "is_new": category in set(new),
            "count": count,
            "share": count / total if total else 0.0,
            "areas": {"portal": sum(1 for b in members if b["area"] == "portal"),
                      "core": sum(1 for b in members if b["area"] == "core"),
                      "none": sum(1 for b in members if b["area"] is None)},
            "regression": regressions,
            "regression_rate": regressions / count,
            "evidence": {"pr": sum(1 for b in members if b["evidence"] == "pr"),
                         "jira": sum(1 for b in members if b["evidence"] != "pr")},
            "low_confidence": sum(1 for b in members if b["confidence"] == "low"),
            "examples": _examples(members),
        })
    rows.sort(key=lambda r: (r["category"] == INSUFFICIENT, -r["count"], r["category"]))
    return rows


def build_model(document, rows, assignments, taxonomy, new=()):
    bugs = _merge(document["bugs"], rows, assignments)
    views = {"all": ranking(bugs, taxonomy, new)}
    for area in AREA_ORDER:
        if area in areas_in_scope(document["repo"]):
            views[area] = ranking([b for b in bugs if b["area"] == area], taxonomy, new)
    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "total": len(bugs),
        "evidence": {"pr": sum(1 for b in bugs if b["evidence"] == "pr"),
                     "jira": sum(1 for b in bugs if b["evidence"] != "pr")},
        "regression": sum(1 for b in bugs if b["regression"]),
        "new_categories": list(new),
        "views": views,
        "insufficient": sorted((b for b in bugs if b["category"] == INSUFFICIENT),
                               key=lambda b: (b["created"], b["key"]), reverse=True),
        "no_area": [b for b in bugs if b["area"] is None],
        "bugs": bugs,
    }

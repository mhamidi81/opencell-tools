#!/usr/bin/env python3
"""Stage 2 of /oc-bug-root-causes: attach each bug's fixing-PR diff as evidence.

Deterministic. For every bug it finds the pull request that fixed it, keeps a trimmed
diff plus a per-file line count, and writes the classifier's input in batch files.

Two Bitbucket costs shape this module:
  * one PR search per repository per bug (title OR branch in a single `q`), and the file
    list is computed from the diff rather than a separate diffstat call — a 280-bug
    window stays near 600 requests, inside the hourly rate limit;
  * the diff endpoint answers 302 to a signed URL on another host. The redirect is
    followed by hand so the Authorization header is only sent to the host that issued
    the request.

A bug whose lookup fails is never dropped: it falls back to Jira-only evidence and says
so. Only a 401 stops the stage, because every later call would fail the same way.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from bitbucket_client import BASE, BitbucketClient, BitbucketError, MissingToken, auth_header

WORKSPACE = "opencellsoft"
REPOS = {"portal": ["opencell-portal"], "core": ["opencell-core"],
         None: ["opencell-portal", "opencell-core"]}
# Without an explicit state Bitbucket lists OPEN PRs only, and a fix is usually MERGED.
PR_STATES = ["MERGED", "OPEN", "DECLINED", "SUPERSEDED"]
DIFF_CAP = 4096
FILESTAT_CAP = 40
BATCH_SIZE = 30

# Tests, lockfiles, translations and build output say nothing about the mistake and
# would eat the 4 KB budget first. They still appear in the per-file list.
EXCLUDED = [re.compile(p) for p in (
    r"(^|/)src/test/", r"(^|/)__tests__/", r"(^|/)tests?/(e2e|support)/",
    r"\.(test|spec)\.[cm]?[jt]sx?$", r"\.snap$",
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$",
    r"(^|/)(i18n|locales)/", r"\.min\.(js|css)$", r"(^|/)(dist|build|generated)/",
)]
FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
TRUNCATED = "\n… [diff truncated at {cap} bytes]\n"


def _key_pattern(key):
    # `~` in a Bitbucket query is a substring match: INTRD-4516 also finds INTRD-45162.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(key)}(?![0-9])", re.I)


def mentions(pr, key):
    pattern = _key_pattern(key)
    title = pr.get("title") or ""
    branch = ((pr.get("source") or {}).get("branch") or {}).get("name") or ""
    return bool(pattern.search(title) or pattern.search(branch))


def select_pr(prs):
    """Merged into dev, else the newest merged, else the newest of any state.
    A fix merged to several branches has one PR per branch; the dev one is canonical."""
    def dest(p):
        return ((p.get("destination") or {}).get("branch") or {}).get("name")

    merged = [p for p in prs if p.get("state") == "MERGED"]
    for pool in ([p for p in merged if dest(p) == "dev"], merged, list(prs)):
        if pool:
            return max(pool, key=lambda p: p.get("updated_on") or "")
    return None


def is_excluded(path):
    return any(p.search(path) for p in EXCLUDED)


def split_diff(text):
    """[(path, chunk)] in file order; text before the first header is dropped."""
    starts = [m.start() for m in FILE_HEADER.finditer(text or "")]
    chunks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        chunks.append((FILE_HEADER.match(chunk).group(2), chunk))
    return chunks


def trim_diff(text, cap=DIFF_CAP):
    kept = "".join(chunk for path, chunk in split_diff(text) if not is_excluded(path))
    data = kept.encode("utf-8")
    if len(data) <= cap:
        return kept
    return data[:cap].decode("utf-8", "ignore") + TRUNCATED.format(cap=cap)


def diff_filestats(text):
    out = []
    for path, chunk in split_diff(text):
        lines = chunk.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        out.append(f"{path} +{added} -{removed}")
    if len(out) > FILESTAT_CAP:
        out = out[:FILESTAT_CAP] + [f"… {len(out) - FILESTAT_CAP} more files"]
    return out


def jira_evidence(note):
    return {"evidence": "jira", "pr_url": None, "pr_title": None, "files": [], "diff": "",
            "note": note}


def write_batches(rows, directory, size=BATCH_SIZE):
    """One classify.NNN.jsonl per `size` rows. Stale files from a larger earlier run are
    removed first, or a sub-agent would classify bugs that are no longer in the window."""
    os.makedirs(directory, exist_ok=True)
    for stale in glob.glob(os.path.join(directory, "classify.*.jsonl")):
        os.remove(stale)
    paths = []
    for start in range(0, len(rows), size):
        path = os.path.join(directory, f"classify.{start // size + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows[start:start + size]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        paths.append(path)
    return paths

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


MAX_ATTEMPTS = 5
RETRY_STATUS = (429, 503)
REDIRECT_STATUS = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 3
AUTH_HINT = (" — the credential was rejected. An ATCTT... repository/workspace Access "
             "Token must be sent as `Authorization: Bearer` with no email; an ATATT... "
             "Atlassian API token must be sent as Basic email:token. Check "
             "BITBUCKET_ACCESS_TOKEN's prefix and that BITBUCKET_EMAIL is set only for "
             "the ATATT form.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as HTTPError so get_raw decides which headers travel."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class EvidenceFetcher:
    def __init__(self, client, opener=None, auth=None, workspace=WORKSPACE, sleep=time.sleep):
        self.client = client
        self._open = opener or urllib.request.build_opener(_NoRedirect).open
        self._auth = auth
        self._sleep = sleep
        self.workspace = workspace

    def get_raw(self, url):
        """GET a non-JSON body. urllib would forward Authorization to the signed URL's
        host; this sends it only while the host is unchanged, as curl -L does."""
        origin = urllib.parse.urlsplit(url).netloc
        hops = attempts = 0
        while True:
            same_host = urllib.parse.urlsplit(url).netloc == origin
            headers = {"Authorization": self._auth} if (same_host and self._auth) else {}
            request = urllib.request.Request(url, method="GET", headers=headers)
            label = urllib.parse.urlsplit(url).path
            try:
                with self._open(request, timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as ex:
                if ex.code in REDIRECT_STATUS and hops < MAX_REDIRECTS:
                    location = ex.headers.get("Location") if ex.headers else None
                    if not location:
                        raise BitbucketError(f"HTTP {ex.code} without Location on GET {label}") from ex
                    url = urllib.parse.urljoin(url, location)
                    hops += 1
                    continue
                if ex.code in RETRY_STATUS and attempts < MAX_ATTEMPTS - 1:
                    attempts += 1
                    self._sleep(2 * attempts)
                    continue
                detail = ex.read()[:200].decode("utf-8", "replace")
                if ex.code == 401:
                    detail += AUTH_HINT
                raise BitbucketError(f"HTTP {ex.code} on GET {label}: {detail}") from ex

    def candidates(self, slug, key):
        query = f'(title ~ "{key}" OR source.branch.name ~ "{key}")'
        found = self.client.paginate(f"/repositories/{self.workspace}/{slug}/pullrequests",
                                     {"q": query, "state": PR_STATES, "pagelen": 50})
        return [dict(p, _slug=slug) for p in found if mentions(p, key)]

    def evidence_for(self, bug):
        key = bug["key"]
        prs = [p for slug in REPOS[bug.get("area")] for p in self.candidates(slug, key)]
        chosen = select_pr(prs)
        if chosen is None:
            return jira_evidence("no PR found")
        slug = chosen["_slug"]
        raw = self.get_raw(f"{BASE}/repositories/{self.workspace}/{slug}"
                           f"/pullrequests/{chosen['id']}/diff")
        diff = raw.decode("utf-8", "replace")
        html = (((chosen.get("links") or {}).get("html") or {}).get("href")
                or f"https://bitbucket.org/{self.workspace}/{slug}/pull-requests/{chosen['id']}")
        return {"evidence": "pr", "pr_url": html, "pr_title": chosen.get("title") or "",
                "files": diff_filestats(diff), "diff": trim_diff(diff), "note": None}


def gather_all(bugs, fetcher, cache_dir, warn=sys.stderr.write,
               disabled_reason="PR lookup disabled"):
    """Evidence for every bug, in order. Only PR evidence is cached: a Jira-only
    fallback is retried on the next run, when a token or a merged PR may exist."""
    os.makedirs(cache_dir, exist_ok=True)
    results = {}
    for bug in bugs:
        key = bug["key"]
        if fetcher is None:
            results[key] = jira_evidence(disabled_reason)
            continue
        path = os.path.join(cache_dir, f"{key}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                results[key] = json.load(handle)
            continue
        try:
            evidence = fetcher.evidence_for(bug)
        except BitbucketError as ex:
            if str(ex).startswith("HTTP 401"):
                warn(f"WARNING: Bitbucket rejected the credential; continuing Jira-only.\n{ex}\n")
                fetcher, disabled_reason = None, "Bitbucket 401"
                results[key] = jira_evidence(disabled_reason)
                continue
            warn(f"WARNING: PR lookup failed for {key}: {ex}\n")
            results[key] = jira_evidence("PR lookup failed")
            continue
        if evidence["evidence"] == "pr":
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(evidence, handle, ensure_ascii=False)
        results[key] = evidence
    return results


def classify_rows(bugs, evidence):
    rows = []
    for b in bugs:
        ev = evidence[b["key"]]
        rows.append({"key": b["key"], "area": b["area"], "summary": b["summary"],
                     "excerpt": b["excerpt"], "comments": b["comments"],
                     "evidence": ev["evidence"], "pr_url": ev["pr_url"],
                     "pr_title": ev["pr_title"], "files": ev["files"], "diff": ev["diff"]})
    return rows


def main(argv=None, fetcher_factory=None, warn=sys.stderr.write):
    parser = argparse.ArgumentParser(description="Attach fixing-PR evidence to each bug.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--run", required=True, help="run directory (cache and batches)")
    parser.add_argument("--out-classify", required=True)
    parser.add_argument("--no-pr", action="store_true")
    parser.add_argument("--workspace", default=WORKSPACE)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        bugs = json.load(handle)["bugs"]

    fetcher, reason = None, "--no-pr"
    if not args.no_pr:
        factory = fetcher_factory or (lambda: EvidenceFetcher(
            BitbucketClient(), auth=auth_header(), workspace=args.workspace))
        try:
            fetcher = factory()
        except MissingToken as ex:
            warn(f"WARNING: {ex}\nContinuing with Jira-only evidence.\n")
            reason = "no Bitbucket token"

    evidence = gather_all(bugs, fetcher, os.path.join(args.run, "pr"), warn=warn,
                          disabled_reason=reason)
    rows = classify_rows(bugs, evidence)
    with open(args.out_classify, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    batches = write_batches(rows, os.path.join(args.run, "batches"), args.batch_size)

    with_pr = sum(1 for r in rows if r["evidence"] == "pr")
    sys.stderr.write(f"PR evidence for {with_pr} of {len(rows)} bugs; "
                     f"{len(batches)} batch file(s) in {os.path.join(args.run, 'batches')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

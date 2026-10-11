#!/usr/bin/env python3
"""Fetch the failed stage's log from a Jenkins build and classify the failure.

Source order (both verified on the live `dev` job):
  step-log  the stage's FAILED step nodes (`execution/node/<id>/wfapi/log`); each
            returns the last ~10 KB of that step, which is where an error lands.
            A stage node's own wfapi/log is empty, so the steps must be walked.
  console   `consoleText` sliced from `[Pipeline] { (<stage>)` to the next stage marker.

Classification (code wins over infra when both match):
  code     a compiler / bundler / linter error a source change can fix
  infra    network, disk, agent, ssh/scp — rebuild only, never a code change
  unknown  neither; the skill reproduces locally before touching anything
"""
import argparse
import html
import json
import re
import sys

from jenkins_common import JenkinsError, client_from_env, fail, job_path

STAGE_MARK = "[Pipeline] { ("

ERROR_PATTERNS = [
    r"error TS\d+", r"\bERROR\b", r"Error:", r"✘", r"✖", r"npm ERR!", r"ERR_PNPM",
    r"error Command failed", r"Could not resolve", r"FATAL ERROR",
    r"script returned exit code [1-9]", r"^\s*\d+:\d+\s+error\s",
]
CODE_PATTERNS = [
    r"error TS\d+", r"Could not resolve", r"is not exported by", r"Module not found",
    r"SyntaxError", r"\[vite\]", r"\[plugin:", r"Transform failed", r"Rollup failed",
    r"^\s*\d+:\d+\s+error\s", r"✖ \d+ problems?",
]
INFRA_PATTERNS = [
    r"ETIMEDOUT", r"ECONNRESET", r"ECONNREFUSED", r"ENOTFOUND", r"EAI_AGAIN", r"ENOSPC",
    r"No space left on device", r"socket hang up", r"Could not read from remote repository",
    r"Host key verification failed", r"Permission denied \(publickey", r"Authentication failed",
    r"ChannelClosedException", r"RemovedNodeListener", r"[Aa]gent .* (went offline|disconnected)",
    r"Cannot contact ", r"\b50[234] (Bad Gateway|Service Unavailable|Gateway Time-?out)",
    r"lost connection",
]
ERROR_RE = [re.compile(p, re.M) for p in ERROR_PATTERNS]
CODE_RE = [re.compile(p, re.M) for p in CODE_PATTERNS]
INFRA_RE = [re.compile(p, re.M) for p in INFRA_PATTERNS]
HTML_HINTS = ("&lt;", "&gt;", "&amp;", "&quot;", "&#39;", "<span", "<a ")


def clean(text):
    """wfapi can return HTML-escaped text with console-note spans. Only text that
    looks escaped is touched, so a plain `Array<string>` is never mangled."""
    if not any(h in text for h in HTML_HINTS):
        return text
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def slice_console(text, stage):
    start = text.find(STAGE_MARK + stage + ")")
    if start < 0:
        return ""
    nxt = text.find(STAGE_MARK, start + 1)
    return text[start:nxt if nxt >= 0 else len(text)]


def error_lines(text, limit=60):
    seen, out = set(), []
    for line in text.splitlines():
        s = line.rstrip()
        if s and s not in seen and any(p.search(s) for p in ERROR_RE):
            seen.add(s)
            out.append(s)
            if len(out) >= limit:
                break
    return out


def classify(text):
    if any(p.search(text) for p in CODE_RE):
        return "code"
    if any(p.search(text) for p in INFRA_RE):
        return "infra"
    return "unknown"


def tail(text, n):
    return "\n".join(text.splitlines()[-n:])


def stage_log(client, branch, build, stage_id, stage_name):
    base = f"{job_path(branch)}/{build}"
    if stage_id:
        nodes = client.get_json(f"{base}/execution/node/{stage_id}/wfapi/describe") \
            .get("stageFlowNodes") or []
        picked = [n for n in nodes if n.get("status") == "FAILED"] or nodes[-3:]
        parts = []
        for node in picked:
            text = client.get_json(f"{base}/execution/node/{node['id']}/wfapi/log").get("text") or ""
            if text.strip():
                parts.append(clean(text))
        if parts:
            return "\n".join(parts), "step-log"
    return slice_console(clean(client.get_text(f"{base}/consoleText")), stage_name), "console"


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description="Failed-stage log excerpt and classification.")
    parser.add_argument("--branch", default="dev")
    parser.add_argument("--build", type=int, required=True)
    parser.add_argument("--stage", required=True, help="stage name, e.g. 'Build Front'")
    parser.add_argument("--stage-id", default=None, help="stage node id from jenkins_status.py")
    parser.add_argument("--tail", type=int, default=300, help="excerpt length in lines")
    args = parser.parse_args(argv)
    try:
        client = client or client_from_env()
        text, source = stage_log(client, args.branch, args.build, args.stage_id, args.stage)
    except JenkinsError as e:
        return fail(e)
    print(json.dumps({"classification": classify(text), "source": source,
                      "error_lines": error_lines(text), "excerpt": tail(text, args.tail)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

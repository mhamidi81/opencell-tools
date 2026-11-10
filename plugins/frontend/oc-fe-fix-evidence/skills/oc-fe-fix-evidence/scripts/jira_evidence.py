#!/usr/bin/env python3
"""Attach a fix-evidence recording to a Jira ticket and post one comment.

    jira_evidence.py check --ticket INTRD-1 --state abc1234
    jira_evidence.py post  --ticket INTRD-1 --state abc1234 --manifest <dir>/manifest.json \
                           --branch fix/INTRD-1 --summary "..." [--uncommitted]

Uses Jira Cloud REST directly because the Atlassian MCP cannot upload files.
Auth is Basic JIRA_EMAIL:JIRA_API_TOKEN, read from the environment only.

The comment goes through API v2 on purpose: v2 takes wiki markup, where
`!file.png!` embeds an attachment by name. v3 (ADF) needs media ids instead.

Comments are append-only, so the duplicate guard is a marker line in the body,
`fix-evidence:<state>`, searched before anything is uploaded.

Exit codes: 0 posted / 0 already posted (check: 0 = not posted, 10 = posted) ·
            2 usage or credentials · 3 manifest refused · 1 Jira error
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = "https://opencellsoft.atlassian.net"
MARKER_PREFIX = "fix-evidence:"
MIME = {".png": "image/png", ".webm": "video/webm"}


class EvidenceError(RuntimeError):
    pass


def auth_header(env=None):
    env = os.environ if env is None else env
    token, email = env.get("JIRA_API_TOKEN"), env.get("JIRA_EMAIL")
    if not token or not email:
        raise EvidenceError(
            "JIRA_EMAIL and JIRA_API_TOKEN must both be set.\n"
            "Create an Atlassian API token at "
            "https://id.atlassian.com/manage/api-tokens, then:\n"
            "  export JIRA_EMAIL='you@opencellsoft.com'\n"
            "  export JIRA_API_TOKEN='ATATT...'"
        )
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def marker(state):
    return f"{MARKER_PREFIX}{state}"


def has_marker(comments, state):
    """`comments` is the v2 comment list; bodies are wiki-markup strings."""
    needle = marker(state)
    return any(needle in (c.get("body") or "") for c in comments)


def attachment_name(ticket, state, file_name):
    return f"{ticket}-evidence-{state}-{file_name}"


def escape(text):
    """Neutralise the wiki-markup characters that would swallow following text."""
    out = str(text)
    for ch in ("{", "}", "[", "]", "!", "|"):
        out = out.replace(ch, "\\" + ch)
    return out


def check_manifest(manifest):
    """Refuse to publish a recording that does not prove what the comment claims."""
    if not manifest.get("ok"):
        return "the scenario did not pass: " + str(manifest.get("error"))
    if not manifest.get("backendVerified"):
        return "no API call reached the chosen backend, so this is not a real-backend run"
    if not manifest.get("screenshots") and not manifest.get("video"):
        return "the run produced no screenshot and no video"
    return None


def build_comment(ticket, state, manifest, branch, summary, uncommitted):
    code = state.split("+")[0]
    where = f"{{{{{escape(branch)}}}}} at {{{{{code}}}}}"
    if uncommitted:
        where += " plus the uncommitted fix"
    lines = [
        "h3. Fix verified in a real browser",
        "",
        f"*What was tested:* {escape(summary)}",
        f"*Backend:* {escape(manifest['server'])} (real server, {manifest['backendRequests']} API calls, no mocks)",
        f"*Portal:* local build of {where}",
        f"*Recorded:* {manifest.get('finishedAt', '')}",
    ]
    if manifest.get("steps"):
        lines += ["", "h4. Steps"] + [f"# {escape(s)}" for s in manifest["steps"]]
    if manifest.get("screenshots"):
        lines += ["", "h4. Screenshots"]
        for shot in manifest["screenshots"]:
            name = attachment_name(ticket, state, shot["file"])
            lines += [f"*{escape(shot['label'])}*", f"!{name}|width=900!", ""]
    if manifest.get("video"):
        name = attachment_name(ticket, state, manifest["video"])
        lines += ["h4. Screencast", f"[^{name}]", ""]
    lines += ["----", f"_Recorded automatically by /oc-fe-fix-evidence — {marker(state)}_"]
    return "\n".join(lines)


def encode_multipart(name, content, boundary=None):
    boundary = boundary or uuid.uuid4().hex
    ext = os.path.splitext(name)[1].lower()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f"Content-Type: {MIME.get(ext, 'application/octet-stream')}\r\n\r\n"
    ).encode()
    return head + content + f"\r\n--{boundary}--\r\n".encode(), boundary


class Jira:
    def __init__(self, opener=None, env=None, base=BASE):
        self._open = opener or urllib.request.urlopen
        self._auth = auth_header(env)
        self._base = base

    def _send(self, method, path, data=None, headers=None):
        request = urllib.request.Request(self._base + path, data=data, method=method)
        request.add_header("Authorization", self._auth)
        request.add_header("Accept", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with self._open(request, timeout=120) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            raise EvidenceError(
                f"Jira {method} {path} -> {error.code}: {error.read()[:200]!r}"
            ) from error
        return json.loads(body) if body else None

    def comments(self, ticket):
        found, start = [], 0
        while True:
            page = self._send(
                "GET", f"/rest/api/2/issue/{ticket}/comment?startAt={start}&maxResults=100"
            )
            found += page.get("comments", [])
            start += len(page.get("comments", []))
            if not page.get("comments") or start >= page.get("total", 0):
                return found

    def attach(self, ticket, name, content):
        data, boundary = encode_multipart(name, content)
        return self._send(
            "POST", f"/rest/api/2/issue/{ticket}/attachments", data,
            {"X-Atlassian-Token": "no-check",
             "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def comment(self, ticket, body):
        return self._send(
            "POST", f"/rest/api/2/issue/{ticket}/comment",
            json.dumps({"body": body}).encode(), {"Content-Type": "application/json"},
        )


def post(jira, args, manifest, out_dir, log=print):
    refusal = check_manifest(manifest)
    if refusal:
        log(f"refused: {refusal}")
        return 3
    if has_marker(jira.comments(args.ticket), args.state):
        log(f"already posted for {args.state} — nothing to do")
        return 0
    files = [s["file"] for s in manifest.get("screenshots", [])]
    if manifest.get("video"):
        files.append(manifest["video"])
    for file_name in files:
        with open(os.path.join(out_dir, file_name), "rb") as handle:
            jira.attach(args.ticket, attachment_name(args.ticket, args.state, file_name),
                        handle.read())
        log(f"attached {file_name}")
    jira.comment(args.ticket, build_comment(
        args.ticket, args.state, manifest, args.branch, args.summary, args.uncommitted))
    log(f"comment posted on {args.ticket}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "post"):
        p = sub.add_parser(name)
        p.add_argument("--ticket", required=True)
        p.add_argument("--state", required=True)
        if name == "post":
            p.add_argument("--manifest", required=True)
            p.add_argument("--branch", required=True)
            p.add_argument("--summary", required=True)
            p.add_argument("--uncommitted", action="store_true")
    args = parser.parse_args(argv)
    try:
        jira = Jira()
        if args.command == "check":
            posted = has_marker(jira.comments(args.ticket), args.state)
            print("posted" if posted else "not-posted")
            return 10 if posted else 0
        with open(args.manifest, encoding="utf-8") as handle:
            manifest = json.load(handle)
        return post(jira, args, manifest, os.path.dirname(os.path.abspath(args.manifest)))
    except EvidenceError as error:
        print(str(error), file=sys.stderr)
        return 2 if "must both be set" in str(error) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Jenkins REST transport for /oc-fe-check-jenkins-build.

Auth is HTTP Basic JENKINS_USER:JENKINS_API_TOKEN. Both are read from the
environment and, when missing there, from the `export` lines of ~/.bashrc:
.bashrc exports do not reach non-interactive shells (the usual `case $- in *i*)`
guard returns before them), so a token that works in a terminal is otherwise
invisible to this script. The file is parsed with a regex, never sourced, and the
token is never printed.

Requests authenticated with an API token are exempt from Jenkins' CSRF crumb
check, so POSTs go out without one; a 403 whose body mentions a crumb is retried
once with a crumb from /crumbIssuer, for instances configured otherwise.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://jenkins.opencell.eu"
CRED_VARS = ("JENKINS_USER", "JENKINS_API_TOKEN")
EXPORT_RE = re.compile(
    r"""^\s*export\s+(JENKINS_USER|JENKINS_API_TOKEN)=(["']?)(.*?)\2\s*(?:#.*)?$""")
EXIT_AUTH, EXIT_NOT_FOUND, EXIT_ERROR = 2, 3, 4

AUTH_HELP = (
    "Jenkins needs JENKINS_USER and JENKINS_API_TOKEN (HTTP Basic):\n"
    "  export JENKINS_USER='<your Jenkins login>'\n"
    "  export JENKINS_API_TOKEN='<Jenkins → your name → Configure → API Token>'\n"
    "Exports in ~/.bashrc do not reach non-interactive shells; this script also reads\n"
    "the `export JENKINS_…=` lines of ~/.bashrc directly, so check they are spelled so.\n"
    "A 403 can also mean the user lacks Job/Read or Job/Build on this job."
)


class JenkinsError(RuntimeError):
    """Any failure talking to Jenkins. `status` is the HTTP code when there is one."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class MissingCredentials(JenkinsError):
    """JENKINS_USER or JENKINS_API_TOKEN found neither in the env nor in ~/.bashrc."""


def _bashrc_exports(path):
    found = {}
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            m = EXPORT_RE.match(line)
            if m and m.group(3) and not m.group(3).startswith("$"):
                found[m.group(1)] = m.group(3)  # last assignment wins, as in bash
    return found


def load_credentials(env=None, bashrc=None):
    env = os.environ if env is None else env
    creds = {k: env.get(k, "") for k in CRED_VARS}
    if not all(creds.values()):
        fallback = _bashrc_exports(Path(bashrc) if bashrc else Path.home() / ".bashrc")
        creds = {k: creds[k] or fallback.get(k, "") for k in CRED_VARS}
    missing = [k for k in CRED_VARS if not creds[k]]
    if missing:
        raise MissingCredentials("Missing " + " and ".join(missing) + ".\n\n" + AUTH_HELP)
    return creds["JENKINS_USER"], creds["JENKINS_API_TOKEN"]


def job_path(branch):
    """`dev` → `/job/dev`. Jenkins job names cannot contain '/', so it is encoded."""
    if not branch:
        raise ValueError("branch must not be empty")
    return "/job/" + urllib.parse.quote(branch, safe="")


def api(path, tree=None):
    """`<path>/api/json`, with an optional percent-encoded `tree` filter."""
    url = path.rstrip("/") + "/api/json"
    return url + ("?tree=" + urllib.parse.quote(tree, safe=",") if tree else "")


class JenkinsClient:
    def __init__(self, user, token, base=BASE, opener=None):
        self.base = base.rstrip("/")
        self.opener = opener or urllib.request.urlopen
        self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    def _open(self, method, path, data=None, headers=None):
        url = path if path.startswith("http") else self.base + path
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Authorization": self.auth, **(headers or {})})
        try:
            return self.opener(req, timeout=60)
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 403) and "crumb" not in body.lower():
                raise JenkinsError(f"HTTP {e.code} on {method} {url}\n\n{AUTH_HELP}",
                                   status=e.code) from None
            raise JenkinsError(f"HTTP {e.code} on {method} {url}: {body}", status=e.code) from None
        except urllib.error.URLError as e:
            raise JenkinsError(f"cannot reach {url}: {e.reason}") from None

    def get_text(self, path):
        with self._open("GET", path) as r:
            return r.read().decode("utf-8", "replace")

    def get_json(self, path):
        return json.loads(self.get_text(path))

    def post_form(self, path, form):
        """POST form-encoded data; returns the response headers, keys lower-cased."""
        data = urllib.parse.urlencode(form).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            with self._open("POST", path, data, headers) as r:
                return {k.lower(): v for k, v in r.headers.items()}
        except JenkinsError as e:
            if e.status != 403 or "crumb" not in str(e).lower():
                raise
        crumb = self.get_json("/crumbIssuer/api/json")
        headers[crumb["crumbRequestField"]] = crumb["crumb"]
        with self._open("POST", path, data, headers) as r:
            return {k.lower(): v for k, v in r.headers.items()}


def client_from_env(env=None, bashrc=None, opener=None):
    user, token = load_credentials(env, bashrc)
    return JenkinsClient(user, token, opener=opener)


def fail(err):
    """Print a JenkinsError to stderr and map it to the scripts' exit code."""
    print(f"ERROR: {err}", file=sys.stderr)
    if isinstance(err, MissingCredentials) or err.status in (401, 403):
        return EXIT_AUTH
    return EXIT_NOT_FOUND if err.status == 404 else EXIT_ERROR

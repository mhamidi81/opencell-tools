#!/usr/bin/env python3
"""Jira Cloud REST transport for /oc-bug-clusters.

Auth is Basic email:token read from JIRA_EMAIL / JIRA_API_TOKEN — never from the
command line, so the token never lands in a shell history or a process list.

429 and 503 are retried with a linear backoff; every other HTTP status raises with
the first 200 bytes of the response body. Failing loudly matters here: a swallowed
error would return zero issues, and zero issues is indistinguishable from a quiet
month unless it raises.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://opencellsoft.atlassian.net"
DEFAULT_EMAIL = "mohamed.hamidi@opencellsoft.com"
MAX_ATTEMPTS = 5
RETRY_STATUS = (429, 503)
# Only GET is safe to retry blind. A 429/503 on POST /rest/api/3/issue may arrive
# AFTER Jira committed the create -- retrying it would duplicate the issue, so a
# POST failure is raised immediately instead.
RETRYABLE_METHODS = {"GET"}


class JiraError(RuntimeError):
    """Any non-retryable failure talking to Jira."""


class MissingToken(JiraError):
    """JIRA_API_TOKEN is not in the environment."""


def auth_header(env=None):
    env = os.environ if env is None else env
    token = env.get("JIRA_API_TOKEN")
    if not token:
        raise MissingToken(
            "JIRA_API_TOKEN is not set.\n"
            "Create an Atlassian API token at "
            "https://id.atlassian.com/manage/api-tokens, then:\n"
            "  export JIRA_API_TOKEN='ATATT...'\n"
            "  export JIRA_EMAIL='you@opencellsoft.com'"
        )
    email = env.get("JIRA_EMAIL") or DEFAULT_EMAIL
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


class JiraClient:
    def __init__(self, opener=None, env=None, sleep=time.sleep, base=BASE):
        self._open = opener or urllib.request.urlopen
        self._auth = auth_header(env)
        self._sleep = sleep
        self._base = base

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(
                self._base + path,
                data=data,
                method=method,
                headers={
                    "Authorization": self._auth,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            try:
                with self._open(request, timeout=60) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as ex:
                retryable = method in RETRYABLE_METHODS and ex.code in RETRY_STATUS
                if retryable and attempt < MAX_ATTEMPTS - 1:
                    self._sleep(2 * (attempt + 1))
                    continue
                detail = ex.read()[:200].decode("utf-8", "replace")
                raise JiraError(f"HTTP {ex.code} on {method} {path}: {detail}") from ex
        raise JiraError(f"retries exhausted on {method} {path}")

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, body):
        return self._request("POST", path, body)

    def search(self, jql, fields, page_size=100):
        """Yield every issue matching jql, following nextPageToken to the last page."""
        token = None
        while True:
            body = {"jql": jql, "fields": fields, "maxResults": page_size}
            if token:
                body["nextPageToken"] = token
            page = self.post("/rest/api/3/search/jql", body)
            yield from page.get("issues") or []
            token = page.get("nextPageToken")
            if page.get("isLast") or not token:
                return

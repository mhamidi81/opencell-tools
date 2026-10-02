"""Shared fixtures. Puts the plugin's scripts/ on sys.path so tests import the
shipped modules directly — there is no package install step for a plugin."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "oc-clean-branches" / "scripts"
sys.path.insert(0, str(SCRIPTS))

ENV = {"BITBUCKET_EMAIL": "dev@opencellsoft.com", "BITBUCKET_ACCESS_TOKEN": "tok"}


class FakeResponse:
    """Minimal stand-in for the object urllib.request.urlopen returns."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode() if payload is not None else b""

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"nope"):
    return urllib.error.HTTPError("https://example/x", code, "err", {}, io.BytesIO(body))


class FakeOpener:
    """Returns queued results in order; records every Request it was handed.

    A queued item that is an Exception is raised instead of returned, which is how
    retry behaviour is tested.
    """

    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if not self.results:
            raise AssertionError("FakeOpener exhausted: an unexpected extra call")
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    def urls(self):
        return [r.full_url for r in self.requests]


@pytest.fixture
def env():
    return dict(ENV)


class FakeBitbucket:
    """Route-keyed stand-in for BitbucketClient: `routes` maps a path to either a
    payload (get) or a list (paginate). A callable route receives the params."""

    def __init__(self, routes):
        self.routes = routes
        self.deleted = []
        self.calls = []

    def _route(self, path, params):
        self.calls.append((path, params))
        if path not in self.routes:
            import bitbucket_client
            raise bitbucket_client.BitbucketError(f"HTTP 404 on GET {path}", status=404)
        value = self.routes[path]
        value = value(params) if callable(value) else value
        if isinstance(value, Exception):
            raise value
        return value

    def get(self, path, params=None):
        return self._route(path, params)

    def paginate(self, path, params=None):
        yield from self._route(path, params)

    def delete_branch(self, workspace, repo, name):
        self.deleted.append((repo, name))


class FakeJira:
    def __init__(self, issues, search_fails=False):
        self.issues = issues
        self.search_fails = search_fails

    def search(self, jql, fields):
        import jira_client
        if self.search_fails:
            raise jira_client.JiraError("HTTP 400", status=400)
        keys = jql[jql.index("(") + 1:jql.index(")")].split(", ")
        return [self.issues[k] for k in keys if k in self.issues]

    def get(self, path):
        import jira_client
        key = path.split("/issue/")[1].split("?")[0]
        if key not in self.issues:
            raise jira_client.JiraError("HTTP 404", status=404)
        return self.issues[key]

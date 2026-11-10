"""Shared fixtures. Puts the plugin's scripts/ on sys.path so tests import the
shipped modules directly — there is no package install step for a plugin."""
import copy
import io
import json
import sys
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "oc-fe-check-jenkins-build" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    return json.loads((FIXTURES / name).read_text())


def job(**last_build):
    """The real `dev` job with lastBuild fields overridden, e.g. job(result="FAILURE")."""
    j = copy.deepcopy(load("job_dev.json"))
    j["lastBuild"].update(last_build)
    return j


def describe(run_status="SUCCESS", **stage_status):
    """The real #4970 stage list with chosen stages overridden, e.g.
    describe("FAILED", **{"Build Front": "FAILED"}). Stages after the first FAILED
    one become NOT_EXECUTED (except post actions), as Jenkins reports them."""
    d = copy.deepcopy(load("describe_4970.json"))
    d["status"] = run_status
    failed = False
    for s in d["stages"]:
        if failed and s["name"] != "Declarative: Post Actions":
            s["status"] = "NOT_EXECUTED"
        if s["name"] in stage_status:
            s["status"] = stage_status[s["name"]]
        if s["status"] == "FAILED":
            failed = True
    return d


def seq(*items):
    """A route value that returns the next item on every call."""
    it = iter(items)
    return lambda: next(it)


class FakeResponse:
    """Minimal stand-in for the object urllib.request.urlopen returns."""

    def __init__(self, body=None, headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        self._body = (body or "").encode()
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"nope"):
    return urllib.error.HTTPError("https://jenkins.example/x", code, "err", {}, io.BytesIO(body))


class FakeOpener:
    """Returns queued results in order and records every Request. A queued Exception
    is raised; a FakeResponse is returned as-is; anything else is a 200 JSON body."""

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
        return item if isinstance(item, FakeResponse) else FakeResponse(item)


class FakeClient:
    """Route-keyed stand-in for JenkinsClient. `routes` maps a path (query string
    excluded) to a payload, a zero-arg callable, or an Exception. POST routes are
    keyed "POST <path>" and return the response-header dict."""

    base = "https://jenkins.example"

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.posts = []

    def _route(self, path):
        self.calls.append(path)
        key = path.split("?")[0]
        if key not in self.routes:
            import jenkins_common
            raise jenkins_common.JenkinsError(f"HTTP 404 on GET {path}", status=404)
        value = self.routes[key]
        value = value() if callable(value) else value
        if isinstance(value, Exception):
            raise value
        return value

    def get_json(self, path):
        return self._route(path)

    def get_text(self, path):
        return self._route(path)

    def post_form(self, path, form):
        self.posts.append((path, form))
        return self.routes.get("POST " + path.split("?")[0], {})

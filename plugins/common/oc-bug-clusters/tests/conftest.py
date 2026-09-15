"""Shared fixtures. Puts the plugin's scripts/ on sys.path so tests import the
shipped modules directly — there is no package install step for a plugin."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "oc-bug-clusters" / "scripts"
sys.path.insert(0, str(SCRIPTS))

ENV = {"JIRA_API_TOKEN": "tok", "JIRA_EMAIL": "dev@opencellsoft.com"}


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
    return urllib.error.HTTPError(
        "https://example/x", code, "err", {}, io.BytesIO(body)
    )


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

    def bodies(self):
        return [json.loads(r.data.decode()) for r in self.requests if r.data]


@pytest.fixture
def env():
    return dict(ENV)

"""Shared fixtures. Puts the plugin's scripts/ on sys.path so tests import the
shipped modules directly — there is no package install step for a plugin."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "oc-bug-root-causes" / "scripts"
sys.path.insert(0, str(SCRIPTS))

JIRA_ENV = {"JIRA_API_TOKEN": "tok", "JIRA_EMAIL": "dev@opencellsoft.com"}
BB_ENV = {"BITBUCKET_ACCESS_TOKEN": "ATCTTtok"}

SAMPLE_DIFF = (
    "diff --git a/src/app/Grid.tsx b/src/app/Grid.tsx\n+real change\n"
    "diff --git a/src/app/Grid.test.tsx b/src/app/Grid.test.tsx\n+test change\n"
    "diff --git a/package-lock.json b/package-lock.json\n+lock\n"
    "diff --git a/public/locales/fr/translation.json b/public/locales/fr/translation.json\n+i18n\n"
    "diff --git a/opencell-admin/src/test/java/FooTest.java "
    "b/opencell-admin/src/test/java/FooTest.java\n+junit\n"
    "diff --git a/opencell-admin/src/main/java/Foo.java "
    "b/opencell-admin/src/main/java/Foo.java\n+main\n-old\n"
)


class FakeResponse:
    """Minimal stand-in for the object urllib.request.urlopen returns.
    Bytes are served raw (a diff); anything else is served as JSON."""

    def __init__(self, payload):
        if isinstance(payload, bytes):
            self._body = payload
        elif payload is None:
            self._body = b""
        else:
            self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"nope", headers=None, url="https://example/x"):
    return urllib.error.HTTPError(url, code, "err", headers or {}, io.BytesIO(body))


class FakeOpener:
    """Returns queued results in order; records every Request it was handed.
    A queued Exception is raised instead of returned."""

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

    def bodies(self):
        return [json.loads(r.data.decode()) for r in self.requests if r.data]


@pytest.fixture
def jira_env():
    return dict(JIRA_ENV)


@pytest.fixture
def bb_env():
    return dict(BB_ENV)

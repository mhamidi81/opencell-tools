# PR Rejection Rate Plugin (`oc-pr-rejection-rate`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/oc-pr-rejection-rate` skill that reports total PRs, rejected PRs and the rejection rate for `opencell-portal` and `opencell-core` over a period, defaulting to the last seven days.

**Architecture:** A skill-only plugin in `plugins/common/`, shaped like `oc-bug-clusters`: real Python under `skills/oc-pr-rejection-rate/scripts/` invoked through `${CLAUDE_PLUGIN_ROOT}`, with an offline pytest suite. Four modules split on a testing boundary — `bitbucket_client.py` owns transport, `pr_fetch.py` owns all I/O, `pr_classify.py` is pure and owns the three rejection rules, `pr_report.py` owns all formatting. The model runs the commands and relays output; it makes no judgement.

**Tech Stack:** Python 3 standard library only (`urllib.request`, `argparse`, `json`, `csv`, `concurrent.futures`), pytest, Bitbucket Cloud REST API v2.0.

**Spec:** `docs/superpowers/specs/2026-09-16-pr-rejection-rate-design.md`

## Global Constraints

- **Plugin name, directory name and skill directory name are all `oc-pr-rejection-rate`.** Source in `marketplace.json` is `./plugins/common/oc-pr-rejection-rate`.
- **Python 3 standard library only.** No `requests`, no third-party dependency. `oc-bug-clusters` sets this precedent; a plugin has no install step.
- **Tests never touch the network.** Every HTTP path is exercised through a `FakeOpener` injected as the client's `opener`.
- **Auth is Basic `email:token`,** from `BITBUCKET_EMAIL` + `BITBUCKET_ACCESS_TOKEN`, read from the environment and **never** passed on the command line. `BITBUCKET_ACCESS_TOKEN` holds an Atlassian API token (`ATATT…`); `Authorization: Bearer` returns 401 for these and must never be used.
- **Read-only.** No POST, PUT or DELETE anywhere in this plugin. No Bitbucket writes, no Jira writes.
- **Fail loudly.** A swallowed error would report zero rejections, and zero is indistinguishable from a good week. Every non-retryable status raises.
- **Defaults:** workspace `opencellsoft`, repo slugs `opencell-portal` (`portal`) and `opencell-core` (`core`), window = last 7 days, `--until` exclusive.
- **Rate is `rejected / total`, rounded to one decimal.** A repository with zero PRs in the window reports `n/a`, never `0.0%`.
- Commit messages are prefixed `INTRD-47180:` and end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

### Task 1: Plugin scaffolding and packaging guards

Creates the plugin so it is discoverable, and locks the naming convention with tests before any logic exists.

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/.claude-plugin/plugin.json`
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/` (directory)
- Create: `plugins/common/oc-pr-rejection-rate/tests/conftest.py`
- Create: `plugins/common/oc-pr-rejection-rate/tests/test_packaging.py`
- Modify: `.claude-plugin/marketplace.json` (add one entry to the `plugins` array)

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/conftest.py` exports the fixtures every later task uses — `FakeResponse`, `FakeOpener(results)`, `http_error(code, body=b"nope")`, and the `env` pytest fixture returning `{"BITBUCKET_EMAIL": "dev@opencellsoft.com", "BITBUCKET_ACCESS_TOKEN": "tok"}`. It puts `skills/oc-pr-rejection-rate/scripts` on `sys.path`.

- [ ] **Step 1: Write the packaging tests**

Create `plugins/common/oc-pr-rejection-rate/tests/test_packaging.py`:

```python
"""The plugin must be discoverable and follow the marketplace naming convention.

Cheap guards against the two mistakes that make a plugin silently absent: a missing
marketplace entry, and a directory name that disagrees with the plugin name.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-pr-rejection-rate"
NAME = "oc-pr-rejection-rate"


def test_plugin_json_name_matches_directory():
    meta = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert meta["name"] == NAME == PLUGIN_DIR.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])
    assert meta["description"].strip()


def test_marketplace_registers_the_plugin():
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in market["plugins"] if p["name"] == NAME]
    assert len(entries) == 1, "plugin must appear exactly once in marketplace.json"
    assert entries[0]["source"] == f"./plugins/common/{NAME}"


def test_skill_directory_name_matches_skill_name():
    assert (PLUGIN_DIR / "skills" / NAME).is_dir()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`
Expected: FAIL — `FileNotFoundError` on `plugin.json`.

- [ ] **Step 3: Create `plugin.json`**

Create `plugins/common/oc-pr-rejection-rate/.claude-plugin/plugin.json`:

```json
{
  "name": "oc-pr-rejection-rate",
  "description": "Report the share of rejected pull requests on opencell-portal and opencell-core over a period, defaulting to the last seven days. A PR counts as rejected if it was declined, had changes requested at any point, or was pushed back from ready to draft - read from the Bitbucket activity feed, so a rejection that was later resolved is still counted. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. Read-only; reads Bitbucket via direct REST with BITBUCKET_EMAIL + BITBUCKET_ACCESS_TOKEN - no MCP.",
  "version": "1.0.0"
}
```

- [ ] **Step 4: Register the plugin in the marketplace**

In `.claude-plugin/marketplace.json`, add this object to the `plugins` array immediately after the `oc-bug-clusters` entry (keeping the common plugins grouped):

```json
{
  "name": "oc-pr-rejection-rate",
  "source": "./plugins/common/oc-pr-rejection-rate"
}
```

Match the surrounding entries' key order and indentation exactly — check a neighbouring entry first, since `marketplace.json` entries in this repo may carry more keys than `name` and `source`.

- [ ] **Step 5: Create the scripts directory and `conftest.py`**

```bash
mkdir -p plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts
```

Create `plugins/common/oc-pr-rejection-rate/tests/conftest.py`:

```python
"""Shared fixtures. Puts the plugin's scripts/ on sys.path so tests import the
shipped modules directly — there is no package install step for a plugin."""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "oc-pr-rejection-rate" / "scripts"
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`
Expected: PASS, 3 passed.

- [ ] **Step 7: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate .claude-plugin/marketplace.json
git commit -m "INTRD-47180: scaffold the oc-pr-rejection-rate plugin

Plugin manifest, marketplace entry and the offline test harness.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `bitbucket_client.py` — transport

The only module that talks to the network. Everything downstream is offline.

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/bitbucket_client.py`
- Test: `plugins/common/oc-pr-rejection-rate/tests/test_bitbucket_client.py`

**Interfaces:**
- Consumes: `FakeOpener`, `http_error`, `env` from `tests/conftest.py`.
- Produces:
  - `BASE = "https://api.bitbucket.org/2.0"`
  - `auth_header(env=None) -> str`
  - `class BitbucketError(RuntimeError)`, `class MissingToken(BitbucketError)`
  - `class BitbucketClient(opener=None, env=None, sleep=time.sleep, base=BASE)` with
    `.get(path, params=None) -> dict` and `.paginate(path, params=None) -> Iterator[dict]`.
    `path` is relative to `BASE` (e.g. `/repositories/opencellsoft/opencell-core/pullrequests`).
    `paginate` yields each element of `values` across every page, following the absolute
    URL in `next`.

- [ ] **Step 1: Write the failing tests**

Create `plugins/common/oc-pr-rejection-rate/tests/test_bitbucket_client.py`:

```python
"""Transport behaviour. No network: every call goes through FakeOpener."""
import base64

import pytest
from conftest import FakeOpener, http_error

import bitbucket_client as bc


def client(results, env, sleep=lambda _s: None):
    opener = FakeOpener(results)
    return bc.BitbucketClient(opener=opener, env=env, sleep=sleep), opener


def test_auth_header_is_basic_email_colon_token(env):
    header = bc.auth_header(env)
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
    assert decoded == "dev@opencellsoft.com:tok"


@pytest.mark.parametrize("missing", ["BITBUCKET_EMAIL", "BITBUCKET_ACCESS_TOKEN"])
def test_missing_credential_names_both_variables(env, missing):
    env.pop(missing)
    with pytest.raises(bc.MissingToken) as ex:
        bc.auth_header(env)
    message = str(ex.value)
    assert "BITBUCKET_EMAIL" in message and "BITBUCKET_ACCESS_TOKEN" in message
    assert "id.atlassian.com" in message


def test_get_sends_the_authorization_header(env):
    api, opener = client([{"ok": True}], env)
    assert api.get("/x") == {"ok": True}
    assert opener.requests[0].get_header("Authorization").startswith("Basic ")


def test_get_encodes_params_and_percent_encodes_the_timezone_plus(env):
    """A raw '+' in an ISO offset decodes server-side as a space and breaks the
    query silently — it must arrive as %2B."""
    api, opener = client([{"values": []}], env)
    api.get("/x", {"q": "created_on>=2026-09-09T00:00:00+00:00"})
    url = opener.urls()[0]
    assert "%2B00%3A00" in url
    assert "+00:00" not in url


def test_get_repeats_a_list_valued_param(env):
    """Bitbucket selects several PR states by repeating `state`, not by comma-joining."""
    api, opener = client([{"values": []}], env)
    api.get("/x", {"state": ["OPEN", "MERGED"]})
    url = opener.urls()[0]
    assert url.count("state=") == 2
    assert "state=OPEN" in url and "state=MERGED" in url


def test_paginate_follows_the_absolute_next_url(env):
    page1 = {"values": [{"id": 1}], "next": "https://api.bitbucket.org/2.0/x?page=2"}
    page2 = {"values": [{"id": 2}]}
    api, opener = client([page1, page2], env)
    assert [v["id"] for v in api.paginate("/x")] == [1, 2]
    assert opener.urls()[1] == "https://api.bitbucket.org/2.0/x?page=2"


def test_paginate_stops_on_a_page_without_next(env):
    api, _ = client([{"values": [{"id": 1}]}], env)
    assert list(api.paginate("/x")) == [{"id": 1}]


def test_429_is_retried_then_succeeds(env):
    slept = []
    api, opener = client([http_error(429), {"ok": True}], env, sleep=slept.append)
    assert api.get("/x") == {"ok": True}
    assert slept == [2]


def test_retries_are_exhausted_and_then_raise(env):
    api, _ = client([http_error(503)] * bc.MAX_ATTEMPTS, env, sleep=lambda _s: None)
    with pytest.raises(bc.BitbucketError):
        api.get("/x")


def test_401_is_not_retried_and_explains_basic_versus_bearer(env):
    api, opener = client([http_error(401, b"Unauthorized")], env)
    with pytest.raises(bc.BitbucketError) as ex:
        api.get("/x")
    assert len(opener.requests) == 1, "401 must not be retried"
    assert "Bearer" in str(ex.value) and "Basic" in str(ex.value)


def test_404_names_the_path_that_was_tried(env):
    api, _ = client([http_error(404, b"No such repository")], env)
    with pytest.raises(bc.BitbucketError) as ex:
        api.get("/repositories/opencellsoft/nope/pullrequests")
    assert "/repositories/opencellsoft/nope/pullrequests" in str(ex.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_bitbucket_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bitbucket_client'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/bitbucket_client.py`:

```python
#!/usr/bin/env python3
"""Bitbucket Cloud REST transport for /oc-pr-rejection-rate.

Auth is Basic email:token from BITBUCKET_EMAIL / BITBUCKET_ACCESS_TOKEN — never from
the command line, so the token never lands in a shell history or a process list.
BITBUCKET_ACCESS_TOKEN holds an Atlassian API token (ATATT...), which authenticates as
email:token over Basic; sending it as `Authorization: Bearer` returns 401, which is why
the 401 message says so explicitly.

429 and 503 are retried with a linear backoff; every other status raises with the first
200 bytes of the body. Failing loudly matters here: a swallowed error would report zero
rejected PRs, and zero is indistinguishable from a good week unless it raises.

Every request is a GET. This module has no write path by design — see the spec's D9.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bitbucket.org/2.0"
MAX_ATTEMPTS = 5
RETRY_STATUS = (429, 503)


class BitbucketError(RuntimeError):
    """Any non-retryable failure talking to Bitbucket."""


class MissingToken(BitbucketError):
    """BITBUCKET_EMAIL or BITBUCKET_ACCESS_TOKEN is not in the environment."""


def auth_header(env=None):
    env = os.environ if env is None else env
    token = env.get("BITBUCKET_ACCESS_TOKEN")
    email = env.get("BITBUCKET_EMAIL")
    if not token or not email:
        raise MissingToken(
            "BITBUCKET_EMAIL and BITBUCKET_ACCESS_TOKEN must both be set.\n"
            "Create an Atlassian API token at "
            "https://id.atlassian.com/manage/api-tokens, then:\n"
            "  export BITBUCKET_EMAIL='you@opencellsoft.com'\n"
            "  export BITBUCKET_ACCESS_TOKEN='ATATT...'"
        )
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def encode_params(params):
    """Encode a query string, repeating any list-valued key.

    Bitbucket selects several PR states by repeating `state`, and percent-encoding
    matters: a raw '+' in an ISO offset decodes server-side as a space, which silently
    breaks the created_on filter. urlencode's default quote_plus renders '+' as %2B.
    """
    pairs = []
    for key, value in (params or {}).items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(v)) for v in value)
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs)


class BitbucketClient:
    def __init__(self, opener=None, env=None, sleep=time.sleep, base=BASE):
        self._open = opener or urllib.request.urlopen
        self._auth = auth_header(env)
        self._sleep = sleep
        self._base = base

    def _url(self, path, params=None):
        url = path if path.startswith("http") else self._base + path
        query = encode_params(params)
        return f"{url}?{query}" if query else url

    def _request(self, url, label):
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(
                url,
                method="GET",
                headers={"Authorization": self._auth, "Accept": "application/json"},
            )
            try:
                with self._open(request, timeout=60) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as ex:
                if ex.code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                    self._sleep(2 * (attempt + 1))
                    continue
                detail = ex.read()[:200].decode("utf-8", "replace")
                if ex.code == 401:
                    detail += (
                        " — an ATATT... token authenticates as email:token over Basic "
                        "auth; Authorization: Bearer returns 401 for these tokens."
                    )
                raise BitbucketError(f"HTTP {ex.code} on GET {label}: {detail}") from ex
        raise BitbucketError(f"retries exhausted on GET {label}")

    def get(self, path, params=None):
        return self._request(self._url(path, params), path)

    def paginate(self, path, params=None):
        """Yield every element of `values`, following `next` to the last page.

        Bitbucket returns `next` as an absolute URL that already carries the query,
        so it is requested verbatim rather than rebuilt.
        """
        url = self._url(path, params)
        while url:
            page = self._request(url, path)
            yield from page.get("values") or []
            url = page.get("next")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_bitbucket_client.py -q`
Expected: PASS, 11 passed.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate
git commit -m "INTRD-47180: Bitbucket REST transport for the rejection-rate plugin

Basic email:token auth, list-valued query params, absolute-next pagination,
429/503 backoff, and a 401 message that names the Basic-versus-Bearer trap.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Probe the live API and pin the draft fixture

**This is spec §4 and it comes before the classifier.** R1 and R2 rest on documented, stable fields; R3 does not. Do not write `pr_classify.py` against a guessed JSON shape.

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/tests/fixtures/activity_drafted.json`
- Create: `plugins/common/oc-pr-rejection-rate/tests/fixtures/README.md`

**Interfaces:**
- Consumes: `BitbucketClient` from Task 2.
- Produces: `tests/fixtures/activity_drafted.json` — a real activity feed, secrets stripped, for a PR known to have been pushed back to draft. Task 4's `test_pr_classify.py` reads it.

- [ ] **Step 1: Confirm the credentials are present**

```bash
[ -n "$BITBUCKET_EMAIL" ] && [ -n "$BITBUCKET_ACCESS_TOKEN" ] && echo ok || echo MISSING
```

If this prints `MISSING`, **stop and tell the user**: `BITBUCKET_ACCESS_TOKEN` was not set when the spec was written and this task cannot be completed without it. Do not guess the shape. Skip to Task 4 and implement the fallback chain against the three modes as written there, then return to this task once the token is available.

- [ ] **Step 2: Find a PR that was pushed back to draft**

`/oc-review-pr` marks a PR draft at a review score of 6-7, so recent portal PRs are the likeliest carriers.

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts")
from bitbucket_client import BitbucketClient
api = BitbucketClient()
path = "/repositories/opencellsoft/opencell-portal/pullrequests"
params = {"state": ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"], "pagelen": 50,
          "sort": "-created_on"}
for pr in list(api.paginate(path, params))[:50]:
    print(pr["id"], pr.get("draft"), pr["state"], pr["title"][:60])
PY
```

Note any id printing `draft True`, and note whether the `draft` key is present at all.

- [ ] **Step 3: Dump one PR's activity feed and inspect how draft is represented**

Replace `PR_ID` with an id from Step 2 (prefer one currently or formerly in draft):

```bash
python3 - <<'PY'
import json, sys
sys.path.insert(0, "plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts")
from bitbucket_client import BitbucketClient
api = BitbucketClient()
entries = list(api.paginate(
    "/repositories/opencellsoft/opencell-portal/pullrequests/PR_ID/activity",
    {"pagelen": 50}))
print("entry kinds:", sorted({k for e in entries for k in e}))
for e in entries:
    if "update" in e:
        u = e["update"]
        print("update keys:", sorted(u), "| changes:", json.dumps(u.get("changes")),
              "| draft:", u.get("draft"), "| state:", u.get("state"))
PY
```

Record which of these is true — it decides which branch of Task 4's fallback chain fires in production:
1. `update.changes` carries a `draft` key with `old`/`new` → mode `activity`, transitions read directly;
2. `update` carries a plain `draft` boolean on each snapshot → mode `activity`, transitions read by comparing consecutive entries;
3. neither → mode `current-flag` or `unavailable`.

- [ ] **Step 4: Save the fixture with secrets stripped**

```bash
mkdir -p plugins/common/oc-pr-rejection-rate/tests/fixtures
python3 - <<'PY'
import json, sys
sys.path.insert(0, "plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts")
from bitbucket_client import BitbucketClient
api = BitbucketClient()
entries = list(api.paginate(
    "/repositories/opencellsoft/opencell-portal/pullrequests/PR_ID/activity",
    {"pagelen": 50}))
# Keep only what the classifier reads. Drops avatars, hrefs, uuids and comment bodies.
def trim(entry):
    kind, payload = next(iter(entry.items()))
    keep = {k: payload[k] for k in ("date", "state", "changes", "draft") if k in payload}
    return {kind: keep}
out = "plugins/common/oc-pr-rejection-rate/tests/fixtures/activity_drafted.json"
json.dump([trim(e) for e in entries], open(out, "w"), indent=2)
print("wrote", out)
PY
```

Read the written file before committing it and confirm it contains no display names, emails, avatar URLs or comment text.

- [ ] **Step 5: Record what the probe found**

Create `plugins/common/oc-pr-rejection-rate/tests/fixtures/README.md`, replacing the bracketed parts with what Step 3 actually printed:

```markdown
# Fixtures

`activity_drafted.json` is a real Bitbucket activity feed, trimmed to the keys the
classifier reads and stripped of names, avatars and comment bodies.

Probed on [DATE] against `opencellsoft/opencell-portal` PR [ID].

**How Bitbucket represents a draft transition here:** [one of — `update.changes.draft`
with old/new; a plain `update.draft` snapshot boolean; not represented at all].

This is the fixture that spec §4 asks for. It exists so `pr_classify.py` is written
against the real shape rather than a guessed one — do not replace it with a
hand-written file.
```

- [ ] **Step 6: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate/tests/fixtures
git commit -m "INTRD-47180: pin a real Bitbucket activity feed as a draft fixture

Probes how Bitbucket represents a ready-to-draft transition so the classifier is
written against the real shape. Trimmed to the keys the classifier reads.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `pr_classify.py` — the three rejection rules

The only module whose correctness decides the number. Pure: JSON in, JSON out, no network, no clock.

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_classify.py`
- Test: `plugins/common/oc-pr-rejection-rate/tests/test_pr_classify.py`

**Interfaces:**
- Consumes: `tests/fixtures/activity_drafted.json` from Task 3.
- Produces:
  - `REASONS = ("declined", "changes_requested", "redrafted")`
  - `is_declined(pr) -> bool`
  - `had_changes_requested(pr) -> bool`
  - `draft_states(activity) -> list[bool] | None` — the draft flag after each update entry, oldest first; `None` when the feed carries no draft data at all
  - `was_redrafted(pr, mode) -> bool`
  - `detect_draft_mode(document) -> str` — one of `"activity"`, `"current-flag"`, `"unavailable"`
  - `classify_pr(pr, mode) -> dict` with keys `id`, `title`, `author`, `created_on`, `state`, `url`, `rejected`, `r_declined`, `r_changes_requested`, `r_redrafted`
  - `build_model(document) -> dict` — the model shape below
  - `main(argv=None) -> int`, CLI `--document PATH --out PATH`

The input document is what Task 5's `pr_fetch.py` writes:

```python
{"window": {"since": "2026-09-09", "until": "2026-09-16"},
 "workspace": "opencellsoft",
 "repos": {"opencell-portal": {"pull_requests": [{  # PR fields verbatim from the list call
     "id": 1, "title": "...", "state": "MERGED", "created_on": "...",
     "draft": False, "author": {"display_name": "..."},
     "links": {"html": {"href": "..."}}, "participants": [...],
     "activity": [...],        # entries, oldest first
     "warnings": []}]}}}
```

The model `build_model` returns:

```python
{"window": {...}, "workspace": "...", "draft_detection": "activity",
 "repos": {"opencell-portal": {"total": 42, "rejected": 11, "rate": 26.2,
     "reasons": {"declined": 3, "changes_requested": 9, "redrafted": 2},
     "prs": [ ... classify_pr dicts ... ]}},
 "totals": {"total": 77, "rejected": 17, "rate": 22.1},
 "warnings": []}
```

- [ ] **Step 1: Write the failing tests**

Create `plugins/common/oc-pr-rejection-rate/tests/test_pr_classify.py`:

```python
"""The three rejection rules. Pure functions, no network, no clock.

These tests are the specification of the metric — if one of them is wrong, the
percentage is wrong and nobody downstream can tell.
"""
import json
from pathlib import Path

import pytest

import pr_classify as pc

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def pr(pid=1, state="OPEN", draft=False, activity=(), **extra):
    base = {"id": pid, "title": f"PR {pid}", "state": state, "draft": draft,
            "created_on": "2026-09-10T09:00:00+00:00",
            "author": {"display_name": "Dev"},
            "links": {"html": {"href": f"https://bitbucket.org/pr/{pid}"}},
            "participants": [], "activity": list(activity), "warnings": []}
    base.update(extra)
    return base


def update(draft=None, changes=None, state="OPEN"):
    payload = {"date": "2026-09-11T09:00:00+00:00", "state": state}
    if draft is not None:
        payload["draft"] = draft
    if changes is not None:
        payload["changes"] = changes
    return {"update": payload}


def document(prs, repo="opencell-portal"):
    return {"window": {"since": "2026-09-09", "until": "2026-09-16"},
            "workspace": "opencellsoft",
            "repos": {repo: {"pull_requests": list(prs)}}}


# --- R1: declined -------------------------------------------------------------

def test_declined_pr_is_rejected():
    assert pc.is_declined(pr(state="DECLINED")) is True


def test_merged_pr_is_not_declined():
    assert pc.is_declined(pr(state="MERGED")) is False


def test_superseded_pr_is_not_a_rejection():
    assert pc.is_declined(pr(state="SUPERSEDED")) is False


# --- R2: changes requested ----------------------------------------------------

def test_changes_requested_in_the_activity_feed_is_a_rejection():
    feed = [{"changes_requested": {"date": "2026-09-11T09:00:00+00:00"}}]
    assert pc.had_changes_requested(pr(activity=feed)) is True


def test_changes_requested_later_cleared_by_an_approval_is_still_a_rejection():
    """The participant flag clears when the reviewer approves. The PR was still
    sent back, and reading current state alone would lose that."""
    feed = [{"changes_requested": {"date": "2026-09-11T09:00:00+00:00"}},
            {"approval": {"date": "2026-09-12T09:00:00+00:00"}}]
    p = pr(activity=feed, state="MERGED", participants=[{"state": "approved"}])
    assert pc.had_changes_requested(p) is True
    assert pc.classify_pr(p, "activity")["rejected"] is True


def test_approval_only_is_not_a_rejection():
    feed = [{"approval": {"date": "2026-09-12T09:00:00+00:00"}}]
    assert pc.had_changes_requested(pr(activity=feed)) is False


def test_current_participant_changes_requested_counts_when_the_feed_is_empty():
    """Belt and braces: if the feed came back empty, a live participant flag is
    still evidence."""
    p = pr(participants=[{"state": "changes_requested"}])
    assert pc.had_changes_requested(p) is True


# --- R3: re-drafted -----------------------------------------------------------

def test_draft_states_reads_explicit_change_entries():
    feed = [update(changes={"draft": {"old": False, "new": True}})]
    assert pc.draft_states(feed) == [False, True]


def test_draft_states_reads_snapshot_booleans():
    feed = [update(draft=False), update(draft=True), update(draft=False)]
    assert pc.draft_states(feed) == [False, True, False]


def test_draft_states_is_none_when_the_feed_carries_no_draft_data():
    feed = [update(), {"approval": {"date": "2026-09-12T09:00:00+00:00"}}]
    assert pc.draft_states(feed) is None


def test_ready_to_draft_is_a_rejection():
    feed = [update(changes={"draft": {"old": False, "new": True}})]
    assert pc.was_redrafted(pr(activity=feed, draft=True), "activity") is True


def test_a_pr_opened_as_a_draft_and_then_readied_is_not_a_rejection():
    """Ordinary work in progress. This is the case the whole R3 design exists for."""
    feed = [update(draft=True), update(draft=False)]
    assert pc.was_redrafted(pr(activity=feed, draft=False), "activity") is False


def test_a_pr_opened_as_a_draft_and_still_a_draft_is_not_a_rejection():
    feed = [update(draft=True)]
    assert pc.was_redrafted(pr(activity=feed, draft=True), "activity") is False


def test_redrafted_then_readied_again_is_still_a_rejection():
    feed = [update(draft=False), update(draft=True), update(draft=False)]
    assert pc.was_redrafted(pr(activity=feed, draft=False), "activity") is True


def test_current_flag_mode_counts_a_draft_pr_with_post_creation_activity():
    p = pr(draft=True, activity=[update(), update()])
    assert pc.was_redrafted(p, "current-flag") is True


def test_current_flag_mode_ignores_a_draft_pr_with_no_post_creation_activity():
    p = pr(draft=True, activity=[update()])
    assert pc.was_redrafted(p, "current-flag") is False


def test_unavailable_mode_never_reports_a_redraft():
    p = pr(draft=True, activity=[update(draft=True), update(draft=False)])
    assert pc.was_redrafted(p, "unavailable") is False


# --- detection mode -----------------------------------------------------------

def test_mode_is_activity_when_any_pr_carries_draft_data():
    doc = document([pr(activity=[update(draft=True)]), pr(pid=2, activity=[update()])])
    assert pc.detect_draft_mode(doc) == "activity"


def test_mode_is_current_flag_when_only_the_pr_object_has_draft():
    doc = document([pr(activity=[update()])])
    assert pc.detect_draft_mode(doc) == "current-flag"


def test_mode_is_unavailable_when_nothing_carries_draft():
    p = pr(activity=[update()])
    del p["draft"]
    assert pc.detect_draft_mode(document([p])) == "unavailable"


def test_the_pinned_live_fixture_resolves_to_a_known_mode():
    """Guards spec §4: whatever Bitbucket actually sends must land in one of the
    three modes, never crash the classifier."""
    feed = json.loads((FIXTURES / "activity_drafted.json").read_text())
    states = pc.draft_states(feed)
    assert states is None or all(isinstance(s, bool) for s in states)


# --- aggregation --------------------------------------------------------------

def test_a_pr_with_two_reasons_counts_once_but_appears_in_both_columns():
    feed = [{"changes_requested": {"date": "2026-09-11T09:00:00+00:00"}}]
    model = pc.build_model(document([pr(state="DECLINED", activity=feed)]))
    repo = model["repos"]["opencell-portal"]
    assert repo["rejected"] == 1
    assert repo["reasons"]["declined"] == 1
    assert repo["reasons"]["changes_requested"] == 1


def test_rate_is_rounded_to_one_decimal():
    prs = [pr(pid=1, state="DECLINED"), pr(pid=2), pr(pid=3)]
    model = pc.build_model(document(prs))
    assert model["repos"]["opencell-portal"]["rate"] == 33.3


def test_rate_is_none_for_a_repo_with_no_prs():
    """`n/a` and `0.0%` are different facts; the model must not conflate them."""
    model = pc.build_model(document([]))
    assert model["repos"]["opencell-portal"]["rate"] is None
    assert model["repos"]["opencell-portal"]["total"] == 0


def test_totals_sum_across_repositories():
    doc = document([pr(pid=1, state="DECLINED"), pr(pid=2)])
    doc["repos"]["opencell-core"] = {"pull_requests": [pr(pid=3), pr(pid=4)]}
    model = pc.build_model(doc)
    assert model["totals"] == {"total": 4, "rejected": 1, "rate": 25.0}


def test_model_always_carries_the_detection_mode():
    model = pc.build_model(document([pr()]))
    assert model["draft_detection"] in {"activity", "current-flag", "unavailable"}


def test_per_pr_warnings_are_collected_onto_the_model():
    p = pr(warnings=["activity fetch failed: HTTP 500"])
    model = pc.build_model(document([p]))
    assert any("HTTP 500" in w for w in model["warnings"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_classify.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_classify'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_classify.py`:

```python
#!/usr/bin/env python3
"""Stage 2 of /oc-pr-rejection-rate: apply the three rejection rules.

Pure — JSON in, JSON out. No network, no clock, no environment. That boundary is what
lets the rules be tested offline, and the rules are the only thing that decides whether
the published percentage is right.

A PR is rejected if ANY rule fires, and it counts ONCE in the rejected total. The
per-reason counters are diagnostic and may sum past it; the report says so.

R1 and R2 read documented, stable fields. R3 does not: how Bitbucket represents a draft
transition is resolved at runtime into one of three declared modes, and the mode travels
with the model so a zero can never be misread as "nobody was re-drafted" when it means
"we could not tell". See the spec's section 4.
"""
import argparse
import json

REASONS = ("declined", "changes_requested", "redrafted")


def is_declined(pr):
    """R1 — the reviewer declined the PR outright."""
    return pr.get("state") == "DECLINED"


def had_changes_requested(pr):
    """R2 — changes were requested at any point.

    Deliberately historical. A reviewer who requests changes and later approves clears
    the participant flag, but the PR was still sent back; reading current state alone
    would lose most of the signal. The participant fallback only matters when the
    activity feed could not be read.
    """
    for entry in pr.get("activity") or []:
        if "changes_requested" in entry:
            return True
    return any(p.get("state") == "changes_requested" for p in pr.get("participants") or [])


def _entry_draft(payload):
    """The draft flag an update entry leaves behind, or None if it says nothing.

    Two shapes are accepted because Bitbucket's own is not contractual: an explicit
    `changes.draft` with old/new, and a plain `draft` snapshot boolean.
    """
    changes = payload.get("changes") or {}
    change = changes.get("draft")
    if isinstance(change, dict) and "new" in change:
        return bool(change["new"])
    if isinstance(payload.get("draft"), bool):
        return payload["draft"]
    return None


def _entry_draft_old(payload):
    changes = payload.get("changes") or {}
    change = changes.get("draft")
    if isinstance(change, dict) and "old" in change:
        return bool(change["old"])
    return None


def draft_states(activity):
    """The draft flag after each update entry, oldest first.

    Returns None when the feed carries no draft data at all — which is the signal that
    R3 must fall back to a coarser mode rather than silently report zero.
    """
    states = []
    for entry in activity or []:
        payload = entry.get("update")
        if payload is None:
            continue
        new = _entry_draft(payload)
        if new is None:
            continue
        if not states:
            old = _entry_draft_old(payload)
            if old is not None:
                states.append(old)
        states.append(new)
    return states or None


def was_redrafted(pr, mode):
    """R3 — the PR moved ready -> draft at least once.

    A PR opened as a draft and later made ready is ordinary work in progress, not a
    rejection, which is why the initial state is read rather than assumed.
    """
    if mode == "unavailable":
        return False
    if mode == "activity":
        states = draft_states(pr.get("activity"))
        if states is None:
            return False
        return any(not before and after for before, after in zip(states, states[1:]))
    # current-flag: the PR is a draft now and was worked on after it was opened. The
    # first update entry is the creation, so a lone entry proves nothing.
    updates = [e for e in pr.get("activity") or [] if "update" in e]
    return bool(pr.get("draft")) and len(updates) > 1


def detect_draft_mode(document):
    """Resolve, from the data actually returned, how R3 can be evaluated."""
    prs = [pr for repo in document.get("repos", {}).values()
           for pr in repo.get("pull_requests") or []]
    if any(draft_states(pr.get("activity")) is not None for pr in prs):
        return "activity"
    if any("draft" in pr for pr in prs):
        return "current-flag"
    return "unavailable"


def classify_pr(pr, mode):
    declined = is_declined(pr)
    changes = had_changes_requested(pr)
    redrafted = was_redrafted(pr, mode)
    return {
        "id": pr.get("id"),
        "title": pr.get("title") or "",
        "author": (pr.get("author") or {}).get("display_name") or "",
        "created_on": pr.get("created_on") or "",
        "state": pr.get("state") or "",
        "url": ((pr.get("links") or {}).get("html") or {}).get("href") or "",
        "rejected": declined or changes or redrafted,
        "r_declined": declined,
        "r_changes_requested": changes,
        "r_redrafted": redrafted,
    }


def _rate(rejected, total):
    """None, not 0.0, for an empty repository — the two mean different things."""
    return round(100.0 * rejected / total, 1) if total else None


def build_model(document):
    mode = detect_draft_mode(document)
    repos, warnings = {}, []
    grand_total = grand_rejected = 0
    for slug, payload in document.get("repos", {}).items():
        rows = [classify_pr(pr, mode) for pr in payload.get("pull_requests") or []]
        for pr in payload.get("pull_requests") or []:
            warnings.extend(f"{slug} PR {pr.get('id')}: {w}" for w in pr.get("warnings") or [])
        rejected = sum(1 for r in rows if r["rejected"])
        repos[slug] = {
            "total": len(rows),
            "rejected": rejected,
            "rate": _rate(rejected, len(rows)),
            "reasons": {reason: sum(1 for r in rows if r[f"r_{reason}"]) for reason in REASONS},
            "prs": rows,
        }
        grand_total += len(rows)
        grand_rejected += rejected
    return {
        "window": document.get("window", {}),
        "workspace": document.get("workspace", ""),
        "draft_detection": mode,
        "repos": repos,
        "totals": {"total": grand_total, "rejected": grand_rejected,
                   "rate": _rate(grand_rejected, grand_total)},
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply the rejection rules to a fetched document.")
    parser.add_argument("--document", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.document) as handle:
        model = build_model(json.load(handle))
    with open(args.out, "w") as handle:
        json.dump(model, handle, indent=2)
    print(f"draft detection mode: {model['draft_detection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_classify.py -q`
Expected: PASS, 27 passed.

If Task 3 was skipped for a missing token, `test_the_pinned_live_fixture_resolves_to_a_known_mode` fails on the missing fixture. That failure is correct and must not be deleted — it is the reminder that §4 is unresolved. Report it to the user and leave it failing.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate
git commit -m "INTRD-47180: the three PR rejection rules

Declined, changes-requested-at-any-point, and ready-to-draft. Rules are pure and
read history rather than current state, so a rejection that was later resolved is
still counted. R3 declares which of three detection modes produced it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `pr_fetch.py` — window resolution and I/O

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_fetch.py`
- Test: `plugins/common/oc-pr-rejection-rate/tests/test_pr_fetch.py`

**Interfaces:**
- Consumes: `BitbucketClient`, `BitbucketError`, `MissingToken` from Task 2.
- Produces:
  - `REPO_SLUG = {"portal": "opencell-portal", "core": "opencell-core"}`
  - `DEFAULT_WORKSPACE = "opencellsoft"`, `DEFAULT_DAYS = 7`
  - `resolve_window(since=None, until=None, today=None) -> (str, str)` — ISO dates; raises `ValueError` when `since >= until`
  - `list_pull_requests(client, workspace, slug, since, until) -> list[dict]`
  - `fetch_activity(client, workspace, slug, pr_id) -> list[dict]`
  - `fetch_repo(client, workspace, slug, since, until, workers=8) -> dict`
  - `main(argv=None) -> int`, CLI `--since --until --repo --workspace --out`
  - Writes the document shape Task 4 consumes.

- [ ] **Step 1: Write the failing tests**

Create `plugins/common/oc-pr-rejection-rate/tests/test_pr_fetch.py`:

```python
"""Window arithmetic and the fetch's request shape. No network."""
from datetime import date

import pytest
from conftest import FakeOpener, http_error

import pr_fetch as pf
from bitbucket_client import BitbucketClient


def client(results, env):
    opener = FakeOpener(results)
    return BitbucketClient(opener=opener, env=env, sleep=lambda _s: None), opener


# --- window -------------------------------------------------------------------

def test_default_window_is_the_last_seven_days_and_includes_today():
    since, until = pf.resolve_window(today=date(2026, 9, 16))
    assert (since, until) == ("2026-09-10", "2026-09-17")


def test_since_defaults_to_seven_days_before_an_explicit_until():
    since, until = pf.resolve_window(until="2026-09-01", today=date(2026, 9, 16))
    assert (since, until) == ("2026-08-25", "2026-09-01")


def test_explicit_dates_are_passed_through():
    assert pf.resolve_window("2026-08-01", "2026-09-01") == ("2026-08-01", "2026-09-01")


@pytest.mark.parametrize("since,until", [("2026-09-10", "2026-09-01"),
                                         ("2026-09-10", "2026-09-10")])
def test_an_inverted_or_empty_window_raises_before_any_fetch(since, until):
    with pytest.raises(ValueError) as ex:
        pf.resolve_window(since, until)
    assert "before" in str(ex.value)


# --- list ---------------------------------------------------------------------

def test_list_requests_every_state_and_the_created_on_window(env):
    api, opener = client([{"values": []}], env)
    pf.list_pull_requests(api, "opencellsoft", "opencell-core", "2026-09-10", "2026-09-17")
    url = opener.urls()[0]
    assert "/repositories/opencellsoft/opencell-core/pullrequests" in url
    for state in ("OPEN", "MERGED", "DECLINED", "SUPERSEDED"):
        assert f"state={state}" in url
    assert "created_on" in url
    assert "%2B00%3A00" in url, "the ISO offset must be percent-encoded"


def test_list_asks_for_the_draft_and_participants_fields(env):
    """Bitbucket omits both from the default list projection; R2's participant
    fallback and R3's current-flag mode are useless without them."""
    api, opener = client([{"values": []}], env)
    pf.list_pull_requests(api, "opencellsoft", "opencell-core", "2026-09-10", "2026-09-17")
    url = opener.urls()[0]
    assert "draft" in url and "participants" in url


# --- activity -----------------------------------------------------------------

def test_fetch_repo_attaches_activity_to_each_pr(env):
    listing = {"values": [{"id": 7, "title": "t", "state": "OPEN"}]}
    activity = {"values": [{"changes_requested": {"date": "2026-09-11T09:00:00+00:00"}}]}
    api, _ = client([listing, activity], env)
    result = pf.fetch_repo(api, "opencellsoft", "opencell-core",
                           "2026-09-10", "2026-09-17", workers=1)
    pr = result["pull_requests"][0]
    assert pr["id"] == 7
    assert pr["activity"] == activity["values"]
    assert pr["warnings"] == []


def test_a_failed_activity_fetch_warns_but_keeps_the_pr_in_the_total(env):
    """Dropping the PR would quietly shrink the denominator and flatter the rate."""
    listing = {"values": [{"id": 7, "title": "t", "state": "OPEN"}]}
    api, _ = client([listing] + [http_error(500)] * 5, env)
    result = pf.fetch_repo(api, "opencellsoft", "opencell-core",
                           "2026-09-10", "2026-09-17", workers=1)
    pr = result["pull_requests"][0]
    assert pr["activity"] == []
    assert pr["warnings"] and "500" in pr["warnings"][0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_fetch'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_fetch.py`:

```python
#!/usr/bin/env python3
"""Stage 1 of /oc-pr-rejection-rate: fetch a window of pull requests and their activity.

All network I/O lives here, so pr_classify.py can stay pure. The window anchors on
created_on: "of the PRs opened this week, X% were rejected" is a stable denominator,
where updated_on would let one PR count in several weeks.

Rejection is historical (see pr_classify), so each PR's activity feed is fetched too —
one extra call per PR. At 50-200 PRs per week per repository that is well inside
Bitbucket's 1000 requests/hour authenticated budget, and the calls are made in a small
thread pool.
"""
import argparse
import concurrent.futures
import json
import sys
from datetime import date, timedelta

from bitbucket_client import BitbucketClient, BitbucketError, MissingToken

DEFAULT_WORKSPACE = "opencellsoft"
DEFAULT_DAYS = 7
DEFAULT_WORKERS = 8
REPO_SLUG = {"portal": "opencell-portal", "core": "opencell-core"}
STATES = ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]

# Bitbucket's default list projection omits `draft` and `participants`. R3's
# current-flag mode and R2's participant fallback are both useless without them, so
# they are requested explicitly rather than hoped for.
FIELDS = ",".join([
    "next",
    "values.id", "values.title", "values.state", "values.created_on",
    "values.updated_on", "values.draft",
    "values.author.display_name",
    "values.links.html.href",
    "values.participants.state", "values.participants.approved",
])


def resolve_window(since=None, until=None, today=None):
    """Resolve the window to two ISO dates. `until` is exclusive, so today counts."""
    today = today or date.today()
    end = date.fromisoformat(until) if until else today + timedelta(days=1)
    start = date.fromisoformat(since) if since else end - timedelta(days=DEFAULT_DAYS)
    if start >= end:
        raise ValueError(f"--since ({start}) must be before --until ({end})")
    return start.isoformat(), end.isoformat()


def list_pull_requests(client, workspace, slug, since, until):
    path = f"/repositories/{workspace}/{slug}/pullrequests"
    params = {
        "state": STATES,
        "pagelen": 50,
        "sort": "-created_on",
        "fields": FIELDS,
        "q": f'created_on >= "{since}T00:00:00+00:00" '
             f'AND created_on < "{until}T00:00:00+00:00"',
    }
    return list(client.paginate(path, params))


def fetch_activity(client, workspace, slug, pr_id):
    path = f"/repositories/{workspace}/{slug}/pullrequests/{pr_id}/activity"
    return list(client.paginate(path, {"pagelen": 50}))


def fetch_repo(client, workspace, slug, since, until, workers=DEFAULT_WORKERS):
    prs = list_pull_requests(client, workspace, slug, since, until)

    def attach(pr):
        try:
            pr["activity"] = fetch_activity(client, workspace, slug, pr["id"])
            pr["warnings"] = []
        except BitbucketError as ex:
            # Never drop the PR: a missing activity feed costs R2 and R3 for this one
            # PR, but dropping it would shrink the denominator and flatter the rate.
            pr["activity"] = []
            pr["warnings"] = [f"activity fetch failed: {ex}"]
        return pr

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        attached = list(pool.map(attach, prs))
    return {"pull_requests": attached}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch a window of Bitbucket pull requests.")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--repo", default="both", choices=["portal", "core", "both"])
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = BitbucketClient()
    except (ValueError, MissingToken) as ex:
        print(str(ex), file=sys.stderr)
        return 2

    slugs = list(REPO_SLUG.values()) if args.repo == "both" else [REPO_SLUG[args.repo]]
    document = {"window": {"since": since, "until": until},
                "workspace": args.workspace, "repos": {}}
    try:
        for slug in slugs:
            document["repos"][slug] = fetch_repo(client, args.workspace, slug, since, until)
    except BitbucketError as ex:
        print(str(ex), file=sys.stderr)
        return 1

    with open(args.out, "w") as handle:
        json.dump(document, handle, indent=2)
    counts = ", ".join(f"{s}: {len(document['repos'][s]['pull_requests'])}" for s in slugs)
    print(f"window {since} -> {until} (exclusive); {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_fetch.py -q`
Expected: PASS, 9 passed.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate
git commit -m "INTRD-47180: fetch a window of PRs and their activity feeds

created_on window with an exclusive upper bound, every PR state, explicit draft and
participants projection, and a thread pool for the per-PR activity calls. A failed
activity fetch warns and keeps the PR in the denominator.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `pr_report.py` — Markdown and CSV

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_report.py`
- Test: `plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py`

**Interfaces:**
- Consumes: the model dict from `pr_classify.build_model`.
- Produces: `render_markdown(model) -> str`, `render_csv_rows(model) -> list[list]`, `format_rate(rate) -> str`, `DETECTION_NOTE: dict[str, str]`. `main` comes in Task 7, once HTML exists.

- [ ] **Step 1: Write the failing tests**

Create `plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py`:

```python
"""Report rendering. Pure string work over a model dict."""
import pr_report as pr


def model(**overrides):
    base = {
        "window": {"since": "2026-09-10", "until": "2026-09-17"},
        "workspace": "opencellsoft",
        "draft_detection": "activity",
        "repos": {
            "opencell-portal": {
                "total": 4, "rejected": 1, "rate": 25.0,
                "reasons": {"declined": 1, "changes_requested": 1, "redrafted": 0},
                "prs": [{"id": 11, "title": "Fix totals", "author": "Dev",
                         "created_on": "2026-09-11T09:00:00+00:00", "state": "DECLINED",
                         "url": "https://bitbucket.org/pr/11", "rejected": True,
                         "r_declined": True, "r_changes_requested": True,
                         "r_redrafted": False}],
            },
        },
        "totals": {"total": 4, "rejected": 1, "rate": 25.0},
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_markdown_shows_the_window_and_that_until_is_exclusive():
    text = pr.render_markdown(model())
    assert "2026-09-10" in text and "2026-09-17" in text
    assert "exclusive" in text.lower()


def test_markdown_reports_the_rate_with_one_decimal_and_a_percent_sign():
    assert "25.0%" in pr.render_markdown(model())


def test_markdown_renders_an_empty_repo_as_n_a_not_zero_percent():
    m = model()
    m["repos"]["opencell-core"] = {"total": 0, "rejected": 0, "rate": None,
                                   "reasons": {"declined": 0, "changes_requested": 0,
                                               "redrafted": 0}, "prs": []}
    text = pr.render_markdown(m)
    assert "n/a" in text
    assert "0.0%" not in text


def test_markdown_says_reason_columns_may_overlap():
    assert "overlap" in pr.render_markdown(model()).lower()


def test_markdown_always_states_the_draft_detection_mode():
    assert "activity" in pr.render_markdown(model())


def test_markdown_warns_loudly_when_r3_could_not_be_measured():
    text = pr.render_markdown(model(draft_detection="unavailable"))
    assert "could not be measured" in text.lower()


def test_markdown_flags_the_current_flag_mode_as_approximate():
    assert "approximate" in pr.render_markdown(model(draft_detection="current-flag")).lower()


def test_markdown_lists_the_rejected_prs_with_their_reasons():
    text = pr.render_markdown(model())
    assert "11" in text and "Fix totals" in text and "declined" in text


def test_markdown_relays_warnings():
    text = pr.render_markdown(model(warnings=["opencell-core PR 3: activity fetch failed"]))
    assert "activity fetch failed" in text


def test_csv_header_carries_one_column_per_rule():
    header = pr.render_csv_rows(model())[0]
    for column in ("repo", "id", "title", "author", "created_on", "state",
                   "rejected", "r_declined", "r_changes_requested", "r_redrafted", "url"):
        assert column in header


def test_csv_has_one_row_per_pr_plus_the_header():
    rows = pr.render_csv_rows(model())
    assert len(rows) == 2
    assert rows[1][0] == "opencell-portal"


def test_csv_carries_the_detection_mode_so_a_saved_file_stays_interpretable():
    rows = pr.render_csv_rows(model())
    assert any("activity" in str(cell) for cell in rows[0] + rows[1]) or \
        "draft_detection" in rows[0]


def test_format_rate_handles_none():
    assert pr.format_rate(None) == "n/a"
    assert pr.format_rate(25.0) == "25.0%"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pr_report'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_report.py`:

```python
#!/usr/bin/env python3
"""Stage 3 of /oc-pr-rejection-rate: render the model as Markdown, CSV and HTML.

All formatting lives here and nothing else does. The one rule worth stating: a
repository with no PRs in the window renders `n/a`, never `0.0%` — "we opened nothing"
and "we opened work and none was rejected" are different facts and must not look alike.

Every output states which draft-detection mode produced R3, so a saved file stays
interpretable months later. See the spec's section 4.
"""
import argparse
import csv
import json

DETECTION_NOTE = {
    "activity": "R3 read ready-to-draft transitions from the activity feed (exact).",
    "current-flag": "R3 is **approximate**: the activity feed carried no draft history, "
                    "so a PR currently in draft with post-creation activity was counted. "
                    "Both over- and under-counting are possible.",
    "unavailable": "R3 **could not be measured**: no draft data was available from "
                   "Bitbucket. The re-drafted column is not a real zero.",
}

CSV_HEADER = ["repo", "id", "title", "author", "created_on", "state", "rejected",
              "r_declined", "r_changes_requested", "r_redrafted", "url",
              "draft_detection"]


def format_rate(rate):
    return "n/a" if rate is None else f"{rate:.1f}%"


def _reasons(row):
    return ", ".join(r for r in ("declined", "changes_requested", "redrafted")
                     if row[f"r_{r}"]) or "-"


def render_markdown(model):
    window = model.get("window", {})
    out = [f"# PR rejection rate — {window.get('since')} → {window.get('until')} "
           f"(on `created_on`; the end date is exclusive)", ""]

    out += ["| Repository | Total PRs | Rejected | Rejection rate |",
            "|---|---:|---:|---:|"]
    for slug, repo in model["repos"].items():
        out.append(f"| {slug} | {repo['total']} | {repo['rejected']} | "
                   f"{format_rate(repo['rate'])} |")
    totals = model["totals"]
    out.append(f"| **All** | **{totals['total']}** | **{totals['rejected']}** | "
               f"**{format_rate(totals['rate'])}** |")

    out += ["", "## Rejection reasons", "",
            "A PR counts once in the rejected total above, so these columns **overlap** "
            "and may sum past it.", "",
            "| Repository | Declined | Changes requested | Re-drafted |",
            "|---|---:|---:|---:|"]
    for slug, repo in model["repos"].items():
        r = repo["reasons"]
        out.append(f"| {slug} | {r['declined']} | {r['changes_requested']} | "
                   f"{r['redrafted']} |")

    out += ["", f"*{DETECTION_NOTE[model['draft_detection']]}*", ""]

    for slug, repo in model["repos"].items():
        rejected = [row for row in repo["prs"] if row["rejected"]]
        if not rejected:
            continue
        out += [f"## Rejected PRs — {slug}", "",
                "| PR | Title | Author | State | Reasons |", "|---|---|---|---|---|"]
        for row in rejected:
            out.append(f"| [#{row['id']}]({row['url']}) | {row['title']} | "
                       f"{row['author']} | {row['state']} | {_reasons(row)} |")
        out.append("")

    if model.get("warnings"):
        out += ["## Warnings", ""] + [f"- {w}" for w in model["warnings"]] + [""]
    return "\n".join(out)


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]
    mode = model["draft_detection"]
    for slug, repo in model["repos"].items():
        for row in repo["prs"]:
            rows.append([slug, row["id"], row["title"], row["author"], row["created_on"],
                         row["state"], row["rejected"], row["r_declined"],
                         row["r_changes_requested"], row["r_redrafted"], row["url"], mode])
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py -q`
Expected: PASS, 13 passed.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate
git commit -m "INTRD-47180: render the rejection report as Markdown and CSV

Headline table, overlapping reason breakdown, rejected-PR detail and a per-run note
naming the draft-detection mode. Empty repositories render n/a, never 0.0%.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: HTML output and the `pr_report.py` CLI

**Files:**
- Modify: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/pr_report.py` (append `CSS`, `render_html`, `main`)
- Modify: `plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py` (append the HTML tests)

**Interfaces:**
- Consumes: `render_markdown`, `render_csv_rows`, `format_rate`, `DETECTION_NOTE` from Task 6.
- Produces: `render_html(model) -> str`, `main(argv=None) -> int` with CLI `--model PATH --out PATH --csv PATH`. Prints the Markdown to stdout and writes both files.

Before writing the CSS, read `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_cluster.py` (the `CSS` constant and `render_html`) and match its visual language — these reports sit next to each other in `./docs/`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py`:

```python
def test_html_is_self_contained():
    """No external CSS or JS: these files get emailed and opened offline."""
    html = pr.render_html(model())
    assert html.startswith("<!doctype html>")
    assert "<style>" in html
    assert "http://" not in html.replace("https://bitbucket.org", "")


def test_html_escapes_a_title_containing_markup():
    m = model()
    m["repos"]["opencell-portal"]["prs"][0]["title"] = "<script>alert(1)</script>"
    html = pr.render_html(m)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_states_the_detection_mode():
    assert "activity feed" in pr.render_html(model())


def test_html_renders_n_a_for_an_empty_repo():
    m = model()
    m["repos"]["opencell-core"] = {"total": 0, "rejected": 0, "rate": None,
                                   "reasons": {"declined": 0, "changes_requested": 0,
                                               "redrafted": 0}, "prs": []}
    assert "n/a" in pr.render_html(m)


def test_main_writes_both_files_and_prints_markdown(tmp_path, capsys):
    import json
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model()))
    html, csv_path = tmp_path / "r.html", tmp_path / "r.csv"
    assert pr.main(["--model", str(model_path), "--out", str(html),
                    "--csv", str(csv_path)]) == 0
    assert "25.0%" in capsys.readouterr().out
    assert html.read_text().startswith("<!doctype html>")
    assert "r_declined" in csv_path.read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_pr_report.py -q`
Expected: FAIL — `AttributeError: module 'pr_report' has no attribute 'render_html'`.

- [ ] **Step 3: Write the implementation**

Append to `pr_report.py`:

```python
CSS = """
body { font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem auto;
       max-width: 62rem; color: #1b1b1b; }
h1 { font-size: 1.5rem; margin-bottom: .2rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
.window { color: #666; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }
th, td { border-bottom: 1px solid #e3e3e3; padding: .45rem .6rem; text-align: left; }
th { background: #f6f7f9; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; border-top: 2px solid #ccc; }
.note { background: #f6f7f9; border-left: 3px solid #999; padding: .6rem .9rem;
        margin: 1rem 0; color: #444; }
.note.warn { background: #fff6e5; border-left-color: #e0a300; }
.reasons { color: #666; font-size: .9em; }
a { color: #0b5cad; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def _e(value):
    import html as _html
    return _html.escape(str(value), quote=True)


def render_html(model):
    window = model.get("window", {})
    mode = model["draft_detection"]
    note_class = "note warn" if mode != "activity" else "note"
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<title>PR rejection rate</title>", f"<style>{CSS}</style></head><body>",
        "<h1>PR rejection rate</h1>",
        f"<p class=\"window\">{_e(window.get('since'))} &rarr; {_e(window.get('until'))} "
        "on <code>created_on</code>; the end date is exclusive.</p>",
        "<table><tr><th>Repository</th><th class=\"num\">Total PRs</th>"
        "<th class=\"num\">Rejected</th><th class=\"num\">Rejection rate</th></tr>",
    ]
    for slug, repo in model["repos"].items():
        parts.append(f"<tr><td>{_e(slug)}</td><td class=\"num\">{repo['total']}</td>"
                     f"<td class=\"num\">{repo['rejected']}</td>"
                     f"<td class=\"num\">{_e(format_rate(repo['rate']))}</td></tr>")
    totals = model["totals"]
    parts.append(f"<tr class=\"total\"><td>All</td><td class=\"num\">{totals['total']}</td>"
                 f"<td class=\"num\">{totals['rejected']}</td>"
                 f"<td class=\"num\">{_e(format_rate(totals['rate']))}</td></tr></table>")

    parts.append("<h2>Rejection reasons</h2><p class=\"reasons\">A PR counts once in the "
                 "rejected total above, so these columns overlap and may sum past it.</p>")
    parts.append("<table><tr><th>Repository</th><th class=\"num\">Declined</th>"
                 "<th class=\"num\">Changes requested</th>"
                 "<th class=\"num\">Re-drafted</th></tr>")
    for slug, repo in model["repos"].items():
        r = repo["reasons"]
        parts.append(f"<tr><td>{_e(slug)}</td><td class=\"num\">{r['declined']}</td>"
                     f"<td class=\"num\">{r['changes_requested']}</td>"
                     f"<td class=\"num\">{r['redrafted']}</td></tr>")
    parts.append("</table>")

    detection_html = DETECTION_NOTE[mode].replace("**", "")
    parts.append(f"<p class=\"{note_class}\">{_e(detection_html)}</p>")

    for slug, repo in model["repos"].items():
        rejected = [row for row in repo["prs"] if row["rejected"]]
        if not rejected:
            continue
        parts.append(f"<h2>Rejected PRs &mdash; {_e(slug)}</h2>")
        parts.append("<table><tr><th>PR</th><th>Title</th><th>Author</th><th>State</th>"
                     "<th>Reasons</th></tr>")
        for row in rejected:
            parts.append(
                f"<tr><td><a href=\"{_e(row['url'])}\">#{_e(row['id'])}</a></td>"
                f"<td>{_e(row['title'])}</td><td>{_e(row['author'])}</td>"
                f"<td>{_e(row['state'])}</td><td>{_e(_reasons(row))}</td></tr>")
        parts.append("</table>")

    if model.get("warnings"):
        parts.append("<h2>Warnings</h2><ul>")
        parts.extend(f"<li>{_e(w)}</li>" for w in model["warnings"])
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the PR rejection-rate report.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    args = parser.parse_args(argv)

    with open(args.model) as handle:
        model = json.load(handle)

    print(render_markdown(model))
    with open(args.out, "w") as handle:
        handle.write(render_html(model))
    with open(args.csv, "w", newline="") as handle:
        csv.writer(handle).writerows(render_csv_rows(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the whole suite to verify it passes**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate
git commit -m "INTRD-47180: self-contained HTML report and the render CLI

Styled to match the other ./docs/ reports, escapes PR titles, and carries the
draft-detection note as a highlighted warning when R3 is approximate or unavailable.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `SKILL.md`, drift guards and repository documentation

**Files:**
- Create: `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/SKILL.md`
- Modify: `plugins/common/oc-pr-rejection-rate/tests/test_packaging.py` (append the drift guards)
- Modify: `CLAUDE.md` (plugin list in "Plugin Types", and a new section)

**Interfaces:**
- Consumes: the CLIs of `pr_fetch.py`, `pr_classify.py`, `pr_report.py` from Tasks 4-7.
- Produces: the `/oc-pr-rejection-rate` command.

- [ ] **Step 1: Write the failing drift guards**

Append to `plugins/common/oc-pr-rejection-rate/tests/test_packaging.py`:

```python
import re
import subprocess
import sys

SKILL = PLUGIN_DIR / "skills" / NAME / "SKILL.md"
SCRIPTS = PLUGIN_DIR / "skills" / NAME / "scripts"


def skill_text():
    return SKILL.read_text()


def test_skill_frontmatter_name_matches_the_plugin():
    head = skill_text().split("---")[1]
    assert f"name: {NAME}" in head
    assert "description:" in head and "argument-hint:" in head


def test_skill_documents_every_flag_it_advertises():
    """The argument-hint and the argument table must not drift apart."""
    text = skill_text()
    hint = re.search(r'argument-hint: "(.+)"', text).group(1)
    advertised = set(re.findall(r"--[a-z-]+", hint))
    documented = set(re.findall(r"^\| `(--[a-z-]+)`", text, re.M))
    assert advertised - documented == set(), "advertised but undocumented"
    assert documented - advertised == set(), "documented but not advertised"


def test_every_script_the_skill_invokes_exists():
    for name in set(re.findall(r"scripts/([a-z_]+\.py)", skill_text())):
        assert (SCRIPTS / name).is_file(), name


def test_skill_only_passes_flags_the_scripts_accept():
    """Catches the commonest rot: a renamed CLI flag the skill still calls."""
    for name in sorted(set(re.findall(r"scripts/([a-z_]+\.py)", skill_text()))):
        helptext = subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--help"],
            capture_output=True, text=True, check=True).stdout
        for block in re.findall(r"```bash\n(.*?)```", skill_text(), re.S):
            if f"scripts/{name}" not in block:
                continue
            for flag in re.findall(r"--[a-z-]+", block):
                assert flag in helptext, f"{name} does not accept {flag}"


def test_skill_states_the_basic_auth_rule():
    """The Bearer trap costs an hour every time someone rediscovers it."""
    text = skill_text()
    assert "BITBUCKET_EMAIL" in text and "BITBUCKET_ACCESS_TOKEN" in text
    assert "Bearer" in text


def test_skill_is_documented_as_read_only():
    assert "read-only" in skill_text().lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests/test_packaging.py -q`
Expected: FAIL — `FileNotFoundError` on `SKILL.md`.

- [ ] **Step 3: Write `SKILL.md`**

Create `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/SKILL.md`:

````markdown
---
name: oc-pr-rejection-rate
description: Report the share of rejected pull requests on opencell-portal and opencell-core over a period, defaulting to the last seven days. A PR counts as rejected if it was declined, had changes requested at any point, or was pushed back from ready to draft - read from the Bitbucket activity feed, so a rejection that was later resolved is still counted. Prints a Markdown report and writes a date-stamped HTML + CSV to ./docs/. Read-only. Reads Bitbucket via direct REST with BITBUCKET_EMAIL + BITBUCKET_ACCESS_TOKEN - there is no Bitbucket MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--workspace SLUG] [--out PATH] [--csv PATH]"
---

## Purpose

Answer one question per repository over a period: **how often does our code get sent
back?** Three numbers — total PRs, rejected PRs, rejection rate — plus the breakdown that
lets someone check them.

A PR is **rejected** if any of these holds. It counts **once**, but appears in every
reason column that applies:

1. **Declined** — `state == DECLINED`.
2. **Changes requested** — at any point in its history. Deliberately historical: a
   reviewer who requests changes and later approves clears the flag, but the PR was
   still sent back.
3. **Re-drafted** — the PR moved ready → draft at least once. `/oc-review-pr` does this
   at a review score of 6-7. A PR **opened** as a draft is ordinary work in progress and
   is **not** a rejection.

This command is **read-only**. It writes nothing to Bitbucket and nothing to Jira. It
needs no git checkout and runs from any directory.

## Access

Requires **`BITBUCKET_EMAIL`** and **`BITBUCKET_ACCESS_TOKEN`**, read from the
environment and never passed on the command line. `BITBUCKET_ACCESS_TOKEN` holds an
**Atlassian API token** (`ATATT…`, from https://id.atlassian.com/manage/api-tokens),
which authenticates as `email:token` over **Basic** auth:

```
curl -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" …     # correct
curl -H "Authorization: Bearer ${BITBUCKET_ACCESS_TOKEN}" …  # 401 for ATATT… tokens
```

If either is unset, tell the user how to create the token and stop. **There is no
Bitbucket MCP** — the Rovo server exposes its Bitbucket tools only under API-token auth,
never over the OAuth flow the official plugin uses. Do not look for one.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-pr-rejection-rate` reports **the last 7
days** on **both** repositories.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 7 days before `--until` | Start of the window, inclusive, on `created_on` |
| `--until` | tomorrow | End of the window, **exclusive** — so today's PRs count |
| `--repo` | `both` | `portal` → `opencell-portal`; `core` → `opencell-core`; `both` |
| `--workspace` | `opencellsoft` | Bitbucket workspace slug |
| `--out` | `./docs/pr-rejection-rate-<TODAY>.html` | HTML report |
| `--csv` | `./docs/pr-rejection-rate-<TODAY>.csv` | One row per PR, one column per rule |

`<TODAY>` is `date -u +%Y-%m-%d`. **Echo the resolved window before doing any work**, e.g.
`Measuring PR rejections on opencell-portal + opencell-core, 2026-09-10 → 2026-09-17`.

## Task 1 — Fetch

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-pr-rejection-rate"
RUN="${TMPDIR:-/tmp}/oc-pr-rejection-rate/[WORKSPACE]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/pr_fetch.py" --since [SINCE] --until [UNTIL] \
  --repo [REPO] --workspace [WORKSPACE] --out "$RUN/prs.json"
```

**Never read `prs.json`.** It holds every PR's full activity feed and exists only for the
next script. If it reports 0 pull requests, say
`No pull requests created in [SINCE] → [UNTIL]` and stop.

## Task 2 — Classify

```bash
python3 "$S/scripts/pr_classify.py" --document "$RUN/prs.json" --out "$RUN/model.json"
```

It prints the resolved **draft detection mode**. Note it — Task 3's report states it, and
if it is not `activity` the re-drafted column is qualified rather than exact.

## Task 3 — Report

```bash
python3 "$S/scripts/pr_report.py" --model "$RUN/model.json" \
  --out [OUT] --csv [CSV]
```

It prints the Markdown report to stdout — **relay it**. Then tell the user where the HTML
and CSV landed.

Two things to say every time, because the numbers are misread without them:

- The reason columns **overlap** — a declined PR that also had changes requested appears
  in both, so they can sum past the rejected total.
- If the draft detection mode is **not** `activity`, say so plainly: the re-drafted
  column is approximate (`current-flag`) or was not measurable at all (`unavailable`).
  Never present it as an exact zero.

Relay every `WARNING:` line verbatim. A PR whose activity feed failed to load still
counts in the total, but its rules 2 and 3 could not be evaluated.

## Failure behaviour

| Condition | What to do |
|---|---|
| `BITBUCKET_EMAIL` or `BITBUCKET_ACCESS_TOKEN` unset | Print the setup instructions from the script and stop. Never report a zero |
| `HTTP 401` | The token is being sent as Bearer, or it is not an `ATATT…` token. Relay the message; it explains the Basic-versus-Bearer rule |
| `HTTP 404` | The workspace or repository slug is wrong. The message names the path that was tried |
| `--since … must be before --until …` | The dates are back to front or equal. Relay it, ask for corrected dates, and stop. Nothing was fetched |
| Zero PRs in the window | Report it and stop. Do not write an empty HTML or CSV |
| A `WARNING:` line | Relay verbatim — a PR's activity feed failed to load, so rules 2 and 3 are unknown for it |
````

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`
Expected: PASS, all tests.

- [ ] **Step 5: Document the plugin in `CLAUDE.md`**

In the **Plugin Types** section, item 1, add `/oc-pr-rejection-rate` to the list of slash commands alongside `/oc-bug-clusters`.

Then add this section immediately after the **Bug clustering (`/oc-bug-clusters`)** section:

```markdown
## PR rejection rate (`/oc-pr-rejection-rate`)

`plugins/common/oc-pr-rejection-rate` reports, per repository and per period (default one
week), the total pull requests, how many were rejected, and the rejection rate. Like
`oc-bug-clusters` it ships **real Python files** under `skills/oc-pr-rejection-rate/scripts/`
and a pytest suite:

```bash
python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q
```

Four things are not obvious from the code:

- **Rejection is historical, not current state.** A reviewer who requests changes and
  later approves clears the participant flag; a PR pushed back to draft and then fixed
  reads as an ordinary ready PR. The rules are therefore evaluated against each PR's
  **activity feed**, which costs one extra API call per PR. Rewriting this to read the PR
  list alone would be faster and would silently undercount most rejections.
- **A PR *opened* as a draft is not a rejection.** Only a **ready → draft** transition is
  — which is what `/oc-review-pr` does at a review score of 6-7. Losing that distinction
  turns every work-in-progress draft into a rejection.
- **R3 declares how it was measured.** How Bitbucket represents a draft transition is
  resolved at runtime into `activity` (exact), `current-flag` (approximate) or
  `unavailable` (not measurable), and that mode appears in the Markdown, the HTML and the
  CSV. Do not remove it: a re-drafted count of zero is meaningless without knowing which
  mode produced it.
- **The window anchors on `created_on` and the reason columns overlap.** `--until` is
  exclusive. A PR counts once in the rejected total but appears in every reason column
  that applies, so the reason columns legitimately sum past it. A repository with no PRs
  in the window reports `n/a`, never `0.0%`.

It is **read-only** — no Bitbucket writes, no Jira writes — and uses the same
`BITBUCKET_EMAIL` + `BITBUCKET_ACCESS_TOKEN` Basic auth as `/oc-review-pr`; see
**Atlassian and Bitbucket Access**.
```

- [ ] **Step 6: Commit**

```bash
git add plugins/common/oc-pr-rejection-rate CLAUDE.md
git commit -m "INTRD-47180: the /oc-pr-rejection-rate skill and its documentation

SKILL.md with the three-task flow, drift guards binding the skill's flags to the
scripts' CLIs, and a CLAUDE.md section recording why rejection is read from the
activity feed rather than current state.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: End-to-end run against the live API

The suite proves the parts. This proves the whole thing works against real Bitbucket data — and it is the only step that can catch a wrong `q` filter or a field Bitbucket does not actually return.

**Files:**
- Create: `docs/pr-rejection-rate-<TODAY>.html` and `.csv` (report artefacts; commit only if the user wants them)

**Interfaces:**
- Consumes: every script from Tasks 2-7.

- [ ] **Step 1: Confirm the credentials are present**

```bash
[ -n "$BITBUCKET_EMAIL" ] && [ -n "$BITBUCKET_ACCESS_TOKEN" ] && echo ok || echo MISSING
```

If `MISSING`, stop and tell the user the plugin is complete and unit-tested but has never been run against live data. Do not claim it works.

- [ ] **Step 2: Run the full pipeline over the last seven days**

```bash
S=plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate
RUN="${TMPDIR:-/tmp}/oc-pr-rejection-rate/live"
mkdir -p "$RUN" docs
python3 "$S/scripts/pr_fetch.py" --repo both --out "$RUN/prs.json"
python3 "$S/scripts/pr_classify.py" --document "$RUN/prs.json" --out "$RUN/model.json"
python3 "$S/scripts/pr_report.py" --model "$RUN/model.json" \
  --out "docs/pr-rejection-rate-$(date -u +%Y-%m-%d).html" \
  --csv "docs/pr-rejection-rate-$(date -u +%Y-%m-%d).csv"
```

- [ ] **Step 3: Check the output against reality**

Verify each of these, and report any that fail rather than explaining them away:

1. The totals are plausible for a week on each repository (single to low double digits, not 0 and not thousands). A 0 total means the `q` filter is wrong, not that nobody worked.
2. The printed draft detection mode matches what Task 3's probe found.
3. Pick one PR the CSV marks `r_declined` and confirm in Bitbucket that it really is declined.
4. Pick one PR marked `r_changes_requested` and confirm the activity shows it.
5. If the mode is `activity`, pick one marked `r_redrafted` and confirm it was pushed back to draft — **and** confirm a PR that was merely opened as a draft is **not** marked.
6. Open the HTML in a browser: tables render, links resolve to Bitbucket, the detection note is visible.

- [ ] **Step 4: Run the whole suite one last time**

Run: `python3 -m pytest plugins/common/oc-pr-rejection-rate/tests -q`
Expected: PASS.

- [ ] **Step 5: Report to the user**

Give them the real numbers, the detection mode, the file paths, and anything from Step 3 that did not check out. Ask whether to commit the generated `docs/` artefacts — `oc-bug-clusters` report output is currently untracked in this repo, so do not commit them unprompted.

---

## Self-Review

**Spec coverage:** §1 problem → Tasks 2-7. §2 D1/D2 → Tasks 1-7 (Python + pytest throughout). D3 → Task 5 `resolve_window` + the `created_on` `q` filter. D4 → Task 5 `fetch_repo`. D5 → Task 4 `was_redrafted`. D6 → Task 4 `build_model` + Task 6's overlap note. D7 → Task 4 `detect_draft_mode` + Tasks 6/7 `DETECTION_NOTE`. D8 → Task 4 (pure module). D9 → Task 2 (GET-only client) + Task 8's read-only test. D10 → Task 5 `REPO_SLUG` + `--workspace`. §3 plugin shape → Tasks 1-8. §4 draft risk → Task 3 (probe) + Task 4 (three modes). §5 rules → Task 4. §6 arguments → Tasks 5, 7, 8. §7 output → Tasks 6, 7. §8 failure behaviour → Task 2 (401/404/429), Task 5 (window, zero PRs, partial activity), Task 8 (the `SKILL.md` table). §9 testing → every task, plus Task 9's live run.

**Placeholder scan:** no TBD/TODO. The only bracketed placeholders are `[SINCE]`, `[REPO]`, `PR_ID` etc. inside `SKILL.md` and probe commands, which are runtime substitutions in the same style as `oc-bug-clusters`'s shipped `SKILL.md`, and `[DATE]`/`[ID]` in Task 3's fixture README, which Step 3 of that task supplies.

**Type consistency:** `draft_states` returns `list[bool] | None` in Task 4's interface, its docstring and its tests. `format_rate(None) == "n/a"` is consistent across Tasks 6 and 7. The model key is `draft_detection` everywhere (Tasks 4, 6, 7, 8). `r_declined` / `r_changes_requested` / `r_redrafted` are spelled identically in `classify_pr`, `REASONS` (without the `r_` prefix, joined in `build_model` via the f-string), `CSV_HEADER` and `_reasons`. `fetch_repo` returns `{"pull_requests": [...]}`, which is exactly what `build_model` reads.

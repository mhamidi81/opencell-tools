# `oc-bug-clusters` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/oc-bug-clusters` marketplace plugin that turns a period of Jira bugs into subject clusters and, on request, into one Enabler per area holding one Sub-task per cluster.

**Architecture:** Four Python scripts shipped inside the skill (`jira_client` transport → `bug_fetch` → `bug_cluster` → `bug_enabler`), orchestrated by `SKILL.md`. Area assignment is deterministic Python; subject classification is the only LLM step, and it happens between `bug_fetch` and `bug_cluster` by reading a compact JSONL and writing `assignments.json`. Jira writes are a separate `--plan`/`--apply` pair so the confirmation gate lives in the skill, not in an interactive prompt.

**Tech Stack:** Python 3.14 **stdlib only** (`urllib`, `json`, `csv`, `argparse`, `datetime`, `re`) — matching the existing `ai_jira_fetch.py` style; pytest 9.0.2 for tests; Jira Cloud REST v3.

**Spec:** `docs/superpowers/specs/2026-09-15-oc-bug-clusters-design.md`

## Global Constraints

- **Naming:** plugin directory = plugin name = skill name = `oc-bug-clusters`; the command is `/oc-bug-clusters`. `common` factory takes no abbreviation (see `CLAUDE.md` → Naming Convention).
- **Stdlib only.** No `requests`, no `sklearn`, no `pandas`. The scripts must run on a bare `python3`.
- **`JIRA_API_TOKEN` is mandatory and read from the environment only** — never accepted as a CLI argument, never printed. `JIRA_EMAIL` defaults to `mohamed.hamidi@opencellsoft.com`.
- **Never use the Atlassian MCP for the fetch** and never add an Atlassian/Bitbucket MCP server to this repo (`CLAUDE.md` rule). Reads go through `POST /rest/api/3/search/jql`.
- **Jira base URL:** `https://opencellsoft.atlassian.net`.
- **Issue type ids:** Enabler `10076`, Sub-task `10003`. **Component names:** `Frontend`, `Backend`. **Area tokens:** `portal`, `core` — the two are never mixed.
- **Default assignees, verbatim:** portal/Frontend → `5ef5c13914f60e0ac1c9b049` (Mohamed Hamidi); core/Backend → `63369fa788ed2ebef97cddfb` (Adil El Jaouhari).
- **`Sub-bug` must be quoted in JQL** (`issuetype in (Bug, "Sub-bug")`) — the hyphen breaks an unquoted term.
- **Every commit message ends with:**
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
- All work happens on branch `feature/INTRD-47165-bug-clusters`.

---

## File Structure

```
plugins/common/oc-bug-clusters/
  .claude-plugin/plugin.json                  # metadata; name + version
  skills/oc-bug-clusters/
    SKILL.md                                  # orchestration, arg table, classification prompt
    references/subjects.md                    # seeded subject taxonomy (editable)
    scripts/
      jira_client.py                          # REST transport only: auth, retry, pagination
      bug_fetch.py                            # stages 1-2: fetch, ADF flatten, area, two outputs
      bug_cluster.py                          # stage 4: cluster model + markdown/CSV/HTML renderers
      bug_enabler.py                          # stage 5: preflight, plan, apply, resume, links
  tests/
    conftest.py                               # puts scripts/ on sys.path; shared fakes
    test_jira_client.py
    test_bug_fetch.py
    test_bug_cluster.py
    test_bug_render.py
    test_bug_enabler.py
    test_packaging.py                         # marketplace wiring + SKILL.md/argparse flag parity
.claude-plugin/marketplace.json               # MODIFY: one new entry
CLAUDE.md                                     # MODIFY: document the new skill
```

Responsibilities, one line each:

- **`jira_client.py`** — HTTP only. Knows nothing about bugs. Everything above it is testable with a fake opener.
- **`bug_fetch.py`** — turns a window into normalized bug records; owns the *deterministic* decisions (resolution filter, area assignment, excerpting).
- **`bug_cluster.py`** — turns records + `assignments.json` into a cluster model, then into three renderings. No network.
- **`bug_enabler.py`** — the only module that writes to Jira; split into a pure planner and an applier so the plan can be shown before anything is created.

Run tests with `python3 -m pytest plugins/common/oc-bug-clusters/tests -q` from the repo root.

---
### Task 1: Plugin scaffold, marketplace registration, subject taxonomy

Creates the package so the plugin is loadable, and the taxonomy every later task
classifies against. Nothing here talks to Jira.

**Files:**
- Create: `plugins/common/oc-bug-clusters/.claude-plugin/plugin.json`
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/references/subjects.md`
- Create: `plugins/common/oc-bug-clusters/tests/test_packaging.py`
- Modify: `.claude-plugin/marketplace.json` (append one entry to `plugins`)

**Interfaces:**
- Consumes: nothing.
- Produces: the taxonomy file path `skills/oc-bug-clusters/references/subjects.md`, whose
  H2 headings (`## <subject>`) are the seeded subject vocabulary read by Task 8's
  classification step and asserted by `test_packaging.py`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b feature/INTRD-47165-bug-clusters
```

- [ ] **Step 2: Write the failing packaging test**

Create `plugins/common/oc-bug-clusters/tests/test_packaging.py`:

```python
"""The plugin must be discoverable and follow the marketplace naming convention.

These are cheap guards against the two mistakes that make a plugin silently absent:
a missing marketplace entry, and a directory name that disagrees with the plugin name.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-bug-clusters"
NAME = "oc-bug-clusters"


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


def seeded_subjects():
    text = (PLUGIN_DIR / "skills" / NAME / "references" / "subjects.md").read_text()
    return re.findall(r"^## ([a-z0-9-]+)$", text, re.M)


def test_subjects_are_lower_kebab_and_unique():
    subjects = seeded_subjects()
    assert len(subjects) >= 15, "taxonomy too thin to classify against"
    assert len(subjects) == len(set(subjects)), "duplicate subject heading"
    for s in subjects:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s), s


def test_every_subject_has_a_description_line():
    text = (PLUGIN_DIR / "skills" / NAME / "references" / "subjects.md").read_text()
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        assert body.strip(), f"subject '{heading}' has no description"
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_packaging.py -q`
Expected: FAIL — `FileNotFoundError` for `plugin.json`.

- [ ] **Step 4: Write `plugin.json`**

Create `plugins/common/oc-bug-clusters/.claude-plugin/plugin.json`:

```json
{
  "name": "oc-bug-clusters",
  "description": "Analyse the bugs created over a period, classify each onto a seeded subject taxonomy, and group any subject carrying at least 5 bugs into a cluster. Area (portal/core) is resolved deterministically from the Jira component with a [front]/[back] summary-tag fallback; the subject is the only LLM judgement. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. With --create-enabler it creates one Enabler per area (Frontend assigned to Mohamed Hamidi, Backend to Adil El Jaouhari) holding one Sub-task per cluster, with the cluster's bugs linked; writes are confirmed, idempotent via a marker label, and resumable. Reads Jira via direct Cloud REST with a mandatory JIRA_API_TOKEN - no Atlassian MCP.",
  "version": "1.0.0"
}
```

- [ ] **Step 5: Register in the marketplace**

In `.claude-plugin/marketplace.json`, append to the `plugins` array, after the
`oc-time-report` entry:

```json
    {
      "name": "oc-bug-clusters",
      "source": "./plugins/common/oc-bug-clusters",
      "description": "Period-scoped bug clustering: classify the bugs created in a window onto a subject taxonomy, group subjects carrying at least 5 bugs, and optionally create one Jira Enabler per area with a Sub-task per cluster"
    }
```

Mind the comma on the entry that previously ended the array.

- [ ] **Step 6: Write the subject taxonomy**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/references/subjects.md`.
The subject names below are drawn from the free-form tags observed on real bugs
(`[Rating]`, `[Quote New UI]`, `[dunning setting]`, `[invoicing]`, `[open order]`,
`[payment logs]`, `[MANUAL MATCHING]`, `[menu]`, `[PERF]`) plus the Opencell domain:

```markdown
# Bug subject taxonomy

The vocabulary `/oc-bug-clusters` classifies bugs onto. One subject per bug, chosen by
what the bug is **about** — the product area it lives in — never by its symptom
(`quoting`, not `blank-screen`).

Editing this file changes future runs. Adding a subject is safe; **renaming one breaks
month-over-month comparison**, so prefer adding an alias line to renaming.

## rating
Price computation, rating scripts, price plans, charge application, contract and
discount application, usage rating, recurring charge generation.

## quoting
Quotes and the CPQ funnel: quote creation, quote versions, quote offers and products,
quote lifecycle, the Quote UI screens.

## ordering
Commercial orders and order lifecycle: order creation, open orders, order validation,
order products, order status transitions.

## subscriptions
Subscriptions, services, activation, suspension, termination, renewal, subscription
lifecycle and its charges.

## catalog
Offer templates, product templates, charge templates, price plan matrixes, bundles,
attributes and their configuration screens.

## invoicing
Invoice generation, invoice lines, aggregation, invoice validation, PDF/XML production,
invoice sequences, billing runs and billing cycles.

## payments
Payments, payment methods, payment gateways, payment schedules, refunds, direct debit,
payment logs and callbacks.

## matching
Matching and unmatching of accounting entries, manual matching, automatic matching,
account operations balancing.

## dunning
Dunning policies, dunning levels, collection plans, dunning settings and actions.

## accounting
Accounting schemes, journals, accounting entries, chart of accounts, general-ledger
export, revenue recognition.

## taxation
Tax categories, tax classes, tax mapping, tax computation and exemptions.

## customers
Customer hierarchy: sellers, customers, customer accounts, billing accounts, user
accounts, contact information and their screens.

## mediation
CDR ingestion, mediation jobs, EDR processing, rejected records, usage import.

## contracts
Framework agreements, contracts, contract lines, contract rules and their application
conditions.

## reporting
Reports, dashboards, exports, Jasper outputs, KPIs and listings meant for analysis.

## jobs
Job scheduler, job instances, job execution and timers, batch processing outside
mediation and invoicing.

## api
REST endpoints, DTO serialization, Swagger/OpenAPI, GraphQL, API error codes and
generic API filtering — where the defect is in the interface itself.

## security
Authentication, Keycloak, roles and permissions, visibility rules, session handling.

## settings
Global and provider settings, custom fields, custom entities, i18n/translations,
currencies, calendars, administration screens.

## data-management
Import/export of data, file processing, attachments and documents, data migration and
purge.

## navigation
Menus, routing, breadcrumbs, page layout, global search — defects in getting to a
screen rather than in the screen's domain.

## performance
Slow pages, slow queries, timeouts, memory and volume problems, where slowness is the
defect rather than a wrong result.
```

- [ ] **Step 7: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_packaging.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 8: Verify the marketplace JSON is still valid**

Run: `python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo OK`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add plugins/common/oc-bug-clusters .claude-plugin/marketplace.json
git commit -m "INTRD-47165: scaffold the oc-bug-clusters plugin

Plugin metadata, marketplace registration, the seeded subject taxonomy
and the packaging tests that guard the naming convention.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 2: `jira_client.py` — REST transport

The only module that performs HTTP. Isolating it means every later task is tested
against a fake opener with no network.

**Files:**
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/jira_client.py`
- Create: `plugins/common/oc-bug-clusters/tests/conftest.py`
- Create: `plugins/common/oc-bug-clusters/tests/test_jira_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces, for Tasks 3, 6 and 7:
  - `BASE = "https://opencellsoft.atlassian.net"`
  - `class JiraError(RuntimeError)` and `class MissingToken(JiraError)`
  - `auth_header(env=None) -> str`
  - `class JiraClient(opener=None, env=None, sleep=time.sleep, base=BASE)` with
    `get(path) -> dict`, `post(path, body) -> dict`,
    `search(jql, fields, page_size=100) -> Iterator[dict]`

- [ ] **Step 1: Write `conftest.py` (shared fakes, no assertions yet)**

Create `plugins/common/oc-bug-clusters/tests/conftest.py`:

```python
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
```

- [ ] **Step 2: Write the failing transport test**

Create `plugins/common/oc-bug-clusters/tests/test_jira_client.py`:

```python
import pytest
from conftest import FakeOpener, http_error

import jira_client as jc


def test_missing_token_raises_with_actionable_message():
    with pytest.raises(jc.MissingToken) as ex:
        jc.auth_header({})
    assert "id.atlassian.com/manage/api-tokens" in str(ex.value)


def test_auth_header_is_basic_email_colon_token(env):
    import base64

    header = jc.auth_header(env)
    scheme, _, payload = header.partition(" ")
    assert scheme == "Basic"
    assert base64.b64decode(payload).decode() == "dev@opencellsoft.com:tok"


def test_auth_header_falls_back_to_the_default_email():
    import base64

    payload = jc.auth_header({"JIRA_API_TOKEN": "tok"}).split(" ", 1)[1]
    assert base64.b64decode(payload).decode().endswith(":tok")
    assert "@opencellsoft.com" in base64.b64decode(payload).decode()


def test_search_follows_next_page_token_and_stops_on_is_last(env):
    opener = FakeOpener([
        {"issues": [{"key": "A-1"}], "nextPageToken": "p2", "isLast": False},
        {"issues": [{"key": "A-2"}], "isLast": True},
    ])
    client = jc.JiraClient(opener=opener, env=env)

    keys = [i["key"] for i in client.search("project = A", ["summary"])]

    assert keys == ["A-1", "A-2"]
    assert opener.bodies()[0]["jql"] == "project = A"
    assert "nextPageToken" not in opener.bodies()[0]
    assert opener.bodies()[1]["nextPageToken"] == "p2"


def test_search_stops_when_the_token_is_absent_even_without_is_last(env):
    opener = FakeOpener([{"issues": [{"key": "A-1"}]}])
    client = jc.JiraClient(opener=opener, env=env)
    assert [i["key"] for i in client.search("q", ["summary"])] == ["A-1"]


def test_retries_429_then_succeeds(env):
    slept = []
    opener = FakeOpener([http_error(429), {"ok": True}])
    client = jc.JiraClient(opener=opener, env=env, sleep=slept.append)

    assert client.post("/x", {}) == {"ok": True}
    assert slept == [2]


def test_does_not_retry_a_400_and_reports_the_body(env):
    opener = FakeOpener([http_error(400, b"bad jql")])
    client = jc.JiraClient(opener=opener, env=env, sleep=lambda _s: None)

    with pytest.raises(jc.JiraError) as ex:
        client.post("/x", {})
    assert "400" in str(ex.value) and "bad jql" in str(ex.value)


def test_gives_up_after_five_attempts(env):
    slept = []
    opener = FakeOpener([http_error(503)] * 5)
    client = jc.JiraClient(opener=opener, env=env, sleep=slept.append)

    with pytest.raises(jc.JiraError):
        client.get("/x")
    assert len(slept) == 4, "4 sleeps between 5 attempts"


def test_empty_body_returns_empty_dict(env):
    opener = FakeOpener([None])
    client = jc.JiraClient(opener=opener, env=env)
    assert client.get("/x") == {}
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_jira_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'jira_client'`.

- [ ] **Step 4: Write the implementation**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/jira_client.py`:

```python
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
                if ex.code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
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
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_jira_client.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 6: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: Jira REST transport for oc-bug-clusters

Basic auth from the environment, 429/503 retry, nextPageToken pagination.
Isolated from the bug logic so every later module tests against a fake
opener with no network.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 3: `bug_fetch.py` — fetch, flatten, filter, assign area

Stages 1 and 2 of the spec. Every decision here is deterministic, which is what keeps
the portal/core split stable between two runs of the same window.

**Files:**
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_fetch.py`
- Create: `plugins/common/oc-bug-clusters/tests/test_bug_fetch.py`

**Interfaces:**
- Consumes: `jira_client.JiraClient` (Task 2).
- Produces, for Tasks 4 and 6:
  - `AREA_COMPONENT = {"portal": "Frontend", "core": "Backend"}`
  - `flatten_adf(node) -> str`, `excerpt(text, limit=300) -> str`
  - `area_of(fields) -> "portal" | "core" | None`, `is_real_defect(fields) -> bool`
  - `resolve_window(since, until, today=None, days=30) -> (str, str)`
  - `build_jql(projects, since, until) -> str`
  - `normalize(issue) -> dict` — the **bug record**, the single shape every later
    module consumes:
    `{key, area, component, summary, excerpt, issuetype, status, status_category,
      resolution, created (YYYY-MM-DD), assignee, reporter, labels, priority,
      parent, url}`
  - `areas_in_scope(repo) -> set[str]`
  - `collect(client, jql, repo) -> dict` — the **`bugs.json` document**:
    `{window, projects, repo, fetched, dropped_invalid, bugs: [record, ...]}`
  - `classify_rows(document) -> list[dict]` — `{key, summary, excerpt, component, labels}`

- [ ] **Step 1: Write the failing test**

Create `plugins/common/oc-bug-clusters/tests/test_bug_fetch.py`:

```python
import json
from datetime import date

import pytest
from conftest import FakeOpener

import bug_fetch as bf
import jira_client as jc


# ---------------------------------------------------------------- ADF flattening

def test_flatten_adf_joins_paragraph_text():
    doc = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Steps to"},
                                          {"type": "text", "text": " reproduce"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "Open the quote"}]},
    ]}
    assert bf.flatten_adf(doc) == "Steps to reproduce Open the quote"


def test_flatten_adf_reaches_text_inside_lists_and_tables():
    doc = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "first"}]}]}]},
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "cell"}]}]}]}]},
    ]}
    assert bf.flatten_adf(doc) == "first cell"


@pytest.mark.parametrize("bad", [None, "", [], {}, {"content": "not-a-list"}, 42])
def test_flatten_adf_never_raises(bad):
    assert bf.flatten_adf(bad) == ""


def test_flatten_adf_collapses_whitespace():
    doc = {"content": [{"type": "text", "text": "a  \n\t b"}]}
    assert bf.flatten_adf(doc) == "a b"


# ------------------------------------------------------------------- excerpting

def test_excerpt_passes_short_text_through():
    assert bf.excerpt("short") == "short"


def test_excerpt_truncates_with_an_ellipsis_at_the_limit():
    out = bf.excerpt("x" * 500, limit=300)
    assert len(out) == 300 and out.endswith("…")


def test_excerpt_handles_none():
    assert bf.excerpt(None) == ""


# --------------------------------------------------------------- area assignment

@pytest.mark.parametrize("component,expected", [
    ("Frontend", "portal"), ("frontend", "portal"),
    ("Backend", "core"), (" BACKEND ", "core"),
])
def test_component_decides_the_area(component, expected):
    assert bf.area_of({"components": [{"name": component}]}) == expected


def test_component_wins_over_a_contradicting_summary_tag():
    fields = {"components": [{"name": "Backend"}], "summary": "[Front] broken"}
    assert bf.area_of(fields) == "core"


@pytest.mark.parametrize("summary,expected", [
    ("[Front] blank screen", "portal"),
    ("[ back ] NPE on save", "core"),
    ("[BACK] NPE", "core"),
])
def test_summary_tag_is_the_fallback(summary, expected):
    assert bf.area_of({"summary": summary}) == expected


@pytest.mark.parametrize("fields", [
    {}, {"components": []}, {"components": [{"name": "Testing"}]},
    {"summary": "[Rating] contract not applied"},
    {"summary": "front-end issue"},          # tag must be bracketed and leading
    {"summary": "fix [front] later"},
])
def test_unresolvable_area_is_none(fields):
    assert bf.area_of(fields) is None


# ------------------------------------------------------------- resolution filter

@pytest.mark.parametrize("resolution", [None, {}, {"name": "Done"}, {"name": "Fixed"}])
def test_real_defects_are_kept(resolution):
    assert bf.is_real_defect({"resolution": resolution}) is True


@pytest.mark.parametrize("name", ["Invalid", "invalid", "Duplicate", " DUPLICATE ",
                                  "Declined", " declined "])
def test_rejecting_resolutions_are_dropped(name):
    assert bf.is_real_defect({"resolution": {"name": name}}) is False


@pytest.mark.parametrize("name", ["Invalid", "invalid", " INVALID "])
def test_the_invalid_status_is_dropped_even_with_no_resolution(name):
    """Measured: this Jira rejects a bug via the STATUS Invalid, so a
    resolution-only filter would keep every one of them."""
    assert bf.is_real_defect({"status": {"name": name}, "resolution": None}) is False


def test_an_ordinary_status_is_kept():
    assert bf.is_real_defect({"status": {"name": "In Progress"}}) is True


# ------------------------------------------------------------------- the window

def test_window_defaults_to_the_last_30_days_ending_tomorrow():
    since, until = bf.resolve_window(None, None, today=date(2026, 9, 15))
    assert (since, until) == ("2026-08-17", "2026-09-16")


def test_until_is_exclusive_so_a_calendar_month_is_exact():
    since, until = bf.resolve_window("2026-08-01", "2026-09-01")
    assert (since, until) == ("2026-08-01", "2026-09-01")


def test_since_alone_is_honoured():
    since, until = bf.resolve_window("2026-01-01", None, today=date(2026, 9, 15))
    assert (since, until) == ("2026-01-01", "2026-09-16")


def test_until_alone_derives_since_30_days_earlier():
    assert bf.resolve_window(None, "2026-03-31") == ("2026-03-01", "2026-03-31")


def test_an_inverted_window_is_rejected():
    with pytest.raises(ValueError, match="must be before"):
        bf.resolve_window("2026-09-01", "2026-08-01")


# ---------------------------------------------------------------------- the JQL

def test_jql_quotes_sub_bug_and_uses_a_half_open_window():
    jql = bf.build_jql(["INTRD"], "2026-08-01", "2026-09-01")
    assert 'issuetype in (Bug, "Sub-bug")' in jql
    assert 'created >= "2026-08-01"' in jql and 'created < "2026-09-01"' in jql
    assert "project in (INTRD)" in jql


def test_jql_joins_several_projects():
    assert "project in (INTRD, MACRD)" in bf.build_jql(
        ["INTRD", "MACRD"], "2026-08-01", "2026-09-01")


# ----------------------------------------------------------------- normalisation

def issue(key="INTRD-1", **overrides):
    fields = {
        "summary": "[Rating] contract ignored",
        "description": {"content": [{"type": "text", "text": "long story"}]},
        "issuetype": {"name": "Bug"},
        "status": {"name": "In Progress",
                   "statusCategory": {"key": "indeterminate"}},
        "resolution": None,
        "components": [{"name": "Backend"}],
        "labels": ["billing"],
        "created": "2026-09-14T21:47:43.801+0200",
        "priority": {"name": "Major"},
        "assignee": {"displayName": "Adil El Jaouhari"},
        "reporter": {"displayName": "Mohamed Hamidi"},
        "parent": None,
    }
    fields.update(overrides)
    return {"key": key, "fields": fields}


def test_normalize_produces_the_shared_record_shape():
    rec = bf.normalize(issue())
    assert rec["key"] == "INTRD-1"
    assert rec["area"] == "core"
    assert rec["component"] == "Backend"
    assert rec["created"] == "2026-09-14"
    assert rec["status_category"] == "indeterminate"
    assert rec["excerpt"] == "long story"
    assert rec["assignee"] == "Adil El Jaouhari"
    assert rec["url"] == "https://opencellsoft.atlassian.net/browse/INTRD-1"
    assert rec["parent"] is None


def test_normalize_survives_every_optional_field_being_absent():
    rec = bf.normalize({"key": "INTRD-2", "fields": {"summary": "x"}})
    assert rec["area"] is None and rec["assignee"] is None
    assert rec["labels"] == [] and rec["excerpt"] == ""
    assert rec["created"] == ""


def test_normalize_records_the_parent_key_of_a_sub_bug():
    rec = bf.normalize(issue(issuetype={"name": "Sub-bug"},
                             parent={"key": "INTRD-900"}))
    assert rec["issuetype"] == "Sub-bug" and rec["parent"] == "INTRD-900"


# -------------------------------------------------------------------- collection

@pytest.mark.parametrize("repo,expected", [
    ("portal", {"portal"}), ("core", {"core"}), ("both", {"portal", "core"}),
])
def test_areas_in_scope(repo, expected):
    assert bf.areas_in_scope(repo) == expected


def client_for(issues, env):
    return jc.JiraClient(opener=FakeOpener([{"issues": issues, "isLast": True}]), env=env)


def test_collect_keeps_the_area_in_scope_and_all_unclassified(env):
    issues = [
        issue("INTRD-1", components=[{"name": "Frontend"}]),
        issue("INTRD-2", components=[{"name": "Backend"}]),
        issue("INTRD-3", components=[], summary="no tag at all"),
    ]
    doc = bf.collect(client_for(issues, env), "jql", "portal")

    assert [b["key"] for b in doc["bugs"]] == ["INTRD-1", "INTRD-3"]
    assert doc["fetched"] == 3


def test_collect_drops_invalid_and_counts_them(env):
    issues = [
        issue("INTRD-1"),
        issue("INTRD-2", resolution={"name": "Declined"}),
        issue("INTRD-3", status={"name": "Invalid",
                                 "statusCategory": {"key": "done"}}),
    ]
    doc = bf.collect(client_for(issues, env), "jql", "core")

    assert [b["key"] for b in doc["bugs"]] == ["INTRD-1"]
    assert doc["fetched"] == 3 and doc["dropped_invalid"] == 2


def test_classify_rows_are_compact_and_cover_only_classifiable_bugs(env):
    issues = [issue("INTRD-1"), issue("INTRD-2", components=[], summary="untagged")]
    doc = bf.collect(client_for(issues, env), "jql", "both")

    rows = bf.classify_rows(doc)

    assert [r["key"] for r in rows] == ["INTRD-1"], "unclassified bugs are not classified"
    assert set(rows[0]) == {"key", "summary", "excerpt", "component", "labels"}
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bug_fetch'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_fetch.py`:

```python
#!/usr/bin/env python3
"""Stage 1-2 of /oc-bug-clusters: fetch a window of bugs and resolve their area.

Everything in this module is deterministic. The area decides which Enabler a bug
ends up under, so it must not move between two runs of the same window — that is
why it is Python and not an LLM judgement.

Two files come out:
  bugs.json           the full normalised records; never read into model context
  classify_input.jsonl  one compact line per classifiable bug; the only file the
                        model reads
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta

from jira_client import BASE, JiraClient, MissingToken

# Area token -> the Jira component that means it. The two vocabularies are kept
# apart deliberately: the token is ours, the component name is Jira's.
AREA_COMPONENT = {"portal": "Frontend", "core": "Backend"}
COMPONENT_AREA = {"frontend": "portal", "backend": "core"}

# The fallback signal. Must be bracketed AND leading — "fix [front] later" is prose,
# not a tag, and treating it as one would mis-file the bug.
TAG = re.compile(r"^\s*\[\s*(front|back)", re.I)
TAG_AREA = {"front": "portal", "back": "core"}

# Measured against live INTRD data (2025-09 → 2026-09): "Invalid" is a Jira
# STATUS here (416 bugs carry it), never a resolution; the resolution the team
# uses to reject a bug is "Declined" (13 of a 100-bug sample). Filtering on
# resolution alone would therefore drop almost nothing.
DROPPED_RESOLUTIONS = {"invalid", "duplicate", "declined"}
DROPPED_STATUSES = {"invalid"}
EXCERPT_LIMIT = 300
DEFAULT_DAYS = 30

FIELDS = ["summary", "description", "issuetype", "status", "resolution", "components",
          "labels", "created", "priority", "assignee", "reporter", "parent"]

# ADF nodes that imply a word boundary when flattened.
BLOCK_TYPES = {"paragraph", "heading", "listItem", "tableRow", "tableCell",
               "codeBlock", "blockquote", "panel", "rule", "hardBreak"}


def flatten_adf(node):
    """Flatten an ADF document to plain text. Returns '' for anything unparseable.

    A bug with an unreadable description must still be classifiable from its summary,
    so this never raises.
    """
    parts = []

    def walk(n, depth=0):
        if depth > 50:
            return
        if isinstance(n, dict):
            if n.get("type") in BLOCK_TYPES:
                parts.append(" ")
            if n.get("type") == "text" and isinstance(n.get("text"), str):
                parts.append(n["text"])
            content = n.get("content")
            if isinstance(content, list):
                for child in content:
                    walk(child, depth + 1)
        elif isinstance(n, list):
            for child in n:
                walk(child, depth + 1)

    try:
        walk(node)
    except (TypeError, AttributeError, RecursionError, ValueError):
        return ""
    return " ".join("".join(parts).split())


def excerpt(text, limit=EXCERPT_LIMIT):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def area_of(fields):
    for component in fields.get("components") or []:
        area = COMPONENT_AREA.get((component.get("name") or "").strip().lower())
        if area:
            return area
    match = TAG.match(fields.get("summary") or "")
    if match:
        return TAG_AREA[match.group(1).lower()]
    return None


def is_real_defect(fields):
    """A bug the team accepted as a genuine defect.

    Checks BOTH fields: this Jira rejects a bug by moving it to the *status*
    Invalid, and separately records resolution Declined/Duplicate. Checking only
    one of the two lets rejected bugs into clusters.
    """
    resolution = (fields.get("resolution") or {}).get("name") or ""
    if resolution.strip().lower() in DROPPED_RESOLUTIONS:
        return False
    status = (fields.get("status") or {}).get("name") or ""
    return status.strip().lower() not in DROPPED_STATUSES


def resolve_window(since, until, today=None, days=DEFAULT_DAYS):
    """Resolve the half-open [since, until) window. `until` defaults to tomorrow so
    that bugs raised today are included."""
    today = today or date.today()
    end = date.fromisoformat(until) if until else today + timedelta(days=1)
    start = date.fromisoformat(since) if since else end - timedelta(days=days)
    if start >= end:
        raise ValueError(f"--since {start} must be before --until {end}")
    return start.isoformat(), end.isoformat()


def build_jql(projects, since, until):
    # "Sub-bug" is quoted: the hyphen breaks an unquoted JQL term.
    return (f'project in ({", ".join(projects)}) '
            f'AND issuetype in (Bug, "Sub-bug") '
            f'AND created >= "{since}" AND created < "{until}" '
            f'ORDER BY created DESC')


def _name(node):
    return (node or {}).get("name") or None


def _display(node):
    return (node or {}).get("displayName") or None


def normalize(issue):
    fields = issue.get("fields") or {}
    components = fields.get("components") or []
    status = fields.get("status") or {}
    return {
        "key": issue.get("key"),
        "area": area_of(fields),
        "component": _name(components[0]) if components else None,
        "summary": fields.get("summary") or "",
        "excerpt": excerpt(flatten_adf(fields.get("description"))),
        "issuetype": _name(fields.get("issuetype")),
        "status": _name(status),
        "status_category": ((status.get("statusCategory") or {}).get("key")) or None,
        "resolution": _name(fields.get("resolution")),
        "created": (fields.get("created") or "")[:10],
        "assignee": _display(fields.get("assignee")),
        "reporter": _display(fields.get("reporter")),
        "labels": list(fields.get("labels") or []),
        "priority": _name(fields.get("priority")),
        "parent": (fields.get("parent") or {}).get("key"),
        "url": f"{BASE}/browse/{issue.get('key')}",
    }


def areas_in_scope(repo):
    return {"portal": {"portal"}, "core": {"core"}, "both": {"portal", "core"}}[repo]


def collect(client, jql, repo):
    """Fetch, filter and normalise. Bugs of the area NOT in scope are excluded;
    bugs with no resolvable area are always kept, so the loss stays visible."""
    scope = areas_in_scope(repo)
    bugs, fetched, dropped = [], 0, 0
    for issue in client.search(jql, FIELDS):
        fetched += 1
        fields = issue.get("fields") or {}
        if not is_real_defect(fields):
            dropped += 1
            continue
        record = normalize(issue)
        if record["area"] is None or record["area"] in scope:
            bugs.append(record)
    return {"repo": repo, "fetched": fetched, "dropped_invalid": dropped, "bugs": bugs}


def classify_rows(document):
    """The compact lines the model reads. Unclassified bugs are not classified —
    they can never join a cluster, so spending context on them is waste."""
    return [{"key": b["key"], "summary": b["summary"], "excerpt": b["excerpt"],
             "component": b["component"], "labels": b["labels"]}
            for b in document["bugs"] if b["area"] is not None]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch and area-tag a window of Jira bugs.")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--repo", default="portal", choices=["portal", "core", "both"])
    parser.add_argument("--out-bugs", required=True)
    parser.add_argument("--out-classify", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = JiraClient()
    except (MissingToken, ValueError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    projects = [p.strip() for p in args.project.split(",") if p.strip()]
    document = collect(client, build_jql(projects, since, until), args.repo)
    document["window"] = {"since": since, "until": until}
    document["projects"] = projects

    with open(args.out_bugs, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    with open(args.out_classify, "w", encoding="utf-8") as handle:
        for row in classify_rows(document):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    kept = len(document["bugs"])
    unclassified = sum(1 for b in document["bugs"] if b["area"] is None)
    sys.stderr.write(
        f"Analysing {', '.join(projects)} bugs, {args.repo}, {since} → {until}\n"
        f"  fetched {document['fetched']}, dropped-invalid {document['dropped_invalid']}, "
        f"kept {kept} ({unclassified} with no resolvable area)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_fetch.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: fetch and area-tag a window of Jira bugs

Deterministic area assignment (component, then a leading [front]/[back]
tag), Invalid/Duplicate filtering, ADF flattening to a 300-char excerpt,
and the half-open window that makes a calendar month exact.

Emits bugs.json (never read into model context) and the compact
classify_input.jsonl the classification step reads.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 4: `bug_cluster.py` — the cluster model

Stage 4's logic, with no rendering and no network. Turning `bugs.json` plus
`assignments.json` into the model every renderer and the Jira writer consume.

**Files:**
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_cluster.py`
- Create: `plugins/common/oc-bug-clusters/tests/test_bug_cluster.py`

**Interfaces:**
- Consumes: `bug_fetch.AREA_COMPONENT`, and the `bugs.json` document + bug-record
  shapes from Task 3.
- Produces, for Tasks 5 and 6:
  - `class MissingAssignments(RuntimeError)` with attribute `.keys -> list[str]`
  - `seeded_subjects(path) -> list[str]` — the `## <subject>` headings of `subjects.md`
  - `build_model(document, assignments, min_cluster, seeded=()) -> model`

  ```python
  model = {
    "window": {"since": str, "until": str}, "projects": [str], "repo": str,
    "min_cluster": int, "fetched": int, "dropped_invalid": int, "kept": int,
    "areas": {                       # in scope only, always portal before core
      "portal": {"component": "Frontend", "bugs": int, "clustered_bugs": int,
                 "clusters": [group], "near": [group]},
    },
    "unclassified": [record],
  }
  group = {"subject": str, "count": int, "bugs": [record], "open": int,
           "closed": int, "labels": [[str, int]], "first_created": str,
           "last_created": str, "is_new": bool}
  ```

- [ ] **Step 1: Write the failing test**

Create `plugins/common/oc-bug-clusters/tests/test_bug_cluster.py`:

```python
import pytest

import bug_cluster as bc


def bug(key, area, created="2026-08-20", category="indeterminate", labels=()):
    return {"key": key, "area": area, "component": None, "summary": f"s {key}",
            "excerpt": "", "issuetype": "Bug", "status": "In Progress",
            "status_category": category, "resolution": None, "created": created,
            "assignee": None, "reporter": None, "labels": list(labels),
            "priority": "Major", "parent": None,
            "url": f"https://opencellsoft.atlassian.net/browse/{key}"}


def document(bugs, repo="portal", **extra):
    doc = {"window": {"since": "2026-08-01", "until": "2026-09-01"},
           "projects": ["INTRD"], "repo": repo, "fetched": len(bugs),
           "dropped_invalid": 0, "bugs": bugs}
    doc.update(extra)
    return doc


def spread(prefix, area, n, subject, assignments):
    bugs = []
    for i in range(n):
        key = f"{prefix}-{i}"
        bugs.append(bug(key, area))
        assignments[key] = subject
    return bugs


# --------------------------------------------------------------- the threshold

def test_a_subject_at_the_threshold_becomes_a_cluster():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert [c["subject"] for c in portal["clusters"]] == ["quoting"]
    assert portal["clusters"][0]["count"] == 5
    assert portal["near"] == []


def test_a_subject_one_below_the_threshold_is_a_near_cluster():
    assignments = {}
    bugs = spread("P", "portal", 4, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert portal["clusters"] == []
    assert [(g["subject"], g["count"]) for g in portal["near"]] == [("quoting", 4)]


def test_the_threshold_is_configurable():
    assignments = {}
    bugs = spread("P", "portal", 3, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=3)
    assert [c["subject"] for c in model["areas"]["portal"]["clusters"]] == ["quoting"]


# ------------------------------------------------------------------- ordering

def test_clusters_are_ordered_by_size_then_subject():
    assignments = {}
    bugs = (spread("A", "portal", 5, "rating", assignments)
            + spread("B", "portal", 7, "quoting", assignments)
            + spread("C", "portal", 5, "invoicing", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    assert [c["subject"] for c in model["areas"]["portal"]["clusters"]] == [
        "quoting", "invoicing", "rating"]


def test_bugs_inside_a_cluster_are_newest_first():
    assignments = {"P-1": "quoting", "P-2": "quoting", "P-3": "quoting",
                   "P-4": "quoting", "P-5": "quoting"}
    bugs = [bug("P-1", "portal", created="2026-08-01"),
            bug("P-2", "portal", created="2026-08-30"),
            bug("P-3", "portal", created="2026-08-15"),
            bug("P-4", "portal", created="2026-08-10"),
            bug("P-5", "portal", created="2026-08-20")]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    keys = [b["key"] for b in model["areas"]["portal"]["clusters"][0]["bugs"]]
    assert keys == ["P-2", "P-5", "P-3", "P-4", "P-1"]


# --------------------------------------------------------------- area isolation

def test_areas_never_share_a_cluster():
    assignments = {}
    bugs = (spread("P", "portal", 3, "quoting", assignments)
            + spread("C", "core", 3, "quoting", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)

    assert model["areas"]["portal"]["clusters"] == []
    assert model["areas"]["core"]["clusters"] == []
    assert model["areas"]["portal"]["near"][0]["count"] == 3
    assert model["areas"]["core"]["near"][0]["count"] == 3


def test_only_areas_in_scope_appear():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments)
    model = bc.build_model(document(bugs, repo="portal"), assignments, min_cluster=5)
    assert list(model["areas"]) == ["portal"]


def test_both_lists_portal_before_core():
    assignments = {}
    bugs = (spread("C", "core", 5, "rating", assignments)
            + spread("P", "portal", 5, "quoting", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    assert list(model["areas"]) == ["portal", "core"]
    assert model["areas"]["portal"]["component"] == "Frontend"
    assert model["areas"]["core"]["component"] == "Backend"


# ------------------------------------------------------------- unclassified tail

def test_unclassified_bugs_are_carried_but_never_clustered():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments) + [bug("U-1", None)]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    assert [b["key"] for b in model["unclassified"]] == ["U-1"]
    assert model["areas"]["portal"]["bugs"] == 5


def test_an_unclassified_bug_needs_no_assignment():
    model = bc.build_model(document([bug("U-1", None)]), {}, min_cluster=5)
    assert len(model["unclassified"]) == 1


# ------------------------------------------------------------ missing assignment

def test_a_bug_without_an_assignment_fails_loudly():
    bugs = [bug("P-1", "portal"), bug("P-2", "portal")]
    with pytest.raises(bc.MissingAssignments) as ex:
        bc.build_model(document(bugs), {"P-1": "quoting"}, min_cluster=5)
    assert ex.value.keys == ["P-2"]
    assert "P-2" in str(ex.value)


# ------------------------------------------------------------------ group stats

def test_group_counts_open_and_closed_by_status_category():
    assignments = {f"P-{i}": "quoting" for i in range(5)}
    bugs = [bug("P-0", "portal", category="done"),
            bug("P-1", "portal", category="done"),
            bug("P-2", "portal", category="new"),
            bug("P-3", "portal", category="indeterminate"),
            bug("P-4", "portal", category=None)]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    cluster = model["areas"]["portal"]["clusters"][0]
    assert cluster["closed"] == 2 and cluster["open"] == 3


def test_group_reports_its_top_labels_and_date_span():
    assignments = {f"P-{i}": "quoting" for i in range(5)}
    bugs = [bug("P-0", "portal", created="2026-08-02", labels=["billing", "TNR"]),
            bug("P-1", "portal", created="2026-08-09", labels=["billing"]),
            bug("P-2", "portal", created="2026-08-21", labels=["billing"]),
            bug("P-3", "portal", created="2026-08-11", labels=["TNR"]),
            bug("P-4", "portal", created="2026-08-15", labels=[])]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    cluster = model["areas"]["portal"]["clusters"][0]
    assert cluster["labels"][0] == ["billing", 3]
    assert cluster["first_created"] == "2026-08-02"
    assert cluster["last_created"] == "2026-08-21"


def test_clustered_bug_count_excludes_near_clusters():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 2, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert portal["bugs"] == 8 and portal["clustered_bugs"] == 6


# ------------------------------------------------------------------ new subjects

def test_a_subject_outside_the_taxonomy_is_flagged_new():
    assignments = {}
    bugs = (spread("A", "portal", 5, "quoting", assignments)
            + spread("B", "portal", 5, "webhooks", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5,
                           seeded=["quoting", "rating"])

    flags = {c["subject"]: c["is_new"] for c in model["areas"]["portal"]["clusters"]}
    assert flags == {"quoting": False, "webhooks": True}


def test_seeded_subjects_reads_the_taxonomy_headings(tmp_path):
    path = tmp_path / "subjects.md"
    path.write_text("# Title\n\n## rating\nPrices.\n\n## quoting\nQuotes.\n")
    assert bc.seeded_subjects(path) == ["rating", "quoting"]


def test_model_carries_the_window_and_counters_through():
    model = bc.build_model(
        document([], **{"fetched": 149, "dropped_invalid": 14}), {}, min_cluster=5)
    assert model["window"]["since"] == "2026-08-01"
    assert model["fetched"] == 149 and model["dropped_invalid"] == 14
    assert model["kept"] == 0 and model["min_cluster"] == 5
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_cluster.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bug_cluster'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_cluster.py`.
Renderers are added in Task 5; this step writes the model only:

```python
#!/usr/bin/env python3
"""Stage 4 of /oc-bug-clusters: bugs + subject assignments -> the cluster model.

No network, no rendering. The model is the one shape the Markdown/CSV/HTML
renderers and the Jira writer all read, so it is built once and asserted here.
"""
import re
from collections import Counter

from bug_fetch import AREA_COMPONENT

AREA_ORDER = ["portal", "core"]
SUBJECT_HEADING = re.compile(r"^## ([a-z0-9-]+)$", re.M)
TOP_LABELS = 3


class MissingAssignments(RuntimeError):
    """A classifiable bug came back with no subject.

    Raised rather than dropped: a silently missing bug is one that never reaches a
    cluster and never reaches the report, which is indistinguishable from a bug that
    genuinely had no peers.
    """

    def __init__(self, keys):
        self.keys = list(keys)
        shown = ", ".join(self.keys[:10])
        more = f" (+{len(self.keys) - 10} more)" if len(self.keys) > 10 else ""
        super().__init__(f"no subject assigned for: {shown}{more}")


def seeded_subjects(path):
    with open(path, encoding="utf-8") as handle:
        return SUBJECT_HEADING.findall(handle.read())


def _group(subject, bugs, seeded):
    bugs = sorted(bugs, key=lambda b: (b["created"], b["key"]), reverse=True)
    labels = Counter(label for b in bugs for label in b["labels"])
    dates = sorted(b["created"] for b in bugs if b["created"])
    closed = sum(1 for b in bugs if b["status_category"] == "done")
    return {
        "subject": subject,
        "count": len(bugs),
        "bugs": bugs,
        "open": len(bugs) - closed,
        "closed": closed,
        "labels": [[name, n] for name, n in labels.most_common(TOP_LABELS)],
        "first_created": dates[0] if dates else "",
        "last_created": dates[-1] if dates else "",
        "is_new": subject not in set(seeded),
    }


def build_model(document, assignments, min_cluster, seeded=()):
    bugs = document["bugs"]
    classifiable = [b for b in bugs if b["area"] is not None]
    missing = [b["key"] for b in classifiable if b["key"] not in assignments]
    if missing:
        raise MissingAssignments(missing)

    scope = [a for a in AREA_ORDER
             if a in {"portal": {"portal"}, "core": {"core"},
                      "both": {"portal", "core"}}[document["repo"]]]

    areas = {}
    for area in scope:
        mine = [b for b in classifiable if b["area"] == area]
        by_subject = {}
        for b in mine:
            by_subject.setdefault(assignments[b["key"]], []).append(b)
        groups = [_group(subject, members, seeded)
                  for subject, members in by_subject.items()]
        groups.sort(key=lambda g: (-g["count"], g["subject"]))
        clusters = [g for g in groups if g["count"] >= min_cluster]
        areas[area] = {
            "component": AREA_COMPONENT[area],
            "bugs": len(mine),
            "clustered_bugs": sum(g["count"] for g in clusters),
            "clusters": clusters,
            "near": [g for g in groups if g["count"] < min_cluster],
        }

    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "min_cluster": min_cluster,
        "fetched": document["fetched"],
        "dropped_invalid": document["dropped_invalid"],
        "kept": len(bugs),
        "areas": areas,
        "unclassified": sorted((b for b in bugs if b["area"] is None),
                               key=lambda b: b["key"]),
    }
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_cluster.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: build the bug cluster model

Groups by (area, subject), promotes any group at or above --min-cluster,
keeps the rest as near-clusters so a subject sitting one short stays
visible. Areas never share a cluster, and a classifiable bug with no
subject raises rather than disappearing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 5: `bug_cluster.py` — Markdown, CSV and HTML renderings

Same file as Task 4, second responsibility: turning the model into the three outputs,
plus the CLI that wires stage 4 together and writes `model.json` for stage 5.

**Files:**
- Modify: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_cluster.py` (append)
- Create: `plugins/common/oc-bug-clusters/tests/test_bug_render.py`

**Interfaces:**
- Consumes: the `model` from Task 4.
- Produces, for Task 8:
  - `render_markdown(model) -> str`
  - `render_csv_rows(model) -> list[list[str]]` — header row first
  - `render_html(model) -> str` — one self-contained document
  - CLI: `bug_cluster.py --bugs B --assignments A --subjects S --min-cluster N
    --out H --csv C --model M`

- [ ] **Step 1: Write the failing test**

Create `plugins/common/oc-bug-clusters/tests/test_bug_render.py`:

```python
import bug_cluster as bc
from test_bug_cluster import bug, document, spread


def model_with(repo="portal", n=6, subject="quoting", extra_bugs=(), assignments=None):
    assignments = {} if assignments is None else assignments
    bugs = spread("P", "portal", n, subject, assignments) + list(extra_bugs)
    return bc.build_model(document(bugs, repo=repo), assignments, min_cluster=5)


# -------------------------------------------------------------------- Markdown

def test_markdown_states_the_window_and_the_counters():
    text = bc.render_markdown(model_with())
    assert "2026-08-01" in text and "2026-09-01" in text
    assert "INTRD" in text


def test_markdown_shows_each_cluster_with_its_size():
    text = bc.render_markdown(model_with(subject="quoting", n=7))
    assert "quoting" in text and "7" in text


def test_markdown_lists_every_bug_key_of_a_cluster():
    assignments = {}
    text = bc.render_markdown(model_with(n=5, assignments=assignments))
    for key in assignments:
        assert key in text


def test_markdown_names_the_near_clusters_with_their_counts():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 3, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    text = bc.render_markdown(model)
    assert "rating" in text and "Near-clusters" in text


def test_markdown_lists_unclassified_bugs():
    text = bc.render_markdown(model_with(extra_bugs=[bug("U-1", None)]))
    assert "U-1" in text and "Unclassified" in text


def test_markdown_says_so_when_an_area_has_no_cluster():
    model = bc.build_model(document([]), {}, min_cluster=5)
    assert "No cluster" in bc.render_markdown(model)


def test_markdown_marks_a_subject_coined_outside_the_taxonomy():
    assignments = {}
    bugs = spread("A", "portal", 5, "webhooks", assignments)
    model = bc.build_model(document(bugs), assignments, 5, seeded=["quoting"])
    assert "new" in bc.render_markdown(model).lower()


def test_markdown_covers_both_areas():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    text = bc.render_markdown(model)
    assert "Frontend" in text and "Backend" in text


# ------------------------------------------------------------------------- CSV

def test_csv_starts_with_a_header_row():
    rows = bc.render_csv_rows(model_with())
    assert rows[0] == ["key", "area", "component", "subject", "in_cluster",
                       "status", "created", "assignee", "labels", "summary", "url"]


def test_csv_has_one_row_per_kept_bug_including_unclassified():
    rows = bc.render_csv_rows(model_with(n=6, extra_bugs=[bug("U-1", None)]))
    assert len(rows) == 1 + 7


def test_csv_marks_whether_a_bug_reached_a_cluster():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 2, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    flags = {r[0]: r[4] for r in bc.render_csv_rows(model)[1:]}
    assert flags["A-0"] == "yes" and flags["B-0"] == "no"


def test_csv_leaves_an_unclassified_bug_without_a_subject():
    rows = bc.render_csv_rows(model_with(extra_bugs=[bug("U-1", None)]))
    row = next(r for r in rows if r[0] == "U-1")
    assert row[1] == "" and row[3] == "" and row[4] == "no"


def test_csv_joins_labels_with_a_space():
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal", labels=["billing", "TNR"])]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    assert bc.render_csv_rows(model)[1][8] == "billing TNR"


# ------------------------------------------------------------------------ HTML

def test_html_is_a_complete_document():
    html = bc.render_html(model_with())
    assert html.lstrip().startswith("<!doctype html>")
    assert "</html>" in html and "<style>" in html


def test_html_escapes_markup_in_a_summary():
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal")]
    bugs[0]["summary"] = "<script>alert(1)</script> & co"
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    html = bc.render_html(model)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "&amp; co" in html


def test_html_links_every_bug_key_to_jira():
    html = bc.render_html(model_with(n=5))
    assert 'href="https://opencellsoft.atlassian.net/browse/P-0"' in html


def test_html_has_one_tab_per_area_when_both_are_in_scope():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    html = bc.render_html(model)
    assert html.count('class="tab"') == 2


def test_html_omits_the_tab_bar_for_a_single_area():
    assert 'class="tab"' not in bc.render_html(model_with())
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_render.py -q`
Expected: FAIL — `AttributeError: module 'bug_cluster' has no attribute 'render_markdown'`.

- [ ] **Step 3: Append the renderers and the CLI to `bug_cluster.py`**

Replace the import block at the top of `bug_cluster.py` with the final set:

```python
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
from collections import Counter
from datetime import date

from bug_fetch import AREA_COMPONENT
```

Then append:

```python
# --------------------------------------------------------------------- Markdown

def _window_line(model):
    w = model["window"]
    return (f"**{', '.join(model['projects'])}** · bugs created "
            f"`{w['since']}` → `{w['until']}` (exclusive) · "
            f"cluster threshold **{model['min_cluster']}**")


def _counter_line(model):
    unclassified = len(model["unclassified"])
    return (f"Fetched **{model['fetched']}** · dropped Invalid/Duplicate "
            f"**{model['dropped_invalid']}** · kept **{model['kept']}** · "
            f"no resolvable area **{unclassified}**")


def _group_line(group):
    labels = ", ".join(f"{name} ×{n}" for name, n in group["labels"]) or "—"
    flag = " **(new subject)**" if group["is_new"] else ""
    return (f"| `{group['subject']}`{flag} | {group['count']} | {group['open']} | "
            f"{group['closed']} | {labels} | {group['first_created']} → "
            f"{group['last_created']} |")


def render_markdown(model):
    out = ["# Bug clusters", "", _window_line(model), "", _counter_line(model), ""]

    for area, data in model["areas"].items():
        out += [f"## {data['component']} (`{area}`) — {data['bugs']} bugs", ""]
        if not data["clusters"]:
            out += [f"_No cluster reached {model['min_cluster']} bugs._", ""]
        else:
            out += [f"{data['clustered_bugs']} of {data['bugs']} bugs fall into "
                    f"{len(data['clusters'])} cluster(s).", "",
                    "| Subject | Bugs | Open | Closed | Top labels | Span |",
                    "|---|---:|---:|---:|---|---|"]
            out += [_group_line(g) for g in data["clusters"]]
            out.append("")
            for cluster in data["clusters"]:
                out += [f"### `{cluster['subject']}` — {cluster['count']} bugs", ""]
                for b in cluster["bugs"]:
                    out.append(f"- [{b['key']}]({b['url']}) · {b['status']} · "
                               f"{b['created']} · {b['summary']}")
                out.append("")
        if data["near"]:
            out += [f"**Near-clusters** (below {model['min_cluster']}): "
                    + ", ".join(f"`{g['subject']}` {g['count']}" for g in data["near"]),
                    ""]

    if model["unclassified"]:
        out += [f"## Unclassified — {len(model['unclassified'])} bugs", "",
                "_No Jira component and no leading `[front]`/`[back]` tag, so these "
                "were not clustered._", ""]
        out += [f"- [{b['key']}]({b['url']}) · {b['summary']}"
                for b in model["unclassified"]]
        out.append("")

    return "\n".join(out)


# -------------------------------------------------------------------------- CSV

CSV_HEADER = ["key", "area", "component", "subject", "in_cluster", "status",
              "created", "assignee", "labels", "summary", "url"]


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]

    def row(bug, area, subject, in_cluster):
        return [bug["key"], area or "", bug["component"] or "", subject or "",
                "yes" if in_cluster else "no", bug["status"] or "", bug["created"],
                bug["assignee"] or "", " ".join(bug["labels"]), bug["summary"],
                bug["url"]]

    for area, data in model["areas"].items():
        for group in data["clusters"]:
            rows += [row(b, area, group["subject"], True) for b in group["bugs"]]
        for group in data["near"]:
            rows += [row(b, area, group["subject"], False) for b in group["bugs"]]
    rows += [row(b, None, None, False) for b in model["unclassified"]]
    return rows


# ------------------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f7f7f8;--fg:#1d1d1f;--mut:#6b6b72;--line:#e3e3e6;--card:#fff;--accent:#2f6fd0}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
h3{font-size:14px;margin:20px 0 6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.meta{color:var(--mut);margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:16px 18px;margin-bottom:18px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);
 vertical-align:top}
th{color:var(--mut);font-weight:600;white-space:nowrap}
td.n,th.n{text-align:right}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.sub{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.new{background:#fde7c7;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.pill{background:#eef1f5;border-radius:4px;padding:1px 6px;font-size:12px;color:var(--mut)}
.tabs{display:flex;gap:6px;margin:18px 0 12px}
.tab{padding:7px 14px;border:1px solid var(--line);border-radius:8px;cursor:pointer;
 background:var(--card)}
.tab[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--mut);font-style:italic}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ededf0;--mut:#9a9aa3;
 --line:#2c2c31;--card:#1c1c20;--accent:#6ea8ff}.new{background:#5a4420}
 .pill{background:#26262b}}
"""

TAB_JS = """
document.querySelectorAll('.tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(t){
      t.setAttribute('aria-selected', String(t === tab));
    });
    document.querySelectorAll('section[data-area]').forEach(function(s){
      s.hidden = s.dataset.area !== tab.dataset.area;
    });
  });
});
"""


def _e(value):
    return html_mod.escape(str(value if value is not None else ""))


def _bug_rows_html(bugs):
    out = []
    for b in bugs:
        out.append(
            f'<tr><td><a href="{_e(b["url"])}">{_e(b["key"])}</a></td>'
            f'<td>{_e(b["summary"])}</td><td>{_e(b["status"])}</td>'
            f'<td>{_e(b["created"])}</td><td>{_e(b["assignee"] or "—")}</td></tr>')
    return "".join(out)


def _area_html(model, area, data):
    parts = [f'<section data-area="{_e(area)}">',
             f'<h2>{_e(data["component"])} — {data["bugs"]} bugs</h2>']

    if not data["clusters"]:
        parts.append(f'<p class="empty">No cluster reached '
                     f'{model["min_cluster"]} bugs.</p>')
    else:
        parts.append('<div class="card"><table><tr><th>Subject</th>'
                     '<th class="n">Bugs</th><th class="n">Open</th>'
                     '<th class="n">Closed</th><th>Top labels</th><th>Span</th></tr>')
        for g in data["clusters"]:
            flag = '<span class="new">new</span>' if g["is_new"] else ""
            labels = ", ".join(f"{_e(n)} ×{c}" for n, c in g["labels"]) or "—"
            parts.append(
                f'<tr><td><span class="sub">{_e(g["subject"])}</span>{flag}</td>'
                f'<td class="n">{g["count"]}</td><td class="n">{g["open"]}</td>'
                f'<td class="n">{g["closed"]}</td><td>{labels}</td>'
                f'<td>{_e(g["first_created"])} → {_e(g["last_created"])}</td></tr>')
        parts.append("</table></div>")

        for g in data["clusters"]:
            parts.append(f'<h3>{_e(g["subject"])} — {g["count"]} bugs</h3>'
                         '<div class="card"><table><tr><th>Key</th><th>Summary</th>'
                         '<th>Status</th><th>Created</th><th>Assignee</th></tr>'
                         + _bug_rows_html(g["bugs"]) + "</table></div>")

    if data["near"]:
        pills = " ".join(f'<span class="pill">{_e(g["subject"])} {g["count"]}</span>'
                         for g in data["near"])
        parts.append(f'<h3>Near-clusters (below {model["min_cluster"]})</h3>'
                     f'<div class="card">{pills}</div>')

    parts.append("</section>")
    return "".join(parts)


def render_html(model):
    w = model["window"]
    title = f"Bug clusters {w['since']} → {w['until']}"
    areas = list(model["areas"].items())

    body = [f"<h1>{_e(title)}</h1>",
            f'<p class="meta">{_e(", ".join(model["projects"]))} · threshold '
            f'{model["min_cluster"]} · fetched {model["fetched"]} · dropped '
            f'{model["dropped_invalid"]} · kept {model["kept"]} · generated '
            f'{_e(date.today().isoformat())}</p>']

    if len(areas) > 1:
        body.append('<div class="tabs">' + "".join(
            f'<div class="tab" data-area="{_e(a)}" role="tab" '
            f'aria-selected="{"true" if i == 0 else "false"}">{_e(d["component"])}'
            f'</div>' for i, (a, d) in enumerate(areas)) + "</div>")

    for index, (area, data) in enumerate(areas):
        section = _area_html(model, area, data)
        if len(areas) > 1 and index > 0:
            section = section.replace(f'<section data-area="{_e(area)}">',
                                      f'<section data-area="{_e(area)}" hidden>', 1)
        body.append(section)

    if model["unclassified"]:
        body.append(f'<h2>Unclassified — {len(model["unclassified"])} bugs</h2>'
                    '<p class="meta">No Jira component and no leading '
                    '<code>[front]</code>/<code>[back]</code> tag, so these were not '
                    'clustered.</p><div class="card"><table>'
                    '<tr><th>Key</th><th>Summary</th><th>Status</th><th>Created</th>'
                    '<th>Assignee</th></tr>'
                    + _bug_rows_html(model["unclassified"]) + "</table></div>")

    script = f"<script>{TAB_JS}</script>" if len(areas) > 1 else ""
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_e(title)}</title><style>{CSS}</style></head><body>"
            + "".join(body) + script + "</body></html>\n")


# -------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="Cluster classified bugs and report.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--assignments", required=True)
    parser.add_argument("--subjects", required=True)
    parser.add_argument("--min-cluster", type=int, default=5)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        document = json.load(handle)
    with open(args.assignments, encoding="utf-8") as handle:
        assignments = json.load(handle)

    try:
        model = build_model(document, assignments, args.min_cluster,
                            seeded_subjects(args.subjects))
    except MissingAssignments as ex:
        sys.stderr.write(f"{ex}\nClassify these and re-run.\n")
        return 2

    for path in (args.out, args.csv, args.model):
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)

    with open(args.model, "w", encoding="utf-8") as handle:
        json.dump(model, handle, ensure_ascii=False, indent=1)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render_html(model))
    with open(args.csv, "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(render_csv_rows(model))

    sys.stdout.write(render_markdown(model))
    sys.stderr.write(f"\nHTML: {args.out}\nCSV:  {args.csv}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Verify the CLI end to end on fixture data**

```bash
cd "$(git rev-parse --show-toplevel)"
S=plugins/common/oc-bug-clusters/skills/oc-bug-clusters
T=$(mktemp -d)
python3 - "$T" <<'PY'
import json, sys
t = sys.argv[1]
bugs = [{"key": f"INTRD-{i}", "area": "portal", "component": "Frontend",
         "summary": f"[Quote] broken {i}", "excerpt": "", "issuetype": "Bug",
         "status": "Open", "status_category": "new", "resolution": None,
         "created": "2026-08-20", "assignee": None, "reporter": None,
         "labels": ["billing"], "priority": "Major", "parent": None,
         "url": f"https://opencellsoft.atlassian.net/browse/INTRD-{i}"}
        for i in range(6)]
json.dump({"window": {"since": "2026-08-01", "until": "2026-09-01"},
           "projects": ["INTRD"], "repo": "portal", "fetched": 6,
           "dropped_invalid": 0, "bugs": bugs}, open(f"{t}/bugs.json", "w"))
json.dump({b["key"]: "quoting" for b in bugs}, open(f"{t}/assignments.json", "w"))
PY
python3 "$S/scripts/bug_cluster.py" --bugs "$T/bugs.json" \
  --assignments "$T/assignments.json" --subjects "$S/references/subjects.md" \
  --min-cluster 5 --out "$T/r.html" --csv "$T/r.csv" --model "$T/model.json"
echo "--- csv ---"; head -3 "$T/r.csv"
```
Expected: Markdown on stdout showing a `quoting` cluster of 6, and a CSV whose
header row is followed by 6 data rows.

- [ ] **Step 6: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: render the cluster model as Markdown, CSV and HTML

Self-contained themed HTML with a tab per area when both are in scope,
every bug key linked to Jira and every summary escaped; CSV carries one
row per kept bug including the unclassified tail.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 6: `bug_enabler.py` — payloads and the write plan

The pure half of stage 5. Splitting the planner from the applier is what lets the
skill show the user exactly what will be created before anything is.

**Files:**
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_enabler.py`
- Create: `plugins/common/oc-bug-clusters/tests/test_bug_enabler.py`

**Interfaces:**
- Consumes: the `model` from Task 4.
- Produces, for Task 7:
  - `ENABLER_TYPE_ID = "10076"`, `SUBTASK_TYPE_ID = "10003"`
  - `DEFAULT_ASSIGNEE = {"portal": "5ef5c13914f60e0ac1c9b049",
                         "core": "63369fa788ed2ebef97cddfb"}`
  - `marker_label(area, since, until) -> str`
  - `adf_doc(blocks) -> dict`, `adf_para(text) -> dict`, `adf_bullets(items) -> dict`
  - `enabler_fields(project, area, model, assignee, report_path) -> dict`
  - `subtask_fields(project, cluster, assignee) -> dict` — **no `parent`**; the
    applier injects it once the Enabler key exists
  - `build_plan(model, project, assignees, report_path) -> plan`

    ```python
    plan = {"project": str, "calls": int, "areas": [
      {"area": str, "component": str, "marker": str, "assignee": str,
       "enabler": {"fields": dict},
       "subtasks": [{"subject": str, "fields": dict, "links": [str]}]}]}
    ```
  - `render_plan(plan) -> str`
  - `required_field_ids(meta) -> set[str]`, `missing_required(meta, fields) -> set[str]`

- [ ] **Step 1: Write the failing test**

Create `plugins/common/oc-bug-clusters/tests/test_bug_enabler.py`:

```python
import pytest

import bug_cluster as bc
import bug_enabler as be
from test_bug_cluster import document, spread


def model_for(repo="portal", sizes=(("quoting", 6),), area="portal"):
    assignments = {}
    bugs = []
    for index, (subject, n) in enumerate(sizes):
        bugs += spread(f"{area[0].upper()}{index}", area, n, subject, assignments)
    for b in bugs:
        b["area"] = area
    return bc.build_model(document(bugs, repo=repo), assignments, min_cluster=5)


def plan_for(**kwargs):
    model = kwargs.pop("model", None) or model_for()
    return be.build_plan(model, project="INTRD",
                         assignees=dict(be.DEFAULT_ASSIGNEE),
                         report_path="./docs/bug-clusters-2026-09-15.html", **kwargs)


# ------------------------------------------------------------------ marker label

def test_marker_label_uses_the_area_token_not_the_component():
    assert be.marker_label("portal", "2026-08-01", "2026-09-01") == \
        "bug-clusters-portal-2026-08-01-2026-09-01"


def test_marker_label_is_a_legal_jira_label():
    label = be.marker_label("core", "2026-08-01", "2026-09-01")
    assert " " not in label and label.islower()


# --------------------------------------------------------------------------- ADF

def test_adf_doc_has_the_shape_rest_v3_demands():
    doc = be.adf_doc([be.adf_para("hello")])
    assert doc["type"] == "doc" and doc["version"] == 1
    assert doc["content"][0]["content"][0]["text"] == "hello"


def test_adf_bullets_makes_one_list_item_per_entry():
    node = be.adf_bullets(["a", "b"])
    assert node["type"] == "bulletList" and len(node["content"]) == 2
    assert node["content"][0]["type"] == "listItem"


# ---------------------------------------------------------------- Enabler fields

def test_enabler_carries_type_project_component_and_assignee():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    assert fields["project"] == {"key": "INTRD"}
    assert fields["issuetype"] == {"id": be.ENABLER_TYPE_ID}
    assert fields["components"] == [{"name": "Frontend"}]
    assert fields["assignee"] == {"id": "5ef5c13914f60e0ac1c9b049"}


def test_enabler_summary_names_the_component_and_the_window():
    summary = plan_for()["areas"][0]["enabler"]["fields"]["summary"]
    assert summary == "Bug clusters — Frontend — 2026-08-01 → 2026-09-01"


def test_enabler_carries_the_marker_label():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    assert "bug-clusters-portal-2026-08-01-2026-09-01" in fields["labels"]


def test_enabler_description_mentions_the_clusters_and_the_report():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    text = str(fields["description"])
    assert "quoting" in text and "bug-clusters-2026-09-15.html" in text


def test_backend_enabler_gets_the_backend_defaults():
    plan = plan_for(model=model_for(repo="core", area="core"))
    fields = plan["areas"][0]["enabler"]["fields"]
    assert fields["components"] == [{"name": "Backend"}]
    assert fields["assignee"] == {"id": "63369fa788ed2ebef97cddfb"}


def test_an_assignee_override_is_honoured():
    model = model_for()
    plan = be.build_plan(model, project="INTRD",
                         assignees={"portal": "acc-999", "core": "x"},
                         report_path="r.html")
    assert plan["areas"][0]["enabler"]["fields"]["assignee"] == {"id": "acc-999"}


# ---------------------------------------------------------------- Sub-task fields

def test_one_subtask_per_cluster_named_subject_and_count():
    plan = plan_for(model=model_for(sizes=(("quoting", 7), ("rating", 5))))
    summaries = [s["fields"]["summary"] for s in plan["areas"][0]["subtasks"]]
    assert summaries == ["quoting — 7 bugs", "rating — 5 bugs"]


def test_subtask_inherits_the_enabler_assignee():
    area = plan_for()["areas"][0]
    assert area["subtasks"][0]["fields"]["assignee"] == area["enabler"]["fields"]["assignee"]


def test_subtask_has_no_parent_at_plan_time():
    assert "parent" not in plan_for()["areas"][0]["subtasks"][0]["fields"]


def test_subtask_uses_the_subtask_type_id():
    fields = plan_for()["areas"][0]["subtasks"][0]["fields"]
    assert fields["issuetype"] == {"id": be.SUBTASK_TYPE_ID}


def test_subtask_lists_every_bug_of_its_cluster_and_links_them():
    plan = plan_for(model=model_for(sizes=(("quoting", 6),)))
    subtask = plan["areas"][0]["subtasks"][0]
    assert len(subtask["links"]) == 6
    text = str(subtask["fields"]["description"])
    for key in subtask["links"]:
        assert key in text


# ------------------------------------------------------------------- plan shape

def test_near_clusters_never_become_subtasks():
    plan = plan_for(model=model_for(sizes=(("quoting", 6), ("rating", 2))))
    assert [s["subject"] for s in plan["areas"][0]["subtasks"]] == ["quoting"]


def test_an_area_with_no_cluster_is_absent_from_the_plan():
    plan = plan_for(model=model_for(sizes=(("quoting", 2),)))
    assert plan["areas"] == []


def test_both_areas_each_get_their_own_enabler():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    plan = be.build_plan(model, "INTRD", dict(be.DEFAULT_ASSIGNEE), "r.html")

    assert [a["component"] for a in plan["areas"]] == ["Frontend", "Backend"]
    assert len({a["marker"] for a in plan["areas"]}) == 2


def test_call_count_is_one_enabler_plus_subtasks_plus_links():
    plan = plan_for(model=model_for(sizes=(("quoting", 6), ("rating", 5))))
    assert plan["calls"] == 1 + 2 + 11


def test_render_plan_shows_every_summary_and_the_call_count():
    text = be.render_plan(plan_for(model=model_for(sizes=(("quoting", 6),))))
    assert "Bug clusters — Frontend" in text
    assert "quoting — 6 bugs" in text
    assert "8" in text            # 1 enabler + 1 subtask + 6 links


# ------------------------------------------------------------- createmeta guard

def test_required_fields_ignore_those_with_a_default():
    meta = {"fields": [
        {"fieldId": "summary", "required": True},
        {"fieldId": "reporter", "required": True, "hasDefaultValue": True},
        {"fieldId": "labels", "required": False},
    ]}
    assert be.required_field_ids(meta) == {"summary"}


def test_missing_required_names_what_the_payload_lacks():
    meta = {"fields": [{"fieldId": "summary", "required": True},
                       {"fieldId": "customfield_1", "required": True}]}
    assert be.missing_required(meta, {"summary": "x"}) == {"customfield_1"}


def test_missing_required_is_empty_when_the_payload_covers_everything():
    meta = {"fields": [{"fieldId": "summary", "required": True}]}
    assert be.missing_required(meta, {"summary": "x", "labels": []}) == set()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_enabler.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bug_enabler'`.

- [ ] **Step 3: Write the planner half of the implementation**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_enabler.py`.
The applier is added in Task 7:

```python
#!/usr/bin/env python3
"""Stage 5 of /oc-bug-clusters: create one Enabler per area, one Sub-task per cluster.

Split deliberately in two. `--plan` computes every payload and prints them, touching
nothing; `--apply` executes a plan. The confirmation gate therefore lives in the skill
between the two calls, rather than as an interactive prompt inside a script that
Claude Code runs non-interactively.
"""
ENABLER_TYPE_ID = "10076"
SUBTASK_TYPE_ID = "10003"

# Standing owner per area. Pinned by accountId: the Jira assignee field accepts
# nothing else, and display names drift.
DEFAULT_ASSIGNEE = {
    "portal": "5ef5c13914f60e0ac1c9b049",   # Mohamed Hamidi
    "core": "63369fa788ed2ebef97cddfb",     # Adil El Jaouhari
}

LINK_TYPE = "Relates"


def marker_label(area, since, until):
    """The label that makes a re-run of the same window a no-op.

    Built from the area TOKEN (portal/core), never the component name, so the label
    matches the --repo value a user would type.
    """
    return f"bug-clusters-{area}-{since}-{until}"


# ------------------------------------------------------------------------- ADF

def adf_para(text):
    node = {"type": "paragraph"}
    if text:
        node["content"] = [{"type": "text", "text": text}]
    return node


def adf_bullets(items):
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [adf_para(i)]} for i in items]}


def adf_doc(blocks):
    return {"type": "doc", "version": 1, "content": list(blocks)}


# --------------------------------------------------------------------- payloads

def enabler_fields(project, area, model, assignee, report_path):
    window = model["window"]
    data = model["areas"][area]
    overview = [
        f"{c['subject']} — {c['count']} bugs "
        f"({c['open']} open, {c['closed']} closed), "
        f"{c['first_created']} → {c['last_created']}"
        for c in data["clusters"]
    ]
    return {
        "project": {"key": project},
        "issuetype": {"id": ENABLER_TYPE_ID},
        "summary": (f"Bug clusters — {data['component']} — "
                    f"{window['since']} → {window['until']}"),
        "components": [{"name": data["component"]}],
        "assignee": {"id": assignee},
        "labels": [marker_label(area, window["since"], window["until"])],
        "description": adf_doc([
            adf_para(f"Bugs created {window['since']} → {window['until']} "
                     f"(exclusive) in {', '.join(model['projects'])}, "
                     f"component {data['component']}."),
            adf_para(f"{data['clustered_bugs']} of {data['bugs']} bugs fall into "
                     f"{len(data['clusters'])} cluster(s) of at least "
                     f"{model['min_cluster']} bugs on one subject."),
            adf_bullets(overview),
            adf_para(f"Full report: {report_path}"),
        ]),
    }


def subtask_fields(project, cluster, assignee):
    """Sub-task payload WITHOUT `parent` — the applier injects it once the Enabler
    key exists."""
    return {
        "project": {"key": project},
        "issuetype": {"id": SUBTASK_TYPE_ID},
        "summary": f"{cluster['subject']} — {cluster['count']} bugs",
        "assignee": {"id": assignee},
        "description": adf_doc([
            adf_para(f"{cluster['count']} bugs classified as "
                     f"'{cluster['subject']}' "
                     f"({cluster['open']} open, {cluster['closed']} closed), "
                     f"raised {cluster['first_created']} → {cluster['last_created']}."),
            adf_bullets([f"{b['key']} — {b['summary']}" for b in cluster["bugs"]]),
        ]),
    }


def build_plan(model, project, assignees, report_path):
    areas, calls = [], 0
    for area, data in model["areas"].items():
        if not data["clusters"]:
            continue
        assignee = assignees[area]
        subtasks = [{"subject": c["subject"],
                     "fields": subtask_fields(project, c, assignee),
                     "links": [b["key"] for b in c["bugs"]]}
                    for c in data["clusters"]]
        areas.append({
            "area": area,
            "component": data["component"],
            "marker": marker_label(area, model["window"]["since"],
                                   model["window"]["until"]),
            "assignee": assignee,
            "enabler": {"fields": enabler_fields(project, area, model, assignee,
                                                 report_path)},
            "subtasks": subtasks,
        })
        calls += 1 + len(subtasks) + sum(len(s["links"]) for s in subtasks)
    return {"project": project, "calls": calls, "areas": areas}


def render_plan(plan):
    if not plan["areas"]:
        return "No cluster reached the threshold — nothing to create.\n"
    out = [f"Will create in {plan['project']} ({plan['calls']} API calls):", ""]
    for area in plan["areas"]:
        out.append(f"  Enabler  {area['enabler']['fields']['summary']}")
        out.append(f"           component {area['component']} · "
                   f"assignee {area['assignee']} · label {area['marker']}")
        for subtask in area["subtasks"]:
            out.append(f"    Sub-task  {subtask['fields']['summary']}  "
                       f"(+{len(subtask['links'])} '{LINK_TYPE}' links)")
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- createmeta guard

def required_field_ids(meta):
    """Field ids Jira demands and will not fill in itself."""
    return {f["fieldId"] for f in meta.get("fields") or []
            if f.get("required") and not f.get("hasDefaultValue")}


def missing_required(meta, fields):
    return required_field_ids(meta) - set(fields)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_enabler.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: build the Enabler/Sub-task write plan

One Enabler per area with the area's default assignee and the marker
label, one Sub-task per cluster inheriting that assignee, and the bug
keys each Sub-task will link. Pure: computes payloads, writes nothing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 7: `bug_enabler.py` — preflight, apply, resume, links

The half that writes. Everything here is defensive: it must be safe to run twice, safe
to interrupt, and it must never leave an Enabler behind that nobody can find again.

**Files:**
- Modify: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_enabler.py` (append)
- Modify: `plugins/common/oc-bug-clusters/tests/test_bug_enabler.py` (append)

**Interfaces:**
- Consumes: `jira_client.JiraClient` (Task 2), the `plan` from Task 6.
- Produces, for Task 8:
  - `resolve_assignee(client, value) -> str` — passes an `accountId` through,
    resolves an email, raises `JiraError` when it matches no one
  - `existing_enabler(client, project, marker) -> str | None`
  - `preflight(client, project, plan) -> None` — raises `JiraError` naming any
    missing required field
  - `new_state() -> dict` — `{"enablers": {}, "subtasks": {}, "links": [],
    "warnings": []}`
  - `apply_plan(client, plan, state, force=False) -> dict` (the updated state)
  - CLI: `bug_enabler.py --model M --project P --report-path R [--assignee-portal V]
    [--assignee-core V] (--plan | --apply) --state S [--force]`

- [ ] **Step 1: Append the failing tests to `test_bug_enabler.py`**

```python
# ============================================================ applier behaviour

import jira_client as jc


class RecordingClient:
    """Stands in for JiraClient. `fail_on` maps a call signature to an exception."""

    def __init__(self, search_results=(), fail_on=None, meta=None):
        self.search_results = list(search_results)
        self.fail_on = dict(fail_on or {})
        self.meta = meta or {"fields": [{"fieldId": "summary", "required": True}]}
        self.posts = []
        self.gets = []
        self._n = 0

    def search(self, jql, fields, page_size=100):
        self.searches = getattr(self, "searches", [])
        self.searches.append(jql)
        return iter(self.search_results.pop(0) if self.search_results else [])

    def get(self, path):
        self.gets.append(path)
        if path in self.fail_on:
            raise self.fail_on[path]
        return self.meta

    def post(self, path, body):
        self.posts.append((path, body))
        summary = (body.get("fields") or {}).get("summary")
        if summary in self.fail_on:
            raise self.fail_on[summary]
        if path == "/rest/api/3/issue":
            self._n += 1
            return {"key": f"INTRD-{900 + self._n}"}
        return {}


def created_issues(client):
    return [b["fields"]["summary"] for p, b in client.posts if p == "/rest/api/3/issue"]


def link_count(client):
    return sum(1 for p, _ in client.posts if p == "/rest/api/3/issueLink")


# ------------------------------------------------------------ assignee resolution

def test_an_account_id_passes_straight_through():
    client = RecordingClient()
    assert be.resolve_assignee(client, "5ef5c13914f60e0ac1c9b049") == \
        "5ef5c13914f60e0ac1c9b049"
    assert client.gets == []


def test_an_email_is_resolved_to_an_account_id():
    client = RecordingClient()
    client.meta = [{"accountId": "acc-1", "emailAddress": "a@opencellsoft.com"}]
    assert be.resolve_assignee(client, "a@opencellsoft.com") == "acc-1"
    assert "user/search" in client.gets[0]


def test_an_unresolvable_email_raises_before_anything_is_written():
    client = RecordingClient()
    client.meta = []
    with pytest.raises(jc.JiraError, match="no Jira user"):
        be.resolve_assignee(client, "ghost@opencellsoft.com")


# ------------------------------------------------------------------ idempotency

def test_an_existing_marker_label_is_found():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    assert be.existing_enabler(client, "INTRD", "bug-clusters-portal-a-b") == "INTRD-500"
    assert 'labels = "bug-clusters-portal-a-b"' in client.searches[0]


def test_no_marker_means_no_existing_enabler():
    assert be.existing_enabler(RecordingClient(), "INTRD", "m") is None


def test_apply_skips_an_area_whose_marker_already_exists():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    state = be.apply_plan(client, plan_for(), be.new_state())

    assert created_issues(client) == []
    assert any("INTRD-500" in w for w in state["warnings"])


def test_force_creates_anyway():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    be.apply_plan(client, plan_for(), be.new_state(), force=True)
    assert len(created_issues(client)) == 2      # 1 enabler + 1 subtask


# ---------------------------------------------------------------------- preflight

def test_preflight_passes_when_every_required_field_is_present():
    client = RecordingClient()
    be.preflight(client, "INTRD", plan_for())     # must not raise


def test_preflight_stops_on_an_unexpected_required_field():
    client = RecordingClient(meta={"fields": [
        {"fieldId": "summary", "required": True},
        {"fieldId": "customfield_777", "required": True}]})
    with pytest.raises(jc.JiraError, match="customfield_777"):
        be.preflight(client, "INTRD", plan_for())


# ------------------------------------------------------------------ creation flow

def test_apply_creates_the_enabler_then_its_subtasks():
    client = RecordingClient()
    be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                  be.new_state())
    assert created_issues(client) == ["Bug clusters — Frontend — 2026-08-01 → 2026-09-01",
                                      "quoting — 6 bugs"]


def test_subtask_is_given_the_enabler_as_its_parent():
    client = RecordingClient()
    be.apply_plan(client, plan_for(), be.new_state())
    subtask_body = [b for p, b in client.posts if p == "/rest/api/3/issue"][1]
    assert subtask_body["fields"]["parent"] == {"key": "INTRD-901"}


def test_every_bug_of_a_cluster_is_linked_to_its_subtask():
    client = RecordingClient()
    state = be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                          be.new_state())
    assert link_count(client) == 6
    assert len(state["links"]) == 6


def test_a_link_uses_the_relates_type_and_points_at_the_subtask():
    client = RecordingClient()
    be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 5),))),
                  be.new_state())
    body = next(b for p, b in client.posts if p == "/rest/api/3/issueLink")
    assert body["type"] == {"name": "Relates"}
    assert body["outwardIssue"] == {"key": "INTRD-902"}


def test_state_records_what_was_created():
    client = RecordingClient()
    state = be.apply_plan(client, plan_for(), be.new_state())
    assert state["enablers"]["portal"] == "INTRD-901"
    assert state["subtasks"]["portal/quoting"] == "INTRD-902"


# --------------------------------------------------------------------- resumption

def test_a_rerun_with_existing_state_creates_nothing_twice():
    plan = plan_for()
    first = be.apply_plan(RecordingClient(), plan, be.new_state())

    client = RecordingClient()
    be.apply_plan(client, plan, first)

    assert created_issues(client) == [] and link_count(client) == 0


def test_a_rerun_completes_a_partially_created_area():
    plan = plan_for(model=model_for(sizes=(("quoting", 5),)))
    state = be.new_state()
    state["enablers"]["portal"] = "INTRD-500"

    client = RecordingClient()
    be.apply_plan(client, plan, state)

    assert created_issues(client) == ["quoting — 5 bugs"]
    assert link_count(client) == 5


# ----------------------------------------------------------- failure containment

def test_a_failed_link_is_warned_about_and_does_not_stop_the_run():
    client = RecordingClient()
    original = client.post

    def post(path, body):
        if path == "/rest/api/3/issueLink":
            client.posts.append((path, body))
            raise jc.JiraError("HTTP 404 on POST /rest/api/3/issueLink: no such issue")
        return original(path, body)

    client.post = post
    state = be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 5),))),
                          be.new_state())

    assert state["subtasks"]["portal/quoting"]
    assert len(state["warnings"]) == 5
    assert state["links"] == []


def test_a_rejected_assignee_retries_the_create_unassigned():
    summary = "Bug clusters — Frontend — 2026-08-01 → 2026-09-01"
    client = RecordingClient(fail_on={
        summary: jc.JiraError("HTTP 400 on POST /rest/api/3/issue: "
                              '{"errors":{"assignee":"not permitted"}}')})
    state = be.apply_plan(client, plan_for(), be.new_state())

    bodies = [b for p, b in client.posts if p == "/rest/api/3/issue"]
    assert "assignee" not in bodies[1]["fields"], "retry drops the assignee"
    assert state["enablers"]["portal"]
    assert any("assignee" in w for w in state["warnings"])


def test_a_failed_subtask_leaves_the_enabler_and_the_state_intact():
    client = RecordingClient(fail_on={
        "quoting — 6 bugs": jc.JiraError("HTTP 500 on POST /rest/api/3/issue: boom")})
    with pytest.raises(jc.JiraError):
        be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                      be.new_state())
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_enabler.py -q`
Expected: FAIL — `AttributeError: module 'bug_enabler' has no attribute 'resolve_assignee'`.

- [ ] **Step 3: Append the applier to `bug_enabler.py`**

Add `import argparse`, `import json`, `import os`, `import sys`,
`import urllib.parse`, and
`from jira_client import JiraClient, JiraError, MissingToken` at the top, then append:

```python
# --------------------------------------------------------------- assignee lookup

def resolve_assignee(client, value):
    """Accept an accountId or an email. An email that matches no user raises — a
    silent fallback here would assign the Enabler to nobody without saying so."""
    if "@" not in value:
        return value
    query = urllib.parse.quote(value)
    users = client.get(f"/rest/api/3/user/search?query={query}") or []
    exact = [u for u in users
             if (u.get("emailAddress") or "").lower() == value.lower()]
    for candidate in (exact, users):
        if len(candidate) == 1:
            return candidate[0]["accountId"]
    raise JiraError(f"'{value}' matches no Jira user (or several); "
                    f"pass an accountId instead")


# ------------------------------------------------------------------ idempotency

def existing_enabler(client, project, marker):
    jql = (f'project = {project} AND issuetype = Enabler '
           f'AND labels = "{marker}" ORDER BY created DESC')
    for issue in client.search(jql, ["summary"]):
        return issue["key"]
    return None


# --------------------------------------------------------------------- preflight

def _createmeta(client, project, type_id):
    return client.get(
        f"/rest/api/3/issue/createmeta/{project}/issuetypes/{type_id}")


def preflight(client, project, plan):
    """Fail before the first write if Jira wants a field the payload has no value for."""
    checks = []
    for area in plan["areas"]:
        checks.append((ENABLER_TYPE_ID, area["enabler"]["fields"]))
        for subtask in area["subtasks"]:
            # `parent` is injected at creation time; declare it so the guard
            # does not report it as missing.
            checks.append((SUBTASK_TYPE_ID, dict(subtask["fields"], parent=True)))
    for type_id, fields in checks:
        missing = missing_required(_createmeta(client, project, type_id), fields)
        if missing:
            raise JiraError(
                f"issue type {type_id} in {project} requires "
                f"{sorted(missing)}, which /oc-bug-clusters does not set. "
                f"Nothing was created.")


# ------------------------------------------------------------------------- apply

def new_state():
    return {"enablers": {}, "subtasks": {}, "links": [], "warnings": []}


def _create(client, fields, state):
    """Create an issue, retrying once without the assignee if Jira refuses it."""
    try:
        return client.post("/rest/api/3/issue", {"fields": fields})["key"]
    except JiraError as ex:
        if "assignee" not in str(ex).lower() or "assignee" not in fields:
            raise
        state["warnings"].append(
            f"Jira refused assignee {fields['assignee']} on "
            f"'{fields['summary']}' — created unassigned. ({ex})")
        retry = {k: v for k, v in fields.items() if k != "assignee"}
        return client.post("/rest/api/3/issue", {"fields": retry})["key"]


def apply_plan(client, plan, state, force=False):
    for area in plan["areas"]:
        token = area["area"]

        if token not in state["enablers"]:
            if not force:
                found = existing_enabler(client, plan["project"], area["marker"])
                if found:
                    state["warnings"].append(
                        f"{area['component']}: {found} already carries label "
                        f"{area['marker']} — skipped. Use --force to create another.")
                    continue
            state["enablers"][token] = _create(client, area["enabler"]["fields"], state)

        enabler_key = state["enablers"][token]

        for subtask in area["subtasks"]:
            slot = f"{token}/{subtask['subject']}"
            if slot not in state["subtasks"]:
                fields = dict(subtask["fields"], parent={"key": enabler_key})
                state["subtasks"][slot] = _create(client, fields, state)
            subtask_key = state["subtasks"][slot]

            for bug_key in subtask["links"]:
                edge = f"{bug_key}->{subtask_key}"
                if edge in state["links"]:
                    continue
                try:
                    client.post("/rest/api/3/issueLink", {
                        "type": {"name": LINK_TYPE},
                        "inwardIssue": {"key": bug_key},
                        "outwardIssue": {"key": subtask_key}})
                    state["links"].append(edge)
                except JiraError as ex:
                    # Best effort: a missing link is cosmetic, a half-created
                    # Enabler is not. Collect and carry on.
                    state["warnings"].append(f"link {edge} failed: {ex}")
    return state


# --------------------------------------------------------------------------- CLI

def _load_state(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    return new_state()


def _save_state(path, state):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create Enablers from a cluster model.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--report-path", default="")
    parser.add_argument("--assignee-portal", default=DEFAULT_ASSIGNEE["portal"])
    parser.add_argument("--assignee-core", default=DEFAULT_ASSIGNEE["core"])
    parser.add_argument("--state", required=True)
    parser.add_argument("--force", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    with open(args.model, encoding="utf-8") as handle:
        model = json.load(handle)

    try:
        client = JiraClient()
        assignees = {"portal": resolve_assignee(client, args.assignee_portal),
                     "core": resolve_assignee(client, args.assignee_core)}
    except (MissingToken, JiraError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    plan = build_plan(model, args.project, assignees, args.report_path)

    if args.plan:
        sys.stdout.write(render_plan(plan))
        _save_state(args.state + ".plan.json", plan)
        return 0

    if not plan["areas"]:
        sys.stdout.write(render_plan(plan))
        return 0

    state = _load_state(args.state)
    try:
        preflight(client, args.project, plan)
        state = apply_plan(client, plan, state, force=args.force)
    finally:
        _save_state(args.state, state)

    for area, key in state["enablers"].items():
        sys.stdout.write(f"{area}: {model['areas'][area]['component']} Enabler {key}\n")
    for slot, key in state["subtasks"].items():
        sys.stdout.write(f"  {slot}: {key}\n")
    sys.stdout.write(f"{len(state['links'])} bug links created\n")
    for warning in state["warnings"]:
        sys.stderr.write(f"WARNING: {warning}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_bug_enabler.py -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 6: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: apply the Enabler plan to Jira, safely

createmeta preflight before the first write, marker-label idempotency,
created.json resume so an interrupted run continues instead of
duplicating, best-effort issue links, and an assignee Jira refuses falls
back to creating unassigned with a warning.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 8: `SKILL.md` — orchestration and the classification step

The document Claude executes. It owns the two things no script can: the semantic
classification, and the confirmation gate between `--plan` and `--apply`.

**Files:**
- Create: `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/SKILL.md`
- Modify: `plugins/common/oc-bug-clusters/tests/test_packaging.py` (append)

**Interfaces:**
- Consumes: every script CLI from Tasks 3, 5 and 7.
- Produces: the user-facing command. Nothing downstream consumes it.

**Run directory.** `${TMPDIR:-/tmp}/oc-bug-clusters/<project>_<repo>_<since>_<until>/`
— keyed by the window so a re-run resumes, outside any repo so no `.gitignore` entry
is needed anywhere. If it is wiped, the marker label still prevents duplicate
Enablers; the state file is an optimisation, the label is the guarantee.

- [ ] **Step 1: Append the failing doc-parity tests to `test_packaging.py`**

```python
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
    hint = re.search(r"argument-hint: \"(.+)\"", text).group(1)
    advertised = set(re.findall(r"--[a-z-]+", hint))
    documented = set(re.findall(r"^\| `(--[a-z-]+)`", text, re.M))
    assert advertised - documented == set(), "advertised but undocumented"
    assert documented - advertised == set(), "documented but not advertised"


def test_skill_pins_both_default_assignee_account_ids():
    text = skill_text()
    assert "5ef5c13914f60e0ac1c9b049" in text     # Mohamed Hamidi, Frontend
    assert "63369fa788ed2ebef97cddfb" in text     # Adil El Jaouhari, Backend


def test_every_script_the_skill_invokes_exists():
    for name in set(re.findall(r"scripts/([a-z_]+\.py)", skill_text())):
        assert (SCRIPTS / name).is_file(), name


def test_skill_only_passes_flags_the_scripts_accept():
    """Catches the commonest rot: a renamed CLI flag the skill still calls."""
    for name in sorted(set(re.findall(r"scripts/([a-z_]+\.py)", skill_text()))):
        helptext = subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--help"],
            capture_output=True, text=True, check=True).stdout
        # Scan each whole fenced block that invokes the script: the commands are
        # backslash-continued across lines, so a line-bounded regex would miss most
        # of the flags — the exact drift this test exists to catch.
        for block in re.findall(r"```bash\n(.*?)```", skill_text(), re.S):
            if f"scripts/{name}" not in block:
                continue
            for flag in re.findall(r"--[a-z-]+", block):
                assert flag in helptext, f"{name} does not accept {flag}"


def test_skill_forbids_the_atlassian_mcp_for_the_fetch():
    assert "Do not use the Atlassian MCP" in skill_text()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests/test_packaging.py -q`
Expected: FAIL — `FileNotFoundError` for `SKILL.md`.

- [ ] **Step 3: Write `SKILL.md`**

Create `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/SKILL.md`:

````markdown
---
name: oc-bug-clusters
description: Analyse the bugs created over a period, classify each onto a seeded subject taxonomy, and group any subject carrying at least 5 bugs into a cluster. Area (portal/core) comes from the Jira component with a [front]/[back] summary-tag fallback and is fully deterministic; the subject is the only LLM judgement. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. With --create-enabler it creates one Enabler per area (Frontend assigned to Mohamed Hamidi, Backend to Adil El Jaouhari) holding one Sub-task per cluster with the cluster's bugs linked - confirmed before writing, idempotent via a marker label, and resumable. Fetches Jira via direct Cloud REST with a mandatory JIRA_API_TOKEN - no Atlassian MCP.
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--create-enabler] [--min-cluster N] [--project KEY] [--assignee-portal ID] [--assignee-core ID] [--out PATH] [--csv PATH] [--force]"
---

## Purpose

Turn a period of Jira bugs into a small number of **subject clusters**, and — on
request — into scheduled work: one **Enabler per area**, each holding one **Sub-task
per cluster**, with the cluster's bugs linked to it.

A cluster is **at least `--min-cluster` (default 5) bugs on the same subject**.

Two properties are worth knowing before changing anything here:

- **Area is deterministic, subject is not.** The portal/core split is computed in
  Python from the Jira component (falling back to a leading `[front]`/`[back]` tag), so
  it never moves between two runs. Only the subject is an LLM judgement.
- **The marker label is what makes re-runs safe.** Every Enabler carries
  `bug-clusters-<area>-<since>-<until>`, and that label is searched before any write.

This command is read-only unless `--create-enabler` is passed. It needs no git
checkout and no Bitbucket token, and runs from any directory.

## Access

Requires **`JIRA_API_TOKEN`** (+ optional `JIRA_EMAIL`) — an Atlassian API token from
*id.atlassian.com → Security → API tokens*, read from the environment and **never
passed on the command line**. If it is unset, tell the user how to create one and stop.

**Do not use the Atlassian MCP for the fetch.** `searchJiraIssuesUsingJql` force-includes
each issue's full description and caps at ~5 issues per call with no cursor — a 50-issue
probe already overflows the tool-result limit. All Jira access here is direct Cloud REST.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-bug-clusters` analyses the **last 30
days** of **portal** bugs in **INTRD** and only reports.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 30 days before `--until` | Start of the window, inclusive, on `created` |
| `--until` | tomorrow | End of the window, **exclusive** — so today's bugs count, and `--since 2026-08-01 --until 2026-09-01` is exactly August |
| `--repo` | `portal` | `portal` → component `Frontend`; `core` → `Backend`; `both` → each area clustered separately, one Enabler each |
| `--create-enabler` | off | Create the Jira Enabler(s). Off means report only |
| `--min-cluster` | `5` | Bugs on one subject before it counts as a cluster |
| `--project` | `INTRD` | Portal *and* core both live in INTRD. `MACRD` is MACO — a different codebase, out of scope here |
| `--assignee-portal` | `5ef5c13914f60e0ac1c9b049` | Frontend Enabler assignee (Mohamed Hamidi). Accepts an accountId or an email |
| `--assignee-core` | `63369fa788ed2ebef97cddfb` | Backend Enabler assignee (Adil El Jaouhari). Same forms |
| `--out` | `./docs/bug-clusters-<TODAY>.html` | HTML report |
| `--csv` | `./docs/bug-clusters-<TODAY>.csv` | One row per bug |
| `--force` | off | Create a second Enabler for a window that already has one |

`<TODAY>` is `date -u +%Y-%m-%d`. Compute missing dates with
`date -u -d '30 days ago' +%Y-%m-%d`.

**Echo the resolved window before doing any work**, e.g.
`Analysing INTRD bugs, portal, 2026-08-16 → 2026-09-16`.

## Task 1 — Fetch and area-tag

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-bug-clusters"
RUN="${TMPDIR:-/tmp}/oc-bug-clusters/[PROJECT]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/bug_fetch.py" --since [SINCE] --until [UNTIL] \
  --project [PROJECT] --repo [REPO] \
  --out-bugs "$RUN/bugs.json" --out-classify "$RUN/classify_input.jsonl"
```

The run directory is keyed by the window so a later `--create-enabler` run resumes
rather than duplicating.

**Never read `bugs.json`.** It holds every bug's full record and exists only for the
next script. If it reports 0 bugs, say
`No bugs created in [SINCE] → [UNTIL] for [PROJECT]` and stop.

## Task 2 — Classify each bug onto a subject

**This is the only step you perform yourself.**

1. Read `$S/references/subjects.md`. Its `## <name>` headings are the vocabulary.
2. Read `$RUN/classify_input.jsonl` — one bug per line: `key`, `summary`, `excerpt`,
   `component`, `labels`. Process it in batches of **at most 60 lines**.
3. Write `$RUN/assignments.json`: a flat object `{"INTRD-47162": "rating", …}` covering
   **every key in the file**. A missing key stops the next step with an error.

Rules:

- **Exactly one subject per bug.** No multi-label, no ties, no empty values.
- **Prefer a subject that already exists** in `subjects.md`.
- You may coin a **new** subject only when **at least `--min-cluster` bugs in the same
  area** fit none of the seeded ones — the same threshold that makes a cluster, so a
  coined subject can never be too small to be one. Report any new subject to the user
  at the end so `subjects.md` can be updated.
- Names are **lower-kebab-case**.
- Classify by what the bug is **about** — the product area it lives in — **never by its
  symptom**. `quoting`, not `blank-screen`. A crash in the quote screen is `quoting`;
  a crash caused by a slow query that times out everywhere is `performance`.
- **Do not trust the reporter's tag.** `[NEW UI]` and `[Quote New UI]` are the same
  subject; `[15.X]` is a version, not a subject.

## Task 3 — Cluster and report

```bash
python3 "$S/scripts/bug_cluster.py" --bugs "$RUN/bugs.json" \
  --assignments "$RUN/assignments.json" --subjects "$S/references/subjects.md" \
  --min-cluster [MIN] --out [OUT] --csv [CSV] --model "$RUN/model.json"
```

It prints the Markdown report to stdout — relay it. Then tell the user where the HTML
and CSV landed, and name any **new subject** you coined.

Stop here unless `--create-enabler` was passed.

## Task 4 — Create the Enablers (only with `--create-enabler`)

**Step 1 — show the plan. Write nothing yet.**

```bash
python3 "$S/scripts/bug_enabler.py" --model "$RUN/model.json" --project [PROJECT] \
  --report-path [OUT] --assignee-portal [AP] --assignee-core [AC] \
  --state "$RUN/created.json" --plan
```

If it prints `No cluster reached the threshold`, say so and stop — **never create an
empty Enabler**.

**Step 2 — ask.** Show the printed plan and ask the user to confirm, plainly: how many
Enablers, how many Sub-tasks, how many bug links, and into which project. **Wait for an
explicit yes.** Do not proceed on silence or on an ambiguous reply.

**Step 3 — apply, only after that yes.**

```bash
python3 "$S/scripts/bug_enabler.py" --model "$RUN/model.json" --project [PROJECT] \
  --report-path [OUT] --assignee-portal [AP] --assignee-core [AC] \
  --state "$RUN/created.json" --apply
```

Report every created key. Relay every `WARNING:` line verbatim — a failed bug link is
reported, not fatal, and the user needs to know which ones to add by hand.

If it says an Enabler already carries the marker label, tell the user the existing key
and that `--force` would create a second one. **Do not pass `--force` on your own
initiative** — only when the user asks for it.

## Failure behaviour

| Condition | What to do |
|---|---|
| `JIRA_API_TOKEN` unset | Print the setup instructions from the script and stop. Never fall back to the MCP |
| Zero bugs in the window | Report it and stop |
| Zero clusters | Show the report's near-clusters, create nothing |
| `no subject assigned for: …` | You missed keys in Task 2. Classify exactly those and re-run Task 3 |
| `requires [...], which /oc-bug-clusters does not set` | A Jira screen changed. Report it; nothing was written |
| An `--assignee-*` email matches no user | Stop and ask for an accountId; nothing was written |
| `WARNING: link … failed` | Relay it; the Enabler and Sub-tasks are fine |
````

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-clusters
git commit -m "INTRD-47165: the /oc-bug-clusters skill document

Orchestrates fetch, classification, report and the gated Enabler write.
Carries the classification rules (one subject per bug, coin a new one
only at the cluster threshold, classify by product area not symptom) and
the confirmation gate between --plan and --apply.

Doc-parity tests check the advertised flags match the documented table
and that every flag the skill passes is one its scripts accept.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---
### Task 9: Repository documentation and live verification

The plugin is only finished once `CLAUDE.md` records the two non-obvious constraints
and the pipeline has been run against real Jira.

**Files:**
- Modify: `CLAUDE.md` (two edits)

**Interfaces:**
- Consumes: everything. Produces: nothing downstream.

- [ ] **Step 1: Add the command to the skill list in `CLAUDE.md`**

In **Plugin Types → 1. Skills & commands**, insert `/oc-bug-clusters` into the list of
slash commands, after `/oc-review-pr`:

```
`/oc-cache-jira`, `/oc-commit`, `/oc-pull-request`, `/oc-review-pr`, `/oc-bug-clusters`, `/oc-fe-fix-bug`, …
```

- [ ] **Step 2: Add a section to `CLAUDE.md`**

Insert immediately before `## MCP Servers Requiring Environment Variables`:

```markdown
## Bug clustering (`/oc-bug-clusters`)

`plugins/common/oc-bug-clusters` groups a period's bugs by subject and can turn each
cluster into Jira work. Unlike the other common plugins it ships **real Python files**
under `skills/oc-bug-clusters/scripts/` (invoked via `${CLAUDE_PLUGIN_ROOT}`, the same
shape `oc-fn-tools` uses for `pptx/`) rather than embedding them in the Markdown, and it
carries a pytest suite in `plugins/common/oc-bug-clusters/tests/`:

```bash
python3 -m pytest plugins/common/oc-bug-clusters/tests -q
```

Four constraints are not obvious from the code:

- **Area is deterministic, subject is not.** `portal`/`core` is resolved in Python from
  the Jira component, with a **leading** `[front]`/`[back]` summary tag as fallback. It
  decides which Enabler a bug lands under, so it must never become an LLM judgement —
  the same window would produce a different split on every run.
- **The marker label is the duplicate guard.** Every Enabler carries
  `bug-clusters-<area-token>-<since>-<until>` and it is searched before any write. The
  `created.json` state file only makes a resume cheaper; the *label* is what makes a
  re-run safe, so never drop it from the payload.
- **The area token and the Jira component are two vocabularies.** `portal`/`core` is
  what `--repo` takes and what keys the label; `Frontend`/`Backend` is what goes on the
  issue. Mixing them silently breaks idempotency, because the label stops matching.
- **`Sub-bug` must be quoted in JQL.** The hyphen breaks an unquoted term, and the
  failure mode is a silent undercount rather than an error.

The two default Enabler assignees are pinned by `accountId` at the top of `SKILL.md` —
Frontend `5ef5c13914f60e0ac1c9b049`, Backend `63369fa788ed2ebef97cddfb`. A handover is a
one-line edit there.
```

- [ ] **Step 3: Run the whole suite one more time**

Run: `python3 -m pytest plugins/common/oc-bug-clusters/tests -q`
Expected: PASS — no failures, no errors.

- [ ] **Step 4: Verify the plugin JSON is well-formed**

```bash
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null
python3 -m json.tool plugins/common/oc-bug-clusters/.claude-plugin/plugin.json > /dev/null
echo OK
```
Expected: `OK`

- [ ] **Step 5: Live read-only run**

Requires `JIRA_API_TOKEN` in the environment. Run the command for real:

```
/oc-bug-clusters --since 2026-08-15 --until 2026-09-15 --repo both
```

Reconcile against the figures measured while writing the spec:

- `project in (INTRD, MACRD)` over that window held **149** Bug/Sub-bug issues; this run
  is INTRD only, so **`fetched` must be at or below 149 and well above zero**.
- In a 50-bug sample the split was **46% Frontend / 40% Backend / 14% no component**.
  `portal`, `core` and `unclassified` should land near those proportions — a wildly
  different split means `area_of` regressed.
- Confirm the HTML opens with two tabs, the CSV has one row per kept bug, and no
  Markdown section contradicts the counters.

Report the actual numbers. **If they do not reconcile, stop and investigate — do not
proceed to Step 6.**

- [ ] **Step 6: Gated write run**

Ask the user before this step; it creates real Jira issues.

```
/oc-bug-clusters --since 2026-08-15 --until 2026-09-15 --repo both --create-enabler
```

Review the printed plan object-by-object with the user, approve, then confirm:

- one Enabler per area, correct component, correct assignee;
- one Sub-task per cluster, each inheriting its Enabler's assignee;
- the bugs appear as `Relates` links on the Sub-task.

Then **run the exact same command again**. It must report the existing Enabler keys and
create nothing — that is the marker label working.

- [ ] **Step 7: Commit and open the PR**

```bash
git add CLAUDE.md
git commit -m "INTRD-47165: document the oc-bug-clusters plugin

Records the four non-obvious constraints: area is deterministic while
subject is not, the marker label rather than created.json is the
duplicate guard, the area token and the Jira component are separate
vocabularies, and Sub-bug must be quoted in JQL.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

Then open the pull request with `/oc-pull-request INTRD-47165`.

---

## Verification Summary

| What | How |
|---|---|
| Naming convention, marketplace wiring | `test_packaging.py` |
| Doc/code flag parity | `test_packaging.py` runs each script's `--help` |
| Transport: auth, retry, pagination | `test_jira_client.py` |
| Area assignment, ADF, window, JQL | `test_bug_fetch.py` |
| Threshold, ordering, area isolation, missing assignment | `test_bug_cluster.py` |
| Markdown / CSV / HTML, escaping, tabs | `test_bug_render.py` |
| Payloads, assignee inheritance, idempotency, resume, failure containment | `test_bug_enabler.py` |
| Real data reconciles | Task 9 Step 5, against the measured 149 / 46-40-14 split |
| Writes are idempotent for real | Task 9 Step 6, second run creates nothing |

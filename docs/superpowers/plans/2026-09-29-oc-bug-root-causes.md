# `/oc-bug-root-causes` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only plugin that reclassifies a period's Jira bugs whose `Root cause` is "Development issue" onto a granular developer-mistake taxonomy, using the Jira text and the diff of the PR that fixed each bug, and reports the ranking as Markdown + HTML + CSV.

**Architecture:** Four stages, like `oc-bug-clusters`. `rc_fetch.py` (Jira REST, deterministic) → `rc_pr.py` (Bitbucket REST, deterministic, writes batch files) → LLM classification fanned out to one sub-agent per batch (driven by `SKILL.md`) → `rc_report.py` (no network: merge, validate, aggregate, render). Transport and area logic are **byte-identical copies** of files in sibling plugins, because `${CLAUDE_PLUGIN_ROOT}` cannot reach another plugin in an install.

**Tech Stack:** Python 3 standard library only (`urllib`, `json`, `csv`, `argparse`, `re`); pytest for tests; Jira Cloud REST v3; Bitbucket Cloud REST 2.0.

**Spec:** `docs/superpowers/specs/2026-09-29-oc-bug-root-causes-design.md`

## Global Constraints

- Plugin name `oc-bug-root-causes`, directory `plugins/common/oc-bug-root-causes`, skill `skills/oc-bug-root-causes/`, version `1.0.0`.
- Python standard library only in `scripts/`. No third-party imports.
- **Read-only.** The only non-GET request is Jira's search `POST /rest/api/3/search/jql`. No Jira writes, no Bitbucket writes.
- Tokens come from the environment only (`JIRA_API_TOKEN`, `JIRA_EMAIL`, `BITBUCKET_ACCESS_TOKEN`, `BITBUCKET_EMAIL`), never argv.
- Jira via direct REST — never the Atlassian MCP.
- Bitbucket auth scheme keyed off the token prefix (`ATCTT…` → Bearer, otherwise Basic `email:token`); a 401 message names **both** schemes.
- `scripts/jira_client.py` and `scripts/bug_fetch.py` are byte-identical to `plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/`; `scripts/bitbucket_client.py` is byte-identical to `plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/`.
- JQL clause: `"Root cause" = "Development issue"` (field `customfield_10111`).
- Defaults: `--since` = 30 days before `--until`; `--until` = tomorrow, exclusive; `--repo both`; `--project INTRD`.
- Limits: description excerpt 600 chars; last 3 comments, 400 chars each; diff cap 4096 bytes; file list cap 40; batch size 30; cause line 120 chars; new category needs ≥ 5 bugs.
- Reports: `./docs/bug-root-causes-<TODAY>.html` and `.csv`, `<TODAY>` = `date -u +%Y-%m-%d`.
- Taxonomy: exactly the 15 agreed categories, lower-kebab-case, `insufficient-evidence` last.
- Run tests with: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q` from the repo root.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A ticket key that is a prefix of another** (`INTRD-4516` vs `INTRD-45162`): Bitbucket's `~` is a substring match, so the other ticket's PR must not be taken as evidence. Pinned in Task 4 (`test_key_must_match_whole_not_as_a_prefix`).
2. **The diff's 302 to a signed URL on another host:** it must be followed, and the `Authorization` header must not travel to the new host. Pinned in Task 5 (`test_diff_redirect_to_another_host_is_followed_without_credentials`).
3. **Bitbucket rate limiting (429/503) mid-run** on a 280-bug window: retried with backoff, not turned into 280 Jira-only fallbacks. Pinned in Task 5 (`test_raw_fetch_retries_rate_limits`).
4. **A PR whose diff has no `diff --git` header** (empty, binary-only): it yields an empty diff and file list without crashing. Pinned in Task 4 (`test_a_diff_without_file_headers_yields_nothing`).
5. **A bug with no component whose fix lives in either repository:** both repositories are searched and the selection rule applies across them. Pinned in Task 5 (`test_an_arealess_bug_is_looked_up_in_both_repositories`).

---

## File Structure

```
plugins/common/oc-bug-root-causes/
  .claude-plugin/plugin.json                         Task 1
  skills/oc-bug-root-causes/
    SKILL.md                                         Task 8
    references/dev-root-causes.md                    Task 2
    scripts/jira_client.py        (copy)             Task 1
    scripts/bug_fetch.py          (copy)             Task 1
    scripts/bitbucket_client.py   (copy)             Task 1
    scripts/rc_fetch.py                              Task 3
    scripts/rc_pr.py                                 Tasks 4-5
    scripts/rc_report.py                             Tasks 6-7
  tests/
    conftest.py                                      Task 1
    test_packaging.py                                Tasks 1, 8
    test_taxonomy.py                                 Task 2
    test_rc_fetch.py                                 Task 3
    test_rc_pr.py                                    Tasks 4-5
    test_rc_report.py                                Tasks 6-7
.claude-plugin/marketplace.json   (modify)           Task 1
CLAUDE.md                         (modify)           Task 8
```

---

### Task 1: Scaffold, copied transport, packaging guards

**Files:**
- Create: `plugins/common/oc-bug-root-causes/.claude-plugin/plugin.json`
- Create (copy): `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/{jira_client.py,bug_fetch.py,bitbucket_client.py}`
- Create: `plugins/common/oc-bug-root-causes/tests/conftest.py`
- Create: `plugins/common/oc-bug-root-causes/tests/test_packaging.py`
- Modify: `.claude-plugin/marketplace.json` (add an entry after `oc-bug-clusters`)

**Interfaces:**
- Produces (conftest): `FakeResponse(payload)` — `payload` may be `bytes` (returned raw), `None` (empty body) or JSON-serialisable; `http_error(code, body=b"nope", headers=None, url="https://example/x") -> urllib.error.HTTPError`; `FakeOpener(results)` — callable `(request, timeout=None)`, records `.requests`, raises queued exceptions, has `.urls()` and `.bodies()`; fixtures `jira_env`, `bb_env`; constant `SAMPLE_DIFF`.
- Produces (copied modules): `jira_client.JiraClient(opener=, env=, sleep=)` with `.get(path)`, `.search(jql, fields)`, `JiraError`, `MissingToken`, `BASE`; `bug_fetch.area_of(fields)`, `excerpt(text, limit)`, `flatten_adf(node)`, `resolve_window(since, until)`, `areas_in_scope(repo)`, `AREA_COMPONENT`; `bitbucket_client.BitbucketClient(opener=, env=, sleep=)` with `.paginate(path, params)`, `auth_header(env)`, `BitbucketError`, `MissingToken`, `BASE`.

- [ ] **Step 1: Write the failing packaging test**

`plugins/common/oc-bug-root-causes/tests/test_packaging.py`:

```python
"""The plugin must be discoverable, follow the naming convention, and keep its copied
transport identical to the originals it was copied from.

Copies, not imports: ${CLAUDE_PLUGIN_ROOT} resolves to this plugin's own versioned
install directory, so a path into oc-bug-clusters or oc-pr-rejection-rate does not exist
once installed. The identity test is what stops the copies from drifting silently.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-bug-root-causes"
NAME = "oc-bug-root-causes"
SCRIPTS = PLUGIN_DIR / "skills" / NAME / "scripts"


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


@pytest.mark.parametrize("name,origin", [
    ("jira_client.py", "oc-bug-clusters/skills/oc-bug-clusters/scripts"),
    ("bug_fetch.py", "oc-bug-clusters/skills/oc-bug-clusters/scripts"),
    ("bitbucket_client.py", "oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts"),
])
def test_copied_transport_is_byte_identical(name, origin):
    original = REPO / "plugins" / "common" / origin / name
    assert (SCRIPTS / name).read_bytes() == original.read_bytes(), (
        f"{name} drifted from {origin}/{name}: change the original, then re-copy it here")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: FAIL — `plugin.json` not found, marketplace entry missing, copied files missing.

- [ ] **Step 3: Create plugin.json, copy the transport, register the plugin**

`plugins/common/oc-bug-root-causes/.claude-plugin/plugin.json`:

```json
{
  "name": "oc-bug-root-causes",
  "description": "Reclassify a period's Jira bugs whose Root cause is \"Development issue\" onto a granular developer-mistake taxonomy (null-handling, dto-payload-mapping, update-overwrites-state, ...), judged from the bug's Jira text and the diff of the PR that fixed it. Regression is recorded as a separate flag. Ranks the categories per area with regression rate and evidence quality, prints Markdown and writes a date-stamped HTML + CSV to ./docs/. Read-only. Jira via direct Cloud REST (JIRA_API_TOKEN), Bitbucket via REST (BITBUCKET_ACCESS_TOKEN, optional - without it the run is Jira-only).",
  "version": "1.0.0"
}
```

```bash
D=plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts
mkdir -p "$D"
cp plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/jira_client.py "$D/"
cp plugins/common/oc-bug-clusters/skills/oc-bug-clusters/scripts/bug_fetch.py "$D/"
cp plugins/common/oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts/bitbucket_client.py "$D/"
```

In `.claude-plugin/marketplace.json`, insert directly after the `oc-bug-clusters` object:

```json
    {
      "name": "oc-bug-root-causes",
      "source": "./plugins/common/oc-bug-root-causes",
      "description": "Reclassify a period's \"Development issue\" bugs onto a granular developer-mistake taxonomy from each bug's Jira text and fixing-PR diff; ranks categories per area with regression rate. Read-only; Markdown + HTML + CSV to ./docs/"
    },
```

`plugins/common/oc-bug-root-causes/tests/conftest.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes .claude-plugin/marketplace.json
git commit -m "oc-bug-root-causes: scaffold plugin with copied Jira/Bitbucket transport

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The developer-mistake taxonomy

**Files:**
- Create: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/references/dev-root-causes.md`
- Test: `plugins/common/oc-bug-root-causes/tests/test_taxonomy.py`

**Interfaces:**
- Produces: a Markdown file whose `## <name>` headings are the vocabulary; the **first paragraph** under each heading is the definition (read by `rc_report.load_taxonomy` in Task 6); an `Examples:` line follows after a blank line.

- [ ] **Step 1: Write the failing test**

`plugins/common/oc-bug-root-causes/tests/test_taxonomy.py`:

```python
"""The taxonomy is the contract between the classifier and the report. Renaming a
category breaks period-over-period comparison, so the exact list is pinned here: a
change to it must be a deliberate edit of this test too."""
import re
from pathlib import Path

TAXONOMY = (Path(__file__).resolve().parents[1] / "skills" / "oc-bug-root-causes"
            / "references" / "dev-root-causes.md")

AGREED = [
    "incomplete-change-propagation", "null-handling", "edge-case-boundary",
    "dto-payload-mapping", "update-overwrites-state", "persistence-transaction",
    "query-construction", "api-contract", "frontend-state-effects", "missing-wiring",
    "business-rule-logic", "numeric-date-precision", "concurrency-lifecycle",
    "ui-cosmetic", "insufficient-evidence",
]


def categories():
    return re.findall(r"^## ([a-z0-9-]+)\s*$", TAXONOMY.read_text(), re.M)


def test_taxonomy_is_exactly_the_agreed_vocabulary():
    assert categories() == AGREED


def test_every_category_has_a_definition_and_examples():
    blocks = re.split(r"^## ", TAXONOMY.read_text(), flags=re.M)[1:]
    for block in blocks:
        name, _, body = block.partition("\n")
        paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        assert paragraphs and not paragraphs[0].startswith("Examples:"), name
        assert any(p.startswith("Examples: INTRD-") for p in paragraphs), name


def test_regression_is_not_a_category():
    assert not any("regression" in c for c in categories())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_taxonomy.py -q`
Expected: FAIL — `FileNotFoundError` on `dev-root-causes.md`.

- [ ] **Step 3: Write the taxonomy**

`plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/references/dev-root-causes.md`:

```markdown
# Developer root-cause taxonomy

The vocabulary `/oc-bug-root-causes` classifies **"Development issue"** bugs onto. One
category per bug, chosen by **the mistake the fix corrects**: read the PR diff first and the
Jira prose second, and ask "what did the developer get wrong?", not "where did the user see
it?". The same list serves Frontend and Backend, so the two areas can be compared.

Whether a bug is a **regression** is recorded separately (`regression: true|false`) and is
never a category: a regression can be any of the mistakes below.

The first paragraph under each heading is the definition the report prints. Editing this
file changes future runs. Adding a category is safe; **renaming one breaks
period-over-period comparison**, so add a line to a definition rather than rename.

## incomplete-change-propagation
A change, fix or rename was applied to some code paths but not all of them: the create path fixed but not the update path, a setting applied to one entity type only, an enum renamed without migrating stored data, a previous fix that missed a sibling case.

Examples: INTRD-45634, INTRD-45671, INTRD-47270, INTRD-45624

## null-handling
A missing value was dereferenced without a guard: NullPointerException or "Cannot read properties of undefined" from optional configuration, an absent settings row, or an unguarded lookup.

Examples: INTRD-46331, INTRD-45167, INTRD-45541, INTRD-44718

## edge-case-boundary
A legitimate but unusual value was mishandled: zero, empty string, false, an empty list, a limit or boundary, a value with special characters, a case-sensitivity difference.

Examples: INTRD-45965, INTRD-44579, INTRD-46198, INTRD-45420

## dto-payload-mapping
Data lost or malformed crossing a boundary between UI, DTO and entity: a field dropped by a mapper or copy constructor, an object sent where a code was expected, an unknown or undeserialisable field, a field never reaching the backend.

Examples: INTRD-46196, INTRD-46854, INTRD-44595, INTRD-45543, INTRD-45461

## update-overwrites-state
An update replaced data it should have merged, or created a record it should have updated: omitted payload fields erase stored values, a partial object replaces the full one, a new line is added instead of editing the existing one, a user value is overwritten by the system.

Examples: INTRD-47176, INTRD-45282, INTRD-45590, INTRD-45620, INTRD-43559

## persistence-transaction
The persistence layer produced the wrong database state: duplicate or orphan rows, side effects surviving a rollback or applied twice, transient-entity and optimistic-lock errors, corrupted relationships or version chains, ID generator collisions.

Examples: INTRD-46292, INTRD-45439, INTRD-45168, INTRD-45292, INTRD-46781

## query-construction
A query was built wrong: invalid SQL/JPQL (GROUP BY, schema or table qualification), or server-side filtering, sorting, paging or export that covers the wrong set or the wrong field.

Examples: INTRD-43566, INTRD-44082, INTRD-47322, INTRD-46981, INTRD-46515, INTRD-45778

## api-contract
The REST surface disagrees with its contract: the wrong HTTP status for a condition, v1 and v2 answering the same request differently, a valid payload rejected, a response missing a documented part.

Examples: INTRD-46336, INTRD-44766, INTRD-46316, INTRD-45795

## frontend-state-effects
Client-side state or effect lifecycle is wrong: re-render or fetch loops, the same request fired repeatedly, stale data until refresh, unsaved changes discarded, UI preferences not persisted.

Examples: INTRD-47328, INTRD-45777, INTRD-46779, INTRD-43961, INTRD-45532

## missing-wiring
Something that had to be registered was forgotten: an app-roles or permission entry, an i18n key, a route, a request handler, a menu or configuration entry — the code exists but is not connected.

Examples: INTRD-45784, INTRD-46822, INTRD-45370, INTRD-45696, INTRD-45456

## business-rule-logic
A business rule was implemented wrongly: the wrong condition, the wrong data source, the wrong precedence or fallback, a rule applied when it should not be.

Examples: INTRD-47162, INTRD-45169, INTRD-44084, INTRD-43576

## numeric-date-precision
Numbers or dates computed or represented wrongly: rounding, floating-point totals, the number of decimals, timezone offsets, an off-by-one day.

Examples: INTRD-46710, INTRD-46784, INTRD-46778, INTRD-43377, INTRD-44021

## concurrency-lifecycle
Behaviour tied to time, nodes or process lifecycle: multi-node cluster races, deadlocks, startup and shutdown handling, timers and jobs relaunched or lost, caches that grow without bound.

Examples: INTRD-45412, INTRD-45289, INTRD-47287, INTRD-45028, INTRD-44507

## ui-cosmetic
Presentation only, with no data or behaviour wrong: wording, translation, casing, colours, layout, a label or icon.

Examples: INTRD-44765, INTRD-46824, INTRD-44707, INTRD-45417, INTRD-44058

## insufficient-evidence
Neither the Jira text nor the PR diff shows what the mistake was. Use it honestly: a bug that has a plausible best guess gets that guess with `low` confidence instead.

Examples: INTRD-45335, INTRD-47271
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/references plugins/common/oc-bug-root-causes/tests/test_taxonomy.py
git commit -m "oc-bug-root-causes: seed the developer-mistake taxonomy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Fetch "Development issue" bugs — `rc_fetch.py`

**Files:**
- Create: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_fetch.py`
- Test: `plugins/common/oc-bug-root-causes/tests/test_rc_fetch.py`

**Interfaces:**
- Consumes: `bug_fetch.{area_of, areas_in_scope, excerpt, flatten_adf, resolve_window}`, `jira_client.{BASE, JiraClient, JiraError, MissingToken}` (Task 1).
- Produces: `build_jql(projects: list[str], since: str, until: str) -> str`; `fetch_comments(client, key: str) -> list[str]`; `normalize(issue: dict, comments: list[str]) -> dict`; `collect(client, jql: str, repo: str, warn=sys.stderr.write) -> dict`; `main(argv=None, client=None) -> int`; constants `EXCERPT_LIMIT=600`, `COMMENT_LIMIT=400`, `COMMENT_COUNT=3`, `NO_BUGS=3`.
- The `bugs.json` document it writes: `{"repo", "window": {"since","until"}, "projects": [...], "fetched": int, "comment_failures": int, "bugs": [bug]}` where each bug is `{"key","area" (portal|core|None),"component","summary","excerpt","comments": [str],"status","status_category","created" (YYYY-MM-DD),"assignee","labels","url"}`.

- [ ] **Step 1: Write the failing tests**

`plugins/common/oc-bug-root-causes/tests/test_rc_fetch.py`:

```python
import json

from conftest import FakeOpener, http_error

import jira_client as jc
import rc_fetch as rf


def adf(text):
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def issue(key, component="Frontend", summary="A bug", description=None):
    return {"key": key, "fields": {
        "summary": summary, "description": description,
        "components": [{"name": component}] if component else [],
        "status": {"name": "Done", "statusCategory": {"key": "done"}},
        "created": "2026-09-01T10:00:00.000+0200", "labels": ["reg"],
        "assignee": {"displayName": "Dev One"}}}


def comments(*texts):
    return {"comments": [{"author": {"displayName": "Dev One"}, "body": adf(t)}
                         for t in texts]}


def test_jql_selects_development_issue_bugs_in_a_half_open_window():
    jql = rf.build_jql(["INTRD"], "2026-09-01", "2026-10-01")
    assert jql.startswith("project in (INTRD) ")
    assert 'issuetype in (Bug, "Sub-bug")' in jql
    assert '"Root cause" = "Development issue"' in jql
    assert 'created >= "2026-09-01" AND created < "2026-10-01"' in jql


def test_fetch_comments_asks_for_the_newest_three_and_trims_each(jira_env):
    opener = FakeOpener([comments("fixed the copy constructor", "x" * 1000)])
    client = jc.JiraClient(opener=opener, env=jira_env)

    got = rf.fetch_comments(client, "INTRD-1")

    assert opener.urls()[0].endswith(
        "/rest/api/3/issue/INTRD-1/comment?orderBy=-created&maxResults=3")
    assert got[0] == "Dev One: fixed the copy constructor"
    assert len(got[1]) <= len("Dev One: ") + rf.COMMENT_LIMIT


def test_collect_drops_other_area_keeps_arealess_and_attaches_comments(jira_env):
    opener = FakeOpener([
        {"issues": [issue("INTRD-1", "Frontend"), issue("INTRD-2", "Backend"),
                    issue("INTRD-3", None)], "isLast": True},
        comments("c1"),   # INTRD-1
        comments(),       # INTRD-3 — INTRD-2 is out of scope, so no call for it
    ])

    doc = rf.collect(jc.JiraClient(opener=opener, env=jira_env), "jql", "portal")

    assert [b["key"] for b in doc["bugs"]] == ["INTRD-1", "INTRD-3"]
    assert doc["fetched"] == 3
    assert doc["bugs"][0]["comments"] == ["Dev One: c1"]
    assert doc["bugs"][1]["area"] is None


def test_a_comment_failure_costs_the_comments_not_the_bug(jira_env):
    warnings = []
    opener = FakeOpener([{"issues": [issue("INTRD-1")], "isLast": True}, http_error(500)])

    doc = rf.collect(jc.JiraClient(opener=opener, env=jira_env), "jql", "both",
                     warn=warnings.append)

    assert doc["bugs"][0]["comments"] == []
    assert doc["comment_failures"] == 1
    assert "INTRD-1" in warnings[0]


def test_normalize_keeps_a_600_char_excerpt_and_a_browse_url():
    rec = rf.normalize(issue("INTRD-1", description=adf("y" * 2000)), [])
    assert len(rec["excerpt"]) == rf.EXCERPT_LIMIT
    assert rec["url"] == "https://opencellsoft.atlassian.net/browse/INTRD-1"
    assert rec["created"] == "2026-09-01"
    assert rec["assignee"] == "Dev One"


def test_main_writes_the_document_and_exits_3_when_empty(tmp_path, jira_env):
    opener = FakeOpener([{"issues": [], "isLast": True}])
    out = tmp_path / "bugs.json"

    code = rf.main(["--since", "2026-09-01", "--until", "2026-10-01", "--out-bugs", str(out)],
                   client=jc.JiraClient(opener=opener, env=jira_env))

    assert code == rf.NO_BUGS
    doc = json.loads(out.read_text())
    assert doc["bugs"] == []
    assert doc["window"] == {"since": "2026-09-01", "until": "2026-10-01"}
    assert doc["repo"] == "both" and doc["projects"] == ["INTRD"]


def test_main_rejects_an_inverted_window(tmp_path, jira_env, capsys):
    code = rf.main(["--since", "2026-10-01", "--until", "2026-09-01",
                    "--out-bugs", str(tmp_path / "b.json")],
                   client=jc.JiraClient(opener=FakeOpener([]), env=jira_env))
    assert code == 2
    assert "must be before" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_rc_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rc_fetch'`.

- [ ] **Step 3: Implement `rc_fetch.py`**

```python
#!/usr/bin/env python3
"""Stage 1 of /oc-bug-root-causes: fetch a window's "Development issue" bugs.

Deterministic. The Root-cause filter is in the JQL, so nothing else is downloaded.
Area resolution is bug_fetch's, copied verbatim from /oc-bug-clusters, so the two
commands never split the same bug differently.

The Invalid/Declined/Duplicate filter of /oc-bug-clusters is deliberately NOT applied:
a bug whose root cause was set to "Development issue" has been triaged as a real defect.

Output: bugs.json, the full normalised records. The model never reads it; stage 2
turns it into the batch files the classifier reads.
"""
import argparse
import json
import sys
from urllib.parse import quote

from bug_fetch import area_of, areas_in_scope, excerpt, flatten_adf, resolve_window
from jira_client import BASE, JiraClient, JiraError, MissingToken

ROOT_CAUSE_FIELD = "customfield_10111"
ROOT_CAUSE_VALUE = "Development issue"
EXCERPT_LIMIT = 600
COMMENT_LIMIT = 400
COMMENT_COUNT = 3
NO_BUGS = 3

FIELDS = ["summary", "description", "issuetype", "status", "resolution", "components",
          "labels", "created", "assignee", "reporter", ROOT_CAUSE_FIELD]


def build_jql(projects, since, until):
    # "Sub-bug" is quoted defensively, as in /oc-bug-clusters.
    return (f'project in ({", ".join(projects)}) '
            f'AND issuetype in (Bug, "Sub-bug") '
            f'AND "Root cause" = "{ROOT_CAUSE_VALUE}" '
            f'AND created >= "{since}" AND created < "{until}" '
            f'ORDER BY created DESC')


def fetch_comments(client, key, count=COMMENT_COUNT, limit=COMMENT_LIMIT):
    """The newest `count` comments as 'Author: text', each trimmed to `limit` chars.
    Developers often explain the fix in a closing comment, which is why these are read."""
    page = client.get(f"/rest/api/3/issue/{quote(key)}/comment"
                      f"?orderBy=-created&maxResults={count}")
    out = []
    for comment in (page.get("comments") or [])[:count]:
        text = excerpt(flatten_adf(comment.get("body")), limit)
        if text:
            author = (comment.get("author") or {}).get("displayName") or "?"
            out.append(f"{author}: {text}")
    return out


def normalize(issue, comments):
    fields = issue.get("fields") or {}
    components = fields.get("components") or []
    status = fields.get("status") or {}
    key = issue.get("key")
    return {
        "key": key,
        "area": area_of(fields),
        "component": (components[0].get("name") if components else None),
        "summary": fields.get("summary") or "",
        "excerpt": excerpt(flatten_adf(fields.get("description")), EXCERPT_LIMIT),
        "comments": comments,
        "status": status.get("name"),
        "status_category": (status.get("statusCategory") or {}).get("key"),
        "created": (fields.get("created") or "")[:10],
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "labels": list(fields.get("labels") or []),
        "url": f"{BASE}/browse/{key}",
    }


def collect(client, jql, repo, warn=sys.stderr.write):
    """Fetch and normalise. Bugs of the area NOT in scope are excluded; bugs with no
    resolvable area are kept — the mistake still has a type when the area is unknown.
    A failed comment fetch costs that bug its comments, never its place in the run."""
    scope = areas_in_scope(repo)
    bugs, fetched, comment_failures = [], 0, 0
    for issue in client.search(jql, FIELDS):
        fetched += 1
        area = area_of(issue.get("fields") or {})
        if area is not None and area not in scope:
            continue
        try:
            comments = fetch_comments(client, issue["key"])
        except JiraError as ex:
            comment_failures += 1
            warn(f"WARNING: comments unavailable for {issue['key']}: {ex}\n")
            comments = []
        bugs.append(normalize(issue, comments))
    return {"repo": repo, "fetched": fetched, "comment_failures": comment_failures,
            "bugs": bugs}


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description='Fetch a window of "Development issue" bugs.')
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--repo", default="both", choices=["portal", "core", "both"])
    parser.add_argument("--out-bugs", required=True)
    args = parser.parse_args(argv)

    try:
        since, until = resolve_window(args.since, args.until)
        client = client or JiraClient()
    except (MissingToken, ValueError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    projects = [p.strip() for p in args.project.split(",") if p.strip()]
    document = collect(client, build_jql(projects, since, until), args.repo)
    document["window"] = {"since": since, "until": until}
    document["projects"] = projects

    with open(args.out_bugs, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)

    bugs = document["bugs"]
    sys.stderr.write(
        f'Analysing {", ".join(projects)} "Development issue" bugs, {args.repo}, '
        f"{since} → {until}\n"
        f"  fetched {document['fetched']}, kept {len(bugs)} "
        f"({sum(1 for b in bugs if b['area'] is None)} with no resolvable area, "
        f"{document['comment_failures']} without comments)\n")
    if not bugs:
        sys.stderr.write(f"No Development issue bugs created in {since} → {until} "
                         f"for {', '.join(projects)}\n")
        return NO_BUGS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `16 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_fetch.py plugins/common/oc-bug-root-causes/tests/test_rc_fetch.py
git commit -m "oc-bug-root-causes: fetch Development-issue bugs with their last comments

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: PR matching, selection and diff trimming (pure functions) — `rc_pr.py`

**Files:**
- Create: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_pr.py`
- Test: `plugins/common/oc-bug-root-causes/tests/test_rc_pr.py`

**Interfaces:**
- Consumes: `bitbucket_client.{BASE, BitbucketClient, BitbucketError, MissingToken, auth_header}` (Task 1) — imported now; used in Task 5.
- Produces: `mentions(pr: dict, key: str) -> bool`; `select_pr(prs: list[dict]) -> dict | None`; `is_excluded(path: str) -> bool`; `split_diff(text: str) -> list[tuple[str, str]]`; `trim_diff(text: str, cap: int = DIFF_CAP) -> str`; `diff_filestats(text: str) -> list[str]` (entries `"path +A -R"`); `jira_evidence(note: str) -> dict`; `write_batches(rows: list[dict], directory: str, size: int = BATCH_SIZE) -> list[str]`; constants `WORKSPACE, REPOS, PR_STATES, DIFF_CAP=4096, FILESTAT_CAP=40, BATCH_SIZE=30`.
- Evidence dict shape (shared with Tasks 5-7): `{"evidence": "pr"|"jira", "pr_url": str|None, "pr_title": str|None, "files": [str], "diff": str, "note": str|None}`.

- [ ] **Step 1: Write the failing tests**

`plugins/common/oc-bug-root-causes/tests/test_rc_pr.py`:

```python
import json

from conftest import SAMPLE_DIFF

import rc_pr as rp


def pr(id, title="", branch="", state="MERGED", dest="dev", updated="2026-09-01T00:00:00"):
    return {"id": id, "title": title, "state": state, "updated_on": updated,
            "source": {"branch": {"name": branch}},
            "destination": {"branch": {"name": dest}},
            "links": {"html": {"href": f"https://bitbucket.org/opencellsoft/x/pull-requests/{id}"}}}


def test_key_must_match_whole_not_as_a_prefix():            # Review Focus 1
    assert rp.mentions(pr(1, title="INTRD-45162 fix rating"), "INTRD-45162")
    assert not rp.mentions(pr(2, title="INTRD-45162 fix rating"), "INTRD-4516")
    assert rp.mentions(pr(3, branch="fix/INTRD-4516"), "INTRD-4516")
    assert rp.mentions(pr(4, title="[intrd-4516] lower case"), "INTRD-4516")


def test_select_prefers_merged_into_dev_then_newest_merged_then_newest_any():
    dev = pr(1, dest="dev", updated="2026-08-01")
    other = pr(2, dest="17.x", updated="2026-09-01")
    open_ = pr(3, state="OPEN", updated="2026-09-10")
    assert rp.select_pr([other, dev, open_])["id"] == 1
    assert rp.select_pr([other, open_])["id"] == 2
    assert rp.select_pr([open_, pr(4, state="DECLINED", updated="2026-01-01")])["id"] == 3
    assert rp.select_pr([]) is None


def test_trim_keeps_production_files_in_order_and_drops_noise():
    out = rp.trim_diff(SAMPLE_DIFF)
    assert "src/app/Grid.tsx" in out and "src/main/java/Foo.java" in out
    assert out.index("Grid.tsx") < out.index("Foo.java")
    for noise in ("Grid.test.tsx", "package-lock.json", "translation.json", "FooTest.java"):
        assert noise not in out


def test_trim_caps_bytes_without_splitting_a_character():
    big = "diff --git a/a.java b/a.java\n" + "+é\n" * 5000
    out = rp.trim_diff(big, cap=100)
    body, sep, _ = out.partition("\n… [diff truncated")
    assert sep, "truncation must be announced"
    assert len(body.encode("utf-8")) <= 100
    assert "\ufffd" not in body


def test_file_stats_cover_every_file_including_tests():
    stats = rp.diff_filestats(SAMPLE_DIFF)
    assert "src/app/Grid.test.tsx +1 -0" in stats
    assert "opencell-admin/src/main/java/Foo.java +1 -1" in stats
    assert len(stats) == 6


def test_file_stats_ignore_the_plus_plus_plus_header():
    diff = "diff --git a/x.java b/x.java\n--- a/x.java\n+++ b/x.java\n+new\n-old\n"
    assert rp.diff_filestats(diff) == ["x.java +1 -1"]


def test_file_stats_are_capped():
    many = "".join(f"diff --git a/f{i}.java b/f{i}.java\n+x\n"
                   for i in range(rp.FILESTAT_CAP + 5))
    stats = rp.diff_filestats(many)
    assert len(stats) == rp.FILESTAT_CAP + 1
    assert stats[-1] == "… 5 more files"


def test_a_diff_without_file_headers_yields_nothing():    # Review Focus 4
    assert rp.trim_diff("") == ""
    assert rp.trim_diff("Binary files differ\n") == ""
    assert rp.diff_filestats("") == []


def test_jira_evidence_shape():
    assert rp.jira_evidence("no PR found") == {
        "evidence": "jira", "pr_url": None, "pr_title": None, "files": [], "diff": "",
        "note": "no PR found"}


def test_write_batches_splits_rows_and_removes_stale_files(tmp_path):
    (tmp_path / "classify.009.jsonl").write_text("stale\n")
    rows = [{"key": f"INTRD-{i}"} for i in range(65)]

    paths = rp.write_batches(rows, str(tmp_path), size=30)

    assert [p.rsplit("/", 1)[1] for p in paths] == [
        "classify.001.jsonl", "classify.002.jsonl", "classify.003.jsonl"]
    assert not (tmp_path / "classify.009.jsonl").exists()
    lines = (tmp_path / "classify.003.jsonl").read_text().splitlines()
    assert [json.loads(l)["key"] for l in lines] == [f"INTRD-{i}" for i in range(60, 65)]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_rc_pr.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rc_pr'`.

- [ ] **Step 3: Implement the pure part of `rc_pr.py`**

```python
#!/usr/bin/env python3
"""Stage 2 of /oc-bug-root-causes: attach each bug's fixing-PR diff as evidence.

Deterministic. For every bug it finds the pull request that fixed it, keeps a trimmed
diff plus a per-file line count, and writes the classifier's input in batch files.

Two Bitbucket costs shape this module:
  * one PR search per repository per bug (title OR branch in a single `q`), and the file
    list is computed from the diff rather than a separate diffstat call — a 280-bug
    window stays near 600 requests, inside the hourly rate limit;
  * the diff endpoint answers 302 to a signed URL on another host. The redirect is
    followed by hand so the Authorization header is only sent to the host that issued
    the request.

A bug whose lookup fails is never dropped: it falls back to Jira-only evidence and says
so. Only a 401 stops the stage, because every later call would fail the same way.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from bitbucket_client import BASE, BitbucketClient, BitbucketError, MissingToken, auth_header

WORKSPACE = "opencellsoft"
REPOS = {"portal": ["opencell-portal"], "core": ["opencell-core"],
         None: ["opencell-portal", "opencell-core"]}
# Without an explicit state Bitbucket lists OPEN PRs only, and a fix is usually MERGED.
PR_STATES = ["MERGED", "OPEN", "DECLINED", "SUPERSEDED"]
DIFF_CAP = 4096
FILESTAT_CAP = 40
BATCH_SIZE = 30

# Tests, lockfiles, translations and build output say nothing about the mistake and
# would eat the 4 KB budget first. They still appear in the per-file list.
EXCLUDED = [re.compile(p) for p in (
    r"(^|/)src/test/", r"(^|/)__tests__/", r"(^|/)tests?/(e2e|support)/",
    r"\.(test|spec)\.[cm]?[jt]sx?$", r"\.snap$",
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml)$",
    r"(^|/)(i18n|locales)/", r"\.min\.(js|css)$", r"(^|/)(dist|build|generated)/",
)]
FILE_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
TRUNCATED = "\n… [diff truncated at {cap} bytes]\n"


def _key_pattern(key):
    # `~` in a Bitbucket query is a substring match: INTRD-4516 also finds INTRD-45162.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(key)}(?![0-9])", re.I)


def mentions(pr, key):
    pattern = _key_pattern(key)
    title = pr.get("title") or ""
    branch = ((pr.get("source") or {}).get("branch") or {}).get("name") or ""
    return bool(pattern.search(title) or pattern.search(branch))


def select_pr(prs):
    """Merged into dev, else the newest merged, else the newest of any state.
    A fix merged to several branches has one PR per branch; the dev one is canonical."""
    def dest(p):
        return ((p.get("destination") or {}).get("branch") or {}).get("name")

    merged = [p for p in prs if p.get("state") == "MERGED"]
    for pool in ([p for p in merged if dest(p) == "dev"], merged, list(prs)):
        if pool:
            return max(pool, key=lambda p: p.get("updated_on") or "")
    return None


def is_excluded(path):
    return any(p.search(path) for p in EXCLUDED)


def split_diff(text):
    """[(path, chunk)] in file order; text before the first header is dropped."""
    starts = [m.start() for m in FILE_HEADER.finditer(text or "")]
    chunks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end]
        chunks.append((FILE_HEADER.match(chunk).group(2), chunk))
    return chunks


def trim_diff(text, cap=DIFF_CAP):
    kept = "".join(chunk for path, chunk in split_diff(text) if not is_excluded(path))
    data = kept.encode("utf-8")
    if len(data) <= cap:
        return kept
    return data[:cap].decode("utf-8", "ignore") + TRUNCATED.format(cap=cap)


def diff_filestats(text):
    out = []
    for path, chunk in split_diff(text):
        lines = chunk.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        out.append(f"{path} +{added} -{removed}")
    if len(out) > FILESTAT_CAP:
        out = out[:FILESTAT_CAP] + [f"… {len(out) - FILESTAT_CAP} more files"]
    return out


def jira_evidence(note):
    return {"evidence": "jira", "pr_url": None, "pr_title": None, "files": [], "diff": "",
            "note": note}


def write_batches(rows, directory, size=BATCH_SIZE):
    """One classify.NNN.jsonl per `size` rows. Stale files from a larger earlier run are
    removed first, or a sub-agent would classify bugs that are no longer in the window."""
    os.makedirs(directory, exist_ok=True)
    for stale in glob.glob(os.path.join(directory, "classify.*.jsonl")):
        os.remove(stale)
    paths = []
    for start in range(0, len(rows), size):
        path = os.path.join(directory, f"classify.{start // size + 1:03d}.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows[start:start + size]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        paths.append(path)
    return paths
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `26 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_pr.py plugins/common/oc-bug-root-causes/tests/test_rc_pr.py
git commit -m "oc-bug-root-causes: PR matching, selection and diff trimming

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Bitbucket evidence fetching, caching and the stage-2 CLI — `rc_pr.py`

**Files:**
- Modify: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_pr.py` (append)
- Test: `plugins/common/oc-bug-root-causes/tests/test_rc_pr.py` (append)

**Interfaces:**
- Consumes: Task 4's functions; `BitbucketClient.paginate(path, params)`; `auth_header()`.
- Produces: `EvidenceFetcher(client, opener=None, auth=None, workspace=WORKSPACE, sleep=time.sleep)` with `.get_raw(url) -> bytes`, `.candidates(slug, key) -> list[dict]` (each PR dict carries `_slug`), `.evidence_for(bug: dict) -> dict`; `gather_all(bugs, fetcher, cache_dir, warn=sys.stderr.write, disabled_reason="PR lookup disabled") -> dict[key, evidence]`; `classify_rows(bugs, evidence) -> list[dict]`; `main(argv=None, fetcher_factory=None, warn=sys.stderr.write) -> int`.
- Classify row shape (read by sub-agents and by Task 7): `{"key","area","summary","excerpt","comments","evidence","pr_url","pr_title","files","diff"}`.

- [ ] **Step 1: Write the failing tests** (append to `test_rc_pr.py`)

```python
import pytest

from conftest import FakeOpener, http_error
from bitbucket_client import BitbucketError, MissingToken


class StubClient:
    """Stands in for BitbucketClient.paginate; records (path, params)."""

    def __init__(self, by_slug):
        self.by_slug = by_slug
        self.calls = []

    def paginate(self, path, params=None):
        self.calls.append((path, params))
        return iter(self.by_slug.get(path.split("/")[3], []))


def fetcher(by_slug, raw_results, sleep=None):
    opener = FakeOpener(raw_results)
    f = rp.EvidenceFetcher(StubClient(by_slug), opener=opener, auth="Bearer ATCTTtok",
                           sleep=sleep or (lambda s: None))
    return f, opener


def test_diff_redirect_to_another_host_is_followed_without_credentials():  # Review Focus 2
    f, opener = fetcher({}, [
        http_error(302, headers={"Location": "https://bbuseruploads.s3.amazonaws.com/d?sig=1"}),
        b"diff body"])

    assert f.get_raw("https://api.bitbucket.org/2.0/repositories/w/r/pullrequests/1/diff") \
        == b"diff body"
    first, second = opener.requests
    assert first.get_header("Authorization") == "Bearer ATCTTtok"
    assert second.full_url.startswith("https://bbuseruploads.s3.amazonaws.com/")
    assert second.get_header("Authorization") is None


def test_same_host_redirect_keeps_credentials():
    f, opener = fetcher({}, [http_error(302, headers={"Location": "/2.0/other"}), b"ok"])
    f.get_raw("https://api.bitbucket.org/2.0/x")
    assert opener.requests[1].full_url == "https://api.bitbucket.org/2.0/other"
    assert opener.requests[1].get_header("Authorization") == "Bearer ATCTTtok"


def test_raw_fetch_retries_rate_limits():                  # Review Focus 3
    slept = []
    f, _ = fetcher({}, [http_error(429), http_error(503), b"ok"], sleep=slept.append)
    assert f.get_raw("https://api.bitbucket.org/2.0/x") == b"ok"
    assert slept == [2, 4]


def test_raw_fetch_401_names_both_schemes():
    f, _ = fetcher({}, [http_error(401)])
    with pytest.raises(BitbucketError) as ex:
        f.get_raw("https://api.bitbucket.org/2.0/x")
    message = str(ex.value)
    assert message.startswith("HTTP 401")
    assert "Bearer" in message and "ATATT" in message


def test_evidence_picks_the_dev_pr_and_trims_its_diff():
    prs = [pr(7, title="INTRD-1 fix", dest="17.x", updated="2026-09-05"),
           pr(8, title="INTRD-1 fix", dest="dev", updated="2026-09-01"),
           pr(9, title="INTRD-10 unrelated")]
    f, opener = fetcher({"opencell-portal": prs}, [SAMPLE_DIFF.encode()])

    ev = f.evidence_for({"key": "INTRD-1", "area": "portal"})

    assert ev["evidence"] == "pr" and ev["note"] is None
    assert ev["pr_url"].endswith("/pull-requests/8")
    assert opener.urls()[0].endswith(
        "/repositories/opencellsoft/opencell-portal/pullrequests/8/diff")
    assert "Grid.test.tsx" not in ev["diff"]
    assert "src/app/Grid.test.tsx +1 -0" in ev["files"]
    _, params = f.client.calls[0]
    assert params["q"] == '(title ~ "INTRD-1" OR source.branch.name ~ "INTRD-1")'
    assert params["state"] == rp.PR_STATES


def test_an_arealess_bug_is_looked_up_in_both_repositories():  # Review Focus 5
    f, opener = fetcher({
        "opencell-portal": [pr(1, title="INTRD-5", state="OPEN", updated="2026-09-09")],
        "opencell-core": [pr(2, title="INTRD-5", updated="2026-09-01")]}, [b""])

    ev = f.evidence_for({"key": "INTRD-5", "area": None})

    assert [path.split("/")[3] for path, _ in f.client.calls] == [
        "opencell-portal", "opencell-core"]
    assert opener.urls()[0].endswith("/opencell-core/pullrequests/2/diff")  # merged wins
    assert ev["evidence"] == "pr"


def test_no_matching_pr_falls_back_to_jira():
    f, _ = fetcher({"opencell-core": [pr(3, title="INTRD-10 not this one")]}, [])
    assert f.evidence_for({"key": "INTRD-1", "area": "core"}) == rp.jira_evidence("no PR found")


class StubFetcher:
    def __init__(self, outcomes):
        self.outcomes = dict(outcomes)
        self.seen = []

    def evidence_for(self, bug):
        self.seen.append(bug["key"])
        outcome = self.outcomes[bug["key"]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


PR_EV = {"evidence": "pr", "pr_url": "u", "pr_title": "t", "files": ["a +1 -0"],
         "diff": "d", "note": None}
BUGS = [{"key": f"INTRD-{i}", "area": "portal"} for i in (1, 2, 3)]


def test_a_401_stops_all_further_lookups(tmp_path):
    warnings = []
    f = StubFetcher({"INTRD-1": BitbucketError("HTTP 401 on GET x: rejected")})

    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)

    assert f.seen == ["INTRD-1"]
    assert all(e["evidence"] == "jira" for e in ev.values())
    assert ev["INTRD-3"]["note"] == "Bitbucket 401"
    assert "Jira-only" in warnings[0]


def test_one_failed_lookup_does_not_stop_the_others(tmp_path):
    warnings = []
    f = StubFetcher({"INTRD-1": BitbucketError("HTTP 500 on GET x"), "INTRD-2": PR_EV,
                     "INTRD-3": rp.jira_evidence("no PR found")})

    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)

    assert ev["INTRD-1"]["note"] == "PR lookup failed"
    assert ev["INTRD-2"] == PR_EV
    assert "INTRD-1" in warnings[0]


def test_pr_evidence_is_cached_and_jira_fallbacks_are_not(tmp_path):
    rp.gather_all(BUGS, StubFetcher({"INTRD-1": PR_EV, "INTRD-2": rp.jira_evidence("no PR found"),
                                     "INTRD-3": PR_EV}), str(tmp_path))
    again = StubFetcher({"INTRD-2": rp.jira_evidence("no PR found")})

    ev = rp.gather_all(BUGS, again, str(tmp_path))

    assert again.seen == ["INTRD-2"]
    assert ev["INTRD-1"] == PR_EV


def test_no_fetcher_means_jira_only_without_reading_the_cache(tmp_path):
    (tmp_path / "INTRD-1.json").write_text(json.dumps(PR_EV))
    ev = rp.gather_all(BUGS, None, str(tmp_path), disabled_reason="--no-pr")
    assert ev["INTRD-1"] == rp.jira_evidence("--no-pr")


FULL = [{"key": "INTRD-1", "area": "portal", "summary": "s", "excerpt": "e",
         "comments": ["c"]}]


def run_main(tmp_path, extra, factory, warnings=None):
    bugs = tmp_path / "bugs.json"
    bugs.write_text(json.dumps({"repo": "both", "bugs": FULL}))
    out = tmp_path / "classify_input.jsonl"
    code = rp.main(["--bugs", str(bugs), "--run", str(tmp_path), "--out-classify", str(out)]
                   + extra, fetcher_factory=factory,
                   warn=(warnings.append if warnings is not None else lambda m: None))
    return code, [json.loads(l) for l in out.read_text().splitlines()]


def test_main_without_a_token_continues_jira_only(tmp_path):
    warnings = []

    def no_token():
        raise MissingToken("BITBUCKET_ACCESS_TOKEN must be set")

    code, rows = run_main(tmp_path, [], no_token, warnings)

    assert code == 0
    assert rows[0]["evidence"] == "jira"
    assert rows[0]["summary"] == "s" and rows[0]["comments"] == ["c"]
    assert "Jira-only" in warnings[0]
    assert (tmp_path / "batches" / "classify.001.jsonl").exists()


def test_main_no_pr_never_builds_a_fetcher(tmp_path):
    def boom():
        raise AssertionError("must not be called with --no-pr")

    code, rows = run_main(tmp_path, ["--no-pr"], boom)
    assert code == 0 and rows[0]["evidence"] == "jira"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_rc_pr.py -q`
Expected: FAIL — `AttributeError: module 'rc_pr' has no attribute 'EvidenceFetcher'`.

- [ ] **Step 3: Append the fetching part to `rc_pr.py`**

```python
MAX_ATTEMPTS = 5
RETRY_STATUS = (429, 503)
REDIRECT_STATUS = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 3
AUTH_HINT = (" — the credential was rejected. An ATCTT... repository/workspace Access "
             "Token must be sent as `Authorization: Bearer` with no email; an ATATT... "
             "Atlassian API token must be sent as Basic email:token. Check "
             "BITBUCKET_ACCESS_TOKEN's prefix and that BITBUCKET_EMAIL is set only for "
             "the ATATT form.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as HTTPError so get_raw decides which headers travel."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class EvidenceFetcher:
    def __init__(self, client, opener=None, auth=None, workspace=WORKSPACE, sleep=time.sleep):
        self.client = client
        self._open = opener or urllib.request.build_opener(_NoRedirect).open
        self._auth = auth
        self._sleep = sleep
        self.workspace = workspace

    def get_raw(self, url):
        """GET a non-JSON body. urllib would forward Authorization to the signed URL's
        host; this sends it only while the host is unchanged, as curl -L does."""
        origin = urllib.parse.urlsplit(url).netloc
        hops = attempts = 0
        while True:
            same_host = urllib.parse.urlsplit(url).netloc == origin
            headers = {"Authorization": self._auth} if (same_host and self._auth) else {}
            request = urllib.request.Request(url, method="GET", headers=headers)
            label = urllib.parse.urlsplit(url).path
            try:
                with self._open(request, timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as ex:
                if ex.code in REDIRECT_STATUS and hops < MAX_REDIRECTS:
                    location = ex.headers.get("Location") if ex.headers else None
                    if not location:
                        raise BitbucketError(f"HTTP {ex.code} without Location on GET {label}") from ex
                    url = urllib.parse.urljoin(url, location)
                    hops += 1
                    continue
                if ex.code in RETRY_STATUS and attempts < MAX_ATTEMPTS - 1:
                    attempts += 1
                    self._sleep(2 * attempts)
                    continue
                detail = ex.read()[:200].decode("utf-8", "replace")
                if ex.code == 401:
                    detail += AUTH_HINT
                raise BitbucketError(f"HTTP {ex.code} on GET {label}: {detail}") from ex

    def candidates(self, slug, key):
        query = f'(title ~ "{key}" OR source.branch.name ~ "{key}")'
        found = self.client.paginate(f"/repositories/{self.workspace}/{slug}/pullrequests",
                                     {"q": query, "state": PR_STATES, "pagelen": 50})
        return [dict(p, _slug=slug) for p in found if mentions(p, key)]

    def evidence_for(self, bug):
        key = bug["key"]
        prs = [p for slug in REPOS[bug.get("area")] for p in self.candidates(slug, key)]
        chosen = select_pr(prs)
        if chosen is None:
            return jira_evidence("no PR found")
        slug = chosen["_slug"]
        raw = self.get_raw(f"{BASE}/repositories/{self.workspace}/{slug}"
                           f"/pullrequests/{chosen['id']}/diff")
        diff = raw.decode("utf-8", "replace")
        html = (((chosen.get("links") or {}).get("html") or {}).get("href")
                or f"https://bitbucket.org/{self.workspace}/{slug}/pull-requests/{chosen['id']}")
        return {"evidence": "pr", "pr_url": html, "pr_title": chosen.get("title") or "",
                "files": diff_filestats(diff), "diff": trim_diff(diff), "note": None}


def gather_all(bugs, fetcher, cache_dir, warn=sys.stderr.write,
               disabled_reason="PR lookup disabled"):
    """Evidence for every bug, in order. Only PR evidence is cached: a Jira-only
    fallback is retried on the next run, when a token or a merged PR may exist."""
    os.makedirs(cache_dir, exist_ok=True)
    results = {}
    for bug in bugs:
        key = bug["key"]
        if fetcher is None:
            results[key] = jira_evidence(disabled_reason)
            continue
        path = os.path.join(cache_dir, f"{key}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                results[key] = json.load(handle)
            continue
        try:
            evidence = fetcher.evidence_for(bug)
        except BitbucketError as ex:
            if str(ex).startswith("HTTP 401"):
                warn(f"WARNING: Bitbucket rejected the credential; continuing Jira-only.\n{ex}\n")
                fetcher, disabled_reason = None, "Bitbucket 401"
                results[key] = jira_evidence(disabled_reason)
                continue
            warn(f"WARNING: PR lookup failed for {key}: {ex}\n")
            results[key] = jira_evidence("PR lookup failed")
            continue
        if evidence["evidence"] == "pr":
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(evidence, handle, ensure_ascii=False)
        results[key] = evidence
    return results


def classify_rows(bugs, evidence):
    rows = []
    for b in bugs:
        ev = evidence[b["key"]]
        rows.append({"key": b["key"], "area": b["area"], "summary": b["summary"],
                     "excerpt": b["excerpt"], "comments": b["comments"],
                     "evidence": ev["evidence"], "pr_url": ev["pr_url"],
                     "pr_title": ev["pr_title"], "files": ev["files"], "diff": ev["diff"]})
    return rows


def main(argv=None, fetcher_factory=None, warn=sys.stderr.write):
    parser = argparse.ArgumentParser(description="Attach fixing-PR evidence to each bug.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--run", required=True, help="run directory (cache and batches)")
    parser.add_argument("--out-classify", required=True)
    parser.add_argument("--no-pr", action="store_true")
    parser.add_argument("--workspace", default=WORKSPACE)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        bugs = json.load(handle)["bugs"]

    fetcher, reason = None, "--no-pr"
    if not args.no_pr:
        factory = fetcher_factory or (lambda: EvidenceFetcher(
            BitbucketClient(), auth=auth_header(), workspace=args.workspace))
        try:
            fetcher = factory()
        except MissingToken as ex:
            warn(f"WARNING: {ex}\nContinuing with Jira-only evidence.\n")
            reason = "no Bitbucket token"

    evidence = gather_all(bugs, fetcher, os.path.join(args.run, "pr"), warn=warn,
                          disabled_reason=reason)
    rows = classify_rows(bugs, evidence)
    with open(args.out_classify, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    batches = write_batches(rows, os.path.join(args.run, "batches"), args.batch_size)

    with_pr = sum(1 for r in rows if r["evidence"] == "pr")
    sys.stderr.write(f"PR evidence for {with_pr} of {len(rows)} bugs; "
                     f"{len(batches)} batch file(s) in {os.path.join(args.run, 'batches')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `39 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_pr.py plugins/common/oc-bug-root-causes/tests/test_rc_pr.py
git commit -m "oc-bug-root-causes: fetch fixing-PR diffs with redirect-safe auth, cache and batches

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Assignment validation and the aggregate model — `rc_report.py`

**Files:**
- Create: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_report.py`
- Test: `plugins/common/oc-bug-root-causes/tests/test_rc_report.py`

**Interfaces:**
- Consumes: `bug_fetch.areas_in_scope` (Task 1); the taxonomy format (Task 2); `bugs.json` (Task 3); classify rows (Task 5).
- Produces: `load_taxonomy(path) -> dict[str, str]` (ordered name → definition); `AssignmentError(problems: list[str])`; `merge_assignments(parts: list[dict]) -> dict`; `validate(keys: list[str], assignments: dict, taxonomy: dict, min_new: int = MIN_NEW) -> list[str]` (the new categories); `build_model(document, rows, assignments, taxonomy, new=()) -> dict`; constants `INSUFFICIENT`, `MIN_NEW=5`, `CAUSE_LIMIT=120`, `EXAMPLES=5`.
- Model shape (used by Task 7): `{"window","projects","repo","total","evidence": {"pr","jira"},"regression": int,"new_categories": [..],"views": {"all": [row], "portal"?: [row], "core"?: [row]},"insufficient": [bug],"no_area": [bug],"bugs": [bug]}`; a `row` is `{"category","definition","is_new","count","share","areas": {"portal","core","none"},"regression","regression_rate","evidence": {"pr","jira"},"low_confidence","examples": [bug]}`; a merged `bug` is the Task 3 record plus `"category","confidence","regression","cause","evidence","pr_url"`.

- [ ] **Step 1: Write the failing tests**

`plugins/common/oc-bug-root-causes/tests/test_rc_report.py`:

```python
import pytest

import rc_report as rr

TAXONOMY_MD = """# t

Intro paragraph.

## null-handling
A missing value was not guarded.
Second line of the same paragraph.

Examples: INTRD-1

## api-contract
Wrong HTTP status.

Examples: INTRD-2

## insufficient-evidence
Too little signal.

Examples: INTRD-3
"""

TAX = {"null-handling": "A missing value was not guarded.",
       "api-contract": "Wrong HTTP status.",
       "insufficient-evidence": "Too little signal."}


def bug(key, area="portal", created="2026-09-01", summary="A bug"):
    return {"key": key, "area": area, "component": None, "summary": summary, "excerpt": "",
            "comments": [], "status": "Done", "status_category": "done", "created": created,
            "assignee": "Dev One", "labels": [],
            "url": f"https://opencellsoft.atlassian.net/browse/{key}"}


def a(category, conf="high", reg=False, cause="the cause"):
    return {"category": category, "confidence": conf, "regression": reg, "cause": cause}


def model_for(bugs, asg, rows=None, repo="both", new=()):
    doc = {"repo": repo, "window": {"since": "2026-09-01", "until": "2026-10-01"},
           "projects": ["INTRD"], "bugs": bugs}
    rows = rows or [{"key": b["key"], "evidence": "jira", "pr_url": None} for b in bugs]
    return rr.build_model(doc, rows, asg, TAX, new)


def test_load_taxonomy_reads_names_and_first_paragraph(tmp_path):
    path = tmp_path / "t.md"
    path.write_text(TAXONOMY_MD)
    tax = rr.load_taxonomy(str(path))
    assert list(tax) == ["null-handling", "api-contract", "insufficient-evidence"]
    assert tax["null-handling"] == ("A missing value was not guarded. "
                                    "Second line of the same paragraph.")


def test_missing_assignments_are_named():
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1", "A-2"], {"A-1": a("null-handling")}, TAX)
    assert "A-2" in str(ex.value)


def test_assignments_for_keys_outside_the_run_are_rejected():
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1"], {"A-1": a("api-contract"), "Z-9": a("api-contract")}, TAX)
    assert "Z-9" in str(ex.value)


def test_malformed_fields_are_each_reported():
    bad = {"A-1": {"category": "api-contract", "confidence": "medium", "regression": "yes",
                   "cause": " "}}
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1"], bad, TAX)
    assert len(ex.value.problems) == 3


def test_an_unknown_category_needs_five_bugs():
    keys = [f"A-{i}" for i in range(5)]
    four = {k: a("brand-new") for k in keys[:4]}
    four[keys[4]] = a("null-handling")
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(keys, four, TAX)
    assert "brand-new" in str(ex.value)
    assert rr.validate(keys, {k: a("brand-new") for k in keys}, TAX) == ["brand-new"]


def test_merge_assignments_rejects_a_key_classified_two_ways():
    assert rr.merge_assignments([{"A-1": a("api-contract")}, {"A-2": a("null-handling")}]) \
        == {"A-1": a("api-contract"), "A-2": a("null-handling")}
    with pytest.raises(rr.AssignmentError) as ex:
        rr.merge_assignments([{"A-1": a("api-contract")}, {"A-1": a("null-handling")}])
    assert "A-1" in str(ex.value)


def test_ranking_counts_shares_regressions_and_evidence():
    bugs = [bug("A-1", "portal"), bug("A-2", "core"), bug("A-3", None), bug("A-4", "portal")]
    asg = {"A-1": a("null-handling", reg=True), "A-2": a("null-handling", conf="low"),
           "A-3": a("null-handling"), "A-4": a("api-contract")}
    rows = [{"key": "A-1", "evidence": "pr", "pr_url": "p1"}] + [
        {"key": k, "evidence": "jira", "pr_url": None} for k in ("A-2", "A-3", "A-4")]

    m = model_for(bugs, asg, rows)

    top = m["views"]["all"][0]
    assert top["category"] == "null-handling" and top["count"] == 3
    assert top["share"] == 0.75
    assert top["areas"] == {"portal": 1, "core": 1, "none": 1}
    assert top["regression"] == 1 and top["regression_rate"] == pytest.approx(1 / 3)
    assert top["evidence"] == {"pr": 1, "jira": 2} and top["low_confidence"] == 1
    assert m["total"] == 4 and m["evidence"] == {"pr": 1, "jira": 3}
    assert m["regression"] == 1
    assert m["views"]["portal"][0]["count"] == 1
    assert [b["key"] for b in m["no_area"]] == ["A-3"]


def test_insufficient_evidence_ranks_last_even_when_largest():
    bugs = [bug(f"A-{i}") for i in range(4)]
    asg = {"A-0": a("api-contract"), **{f"A-{i}": a("insufficient-evidence") for i in (1, 2, 3)}}
    m = model_for(bugs, asg)
    assert [r["category"] for r in m["views"]["all"]] == ["api-contract", "insufficient-evidence"]
    assert len(m["insufficient"]) == 3


def test_examples_prefer_pr_evidence_then_newest_and_stop_at_five():
    bugs = [bug(f"A-{i}", created=f"2026-09-{10 + i:02d}") for i in range(7)]
    asg = {b["key"]: a("null-handling") for b in bugs}
    rows = [{"key": b["key"], "evidence": "pr" if b["key"] == "A-0" else "jira",
             "pr_url": None} for b in bugs]
    examples = model_for(bugs, asg, rows)["views"]["all"][0]["examples"]
    assert [b["key"] for b in examples] == ["A-0", "A-6", "A-5", "A-4", "A-3"]


def test_single_area_run_has_no_other_area_view():
    m = model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal")
    assert set(m["views"]) == {"all", "portal"}


def test_cause_is_trimmed_and_new_categories_are_labelled():
    m = model_for([bug("A-1")], {"A-1": a("brand-new", cause="z" * 300)}, new=["brand-new"])
    row = m["views"]["all"][0]
    assert row["is_new"] and "dev-root-causes.md" in row["definition"]
    assert len(m["bugs"][0]["cause"]) == rr.CAUSE_LIMIT
    assert m["new_categories"] == ["brand-new"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_rc_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rc_report'`.

- [ ] **Step 3: Implement the model part of `rc_report.py`**

```python
#!/usr/bin/env python3
"""Stage 4 of /oc-bug-root-causes: assignments + evidence -> the ranking model -> reports.

No network. The classification is the only LLM judgement in the command, and it arrives
in several parts (one per sub-agent batch), so this module refuses to report on anything
it cannot account for: a missing key, a key outside the run, a key classified two ways,
or a coined category too small to be one. A silently missing bug would look exactly like
a category that did not happen.
"""
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
from collections import Counter
from datetime import date

from bug_fetch import areas_in_scope

INSUFFICIENT = "insufficient-evidence"
MIN_NEW = 5
CAUSE_LIMIT = 120
EXAMPLES = 5
AREA_ORDER = ["portal", "core"]
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
NEW_DEFINITION = "New category coined in this run — add it to references/dev-root-causes.md."


class AssignmentError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def load_taxonomy(path):
    """Ordered {name: definition}; the definition is the first paragraph under the heading."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    taxonomy = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        name = heading.strip()
        if not KEBAB.fullmatch(name):
            continue
        paragraph = body.strip().split("\n\n", 1)[0]
        taxonomy[name] = " ".join(paragraph.split())
    return taxonomy


def _shown(keys):
    keys = list(keys)
    more = f" (+{len(keys) - 10} more)" if len(keys) > 10 else ""
    return ", ".join(keys[:10]) + more


def merge_assignments(parts):
    merged, conflicts = {}, set()
    for part in parts:
        for key, value in part.items():
            if key in merged and merged[key] != value:
                conflicts.add(key)
            merged[key] = value
    if conflicts:
        raise AssignmentError([f"classified differently in two parts: {_shown(sorted(conflicts))}"])
    return merged


def validate(keys, assignments, taxonomy, min_new=MIN_NEW):
    """Raise AssignmentError listing every problem; return the new categories."""
    problems = []
    known = set(keys)
    missing = [k for k in keys if k not in assignments]
    if missing:
        problems.append(f"no category assigned for: {_shown(missing)}")
    outside = sorted(k for k in assignments if k not in known)
    if outside:
        problems.append(f"assignments for bugs not in this run: {_shown(outside)}")

    coined = Counter()
    for key in keys:
        if key not in assignments:
            continue
        entry = assignments[key]
        if not isinstance(entry, dict):
            problems.append(f"{key}: the assignment must be an object")
            continue
        category = entry.get("category")
        if not isinstance(category, str) or not KEBAB.fullmatch(category):
            problems.append(f"{key}: category must be lower-kebab-case, got {category!r}")
        elif category not in taxonomy:
            coined[category] += 1
        if entry.get("confidence") not in ("high", "low"):
            problems.append(f"{key}: confidence must be 'high' or 'low'")
        if not isinstance(entry.get("regression"), bool):
            problems.append(f"{key}: regression must be true or false")
        cause = entry.get("cause")
        if not isinstance(cause, str) or not cause.strip():
            problems.append(f"{key}: cause must be a non-empty line")

    for category, count in sorted(coined.items()):
        if count < min_new:
            problems.append(f"unknown category '{category}' on {count} bug(s): use a seeded "
                            f"category, or coin a new one only for >= {min_new} bugs")
    if problems:
        raise AssignmentError(problems)
    return sorted(coined)


def _merge(bugs, rows, assignments):
    evidence = {r["key"]: r for r in rows}
    merged = []
    for b in bugs:
        entry = assignments[b["key"]]
        row = evidence.get(b["key"]) or {}
        merged.append({**b, "category": entry["category"], "confidence": entry["confidence"],
                       "regression": entry["regression"],
                       "cause": entry["cause"].strip()[:CAUSE_LIMIT],
                       "evidence": row.get("evidence") or "jira",
                       "pr_url": row.get("pr_url")})
    return merged


def _examples(members):
    newest = sorted(members, key=lambda b: (b["created"], b["key"]), reverse=True)
    return sorted(newest, key=lambda b: b["evidence"] != "pr")[:EXAMPLES]


def ranking(bugs, taxonomy, new=()):
    total = len(bugs)
    groups = {}
    for b in bugs:
        groups.setdefault(b["category"], []).append(b)
    rows = []
    for category, members in groups.items():
        count = len(members)
        regressions = sum(1 for b in members if b["regression"])
        rows.append({
            "category": category,
            "definition": taxonomy.get(category, NEW_DEFINITION),
            "is_new": category in set(new),
            "count": count,
            "share": count / total if total else 0.0,
            "areas": {"portal": sum(1 for b in members if b["area"] == "portal"),
                      "core": sum(1 for b in members if b["area"] == "core"),
                      "none": sum(1 for b in members if b["area"] is None)},
            "regression": regressions,
            "regression_rate": regressions / count,
            "evidence": {"pr": sum(1 for b in members if b["evidence"] == "pr"),
                         "jira": sum(1 for b in members if b["evidence"] != "pr")},
            "low_confidence": sum(1 for b in members if b["confidence"] == "low"),
            "examples": _examples(members),
        })
    rows.sort(key=lambda r: (r["category"] == INSUFFICIENT, -r["count"], r["category"]))
    return rows


def build_model(document, rows, assignments, taxonomy, new=()):
    bugs = _merge(document["bugs"], rows, assignments)
    views = {"all": ranking(bugs, taxonomy, new)}
    for area in AREA_ORDER:
        if area in areas_in_scope(document["repo"]):
            views[area] = ranking([b for b in bugs if b["area"] == area], taxonomy, new)
    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "total": len(bugs),
        "evidence": {"pr": sum(1 for b in bugs if b["evidence"] == "pr"),
                     "jira": sum(1 for b in bugs if b["evidence"] != "pr")},
        "regression": sum(1 for b in bugs if b["regression"]),
        "new_categories": list(new),
        "views": views,
        "insufficient": sorted((b for b in bugs if b["category"] == INSUFFICIENT),
                               key=lambda b: (b["created"], b["key"]), reverse=True),
        "no_area": [b for b in bugs if b["area"] is None],
        "bugs": bugs,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `50 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_report.py plugins/common/oc-bug-root-causes/tests/test_rc_report.py
git commit -m "oc-bug-root-causes: validate assignment parts and build the ranking model

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Markdown / CSV / HTML rendering and the report CLI — `rc_report.py`

**Files:**
- Modify: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_report.py` (append)
- Test: `plugins/common/oc-bug-root-causes/tests/test_rc_report.py` (append)

**Interfaces:**
- Consumes: Task 6's model and functions.
- Produces: `render_markdown(model) -> str`; `CSV_HEADER`; `render_csv_rows(model) -> list[list[str]]`; `render_html(model, today=None) -> str`; `main(argv=None) -> int` with args `--bugs --classify --assignments (nargs="+") --taxonomy --out --csv --model`; exit `2` on `AssignmentError`.

- [ ] **Step 1: Write the failing tests** (append to `test_rc_report.py`)

```python
import json


def sample_model():
    bugs = [bug("A-1", "portal", summary="Grid | broken <script>"), bug("A-2", "core"),
            bug("A-3", None)]
    asg = {"A-1": a("null-handling", reg=True, cause="guard missing on `cfg`"),
           "A-2": a("brand-new"), "A-3": a("insufficient-evidence")}
    rows = [{"key": "A-1", "evidence": "pr", "pr_url": "https://bb/pr/1"},
            {"key": "A-2", "evidence": "jira", "pr_url": None},
            {"key": "A-3", "evidence": "jira", "pr_url": None}]
    return model_for(bugs, asg, rows, new=["brand-new"])


def test_markdown_header_ranking_and_sections():
    md = rr.render_markdown(sample_model())
    assert md.startswith("# Development-issue root causes")
    assert "**3** bugs · PR evidence **1** · Jira-only **2** · regressions **1**" in md
    assert "| `null-handling` | 1 | 33.3% | 1 | 0 | 0 | 1 (100%) | 1 / 0 | 0 |" in md
    assert "`brand-new` **(new)**" in md
    assert "## Ranking — Frontend" in md and "## Ranking — Backend" in md
    assert "Grid \\| broken" in md
    assert "[PR](https://bb/pr/1)" in md
    assert "## Insufficient evidence — 1 bugs" in md
    assert "## No resolvable area — 1 bugs" in md
    assert "## New categories" in md


def test_single_area_markdown_shows_one_ranking():
    md = rr.render_markdown(model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal"))
    assert md.count("## Ranking") == 1


def test_csv_has_one_row_per_bug():
    rows = rr.render_csv_rows(sample_model())
    assert rows[0] == rr.CSV_HEADER
    assert len(rows) == 4
    first = dict(zip(rows[0], rows[1]))
    assert first["key"] == "A-1" and first["regression"] == "yes"
    assert first["evidence"] == "pr" and first["pr_url"] == "https://bb/pr/1"
    assert first["cause"] == "guard missing on `cfg`"
    assert dict(zip(rows[0], rows[3]))["area"] == ""


def test_html_escapes_content_and_offers_area_tabs():
    page = rr.render_html(sample_model(), today="2026-09-29")
    assert "Grid | broken &lt;script&gt;" in page
    assert 'data-view="portal"' in page and 'data-view="core"' in page
    assert 'class="tab"' in page
    assert "prefers-color-scheme:dark" in page


def test_single_area_html_has_no_tabs():
    page = rr.render_html(model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal"),
                          today="2026-09-29")
    assert 'class="tab"' not in page


def write_run(tmp_path, parts):
    (tmp_path / "bugs.json").write_text(json.dumps({
        "repo": "both", "window": {"since": "2026-09-01", "until": "2026-10-01"},
        "projects": ["INTRD"], "bugs": [bug("A-1"), bug("A-2", "core")]}))
    (tmp_path / "ci.jsonl").write_text(
        json.dumps({"key": "A-1", "evidence": "jira", "pr_url": None}) + "\n"
        + json.dumps({"key": "A-2", "evidence": "jira", "pr_url": None}) + "\n")
    (tmp_path / "tax.md").write_text(TAXONOMY_MD)
    paths = []
    for i, part in enumerate(parts, 1):
        p = tmp_path / f"{i:03d}.json"
        p.write_text(json.dumps(part))
        paths.append(str(p))
    return (["--bugs", str(tmp_path / "bugs.json"), "--classify", str(tmp_path / "ci.jsonl"),
             "--assignments", *paths, "--taxonomy", str(tmp_path / "tax.md"),
             "--out", str(tmp_path / "docs" / "r.html"), "--csv", str(tmp_path / "docs" / "r.csv"),
             "--model", str(tmp_path / "model.json")])


def test_main_merges_parts_and_writes_every_report(tmp_path, capsys):
    args = write_run(tmp_path, [{"A-1": a("null-handling")}, {"A-2": a("api-contract")}])
    assert rr.main(args) == 0
    assert (tmp_path / "docs" / "r.html").exists()
    assert (tmp_path / "docs" / "r.csv").exists()
    assert json.loads((tmp_path / "model.json").read_text())["total"] == 2
    assert "# Development-issue root causes" in capsys.readouterr().out


def test_main_exits_2_and_names_the_missing_bug(tmp_path, capsys):
    args = write_run(tmp_path, [{"A-1": a("null-handling")}])
    assert rr.main(args) == 2
    err = capsys.readouterr().err
    assert "A-2" in err and "re-run" in err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_rc_report.py -q`
Expected: FAIL — `AttributeError: module 'rc_report' has no attribute 'render_markdown'`.

- [ ] **Step 3: Append the renderers and CLI to `rc_report.py`**

```python
# --------------------------------------------------------------------- Markdown

AREA_LABEL = {"portal": "Frontend", "core": "Backend", None: "No area"}
VIEW_TITLE = {"all": "all areas", "portal": "Frontend", "core": "Backend"}
RANK_HEAD = ["| Category | Bugs | Share | Frontend | Backend | No area | Regressions "
             "| Evidence (PR / Jira) | Low conf. |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]


def _md(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _shown_views(model):
    """A single-area run has views {all, <area>} holding the same bugs: show one."""
    views = model["views"]
    return [(v, rows) for v, rows in views.items() if v == "all" or len(views) > 2]


def _rank_row(r):
    flag = " **(new)**" if r["is_new"] else ""
    areas = r["areas"]
    return (f"| `{r['category']}`{flag} | {r['count']} | {r['share']:.1%} | "
            f"{areas['portal']} | {areas['core']} | {areas['none']} | "
            f"{r['regression']} ({r['regression_rate']:.0%}) | "
            f"{r['evidence']['pr']} / {r['evidence']['jira']} | {r['low_confidence']} |")


def _example_line(b):
    parts = [f"[{b['key']}]({b['url']})", AREA_LABEL[b["area"]]]
    if b["regression"]:
        parts.append("regression")
    if b["confidence"] == "low":
        parts.append("low confidence")
    if b["pr_url"]:
        parts.append(f"[PR]({b['pr_url']})")
    return f"- {' · '.join(parts)} — {_md(b['cause'])} — _{_md(b['summary'])}_"


def render_markdown(model):
    w, ev = model["window"], model["evidence"]
    out = ["# Development-issue root causes", "",
           f"**{', '.join(model['projects'])}** · \"Development issue\" bugs created "
           f"`{w['since']}` → `{w['until']}` (exclusive) · repo **{model['repo']}**", "",
           f"**{model['total']}** bugs · PR evidence **{ev['pr']}** · Jira-only "
           f"**{ev['jira']}** · regressions **{model['regression']}** · insufficient "
           f"evidence **{len(model['insufficient'])}**", ""]

    for view, rows in _shown_views(model):
        out += [f"## Ranking — {VIEW_TITLE[view]}", ""]
        out += (RANK_HEAD + [_rank_row(r) for r in rows]) if rows else ["_No bugs._"]
        out.append("")

    out += ["## Categories", ""]
    for r in model["views"]["all"]:
        if r["category"] == INSUFFICIENT:
            continue
        out += [f"### `{r['category']}` — {r['count']} bugs", "", f"_{_md(r['definition'])}_", ""]
        out += [_example_line(b) for b in r["examples"]]
        out.append("")

    if model["insufficient"]:
        out += [f"## Insufficient evidence — {len(model['insufficient'])} bugs", "",
                "_Neither Jira nor the PR shows the mistake. Filling in these tickets makes "
                "the next run sharper._", ""]
        out += [f"- [{b['key']}]({b['url']}) · {AREA_LABEL[b['area']]} · {_md(b['summary'])}"
                for b in model["insufficient"]]
        out.append("")

    if model["no_area"]:
        out += [f"## No resolvable area — {len(model['no_area'])} bugs", "",
                "_No Jira component and no leading `[front]`/`[back]` tag. They are ranked "
                "under \"No area\"._", ""]
        out += [f"- [{b['key']}]({b['url']}) · `{b['category']}` · {_md(b['summary'])}"
                for b in model["no_area"]]
        out.append("")

    if model["new_categories"]:
        out += ["## New categories", "",
                "Coined in this run — add them to `references/dev-root-causes.md` to keep them: "
                + ", ".join(f"`{c}`" for c in model["new_categories"]), ""]
    return "\n".join(out)


# -------------------------------------------------------------------------- CSV

CSV_HEADER = ["key", "area", "category", "confidence", "regression", "evidence", "pr_url",
              "cause", "status", "created", "assignee", "summary", "url"]


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]
    for b in model["bugs"]:
        rows.append([b["key"], b["area"] or "", b["category"], b["confidence"],
                     "yes" if b["regression"] else "no", b["evidence"], b["pr_url"] or "",
                     b["cause"], b.get("status") or "", b.get("created") or "",
                     b.get("assignee") or "", b.get("summary") or "", b.get("url") or ""])
    return rows


# ------------------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f7f7f8;--fg:#1d1d1f;--mut:#6b6b72;--line:#e3e3e6;--card:#fff;--accent:#2f6fd0;
 --newbg:#fde7c7;--pill:#eef1f5}
*{box-sizing:border-box}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
h3{font-size:14px;margin:20px 0 4px}
.meta,.def{color:var(--mut)}.meta{margin-bottom:18px}.def{margin:0 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:12px 16px;margin-bottom:18px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.sub{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.new{background:var(--newbg);border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.pill{background:var(--pill);border-radius:4px;padding:1px 6px;font-size:12px;color:var(--mut)}
.tabs{display:flex;gap:6px;margin:18px 0 12px;flex-wrap:wrap}
.tab{font:inherit;padding:7px 14px;border:1px solid var(--line);border-radius:8px;
 cursor:pointer;background:var(--card);color:var(--fg)}
.tab[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--mut);font-style:italic}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ededf0;--mut:#9a9aa3;
 --line:#2c2c31;--card:#1c1c20;--accent:#6ea8ff;--newbg:#5a4420;--pill:#26262b}}
"""

TAB_JS = """
document.querySelectorAll('.tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(t){
      t.setAttribute('aria-selected', String(t === tab));
    });
    document.querySelectorAll('section[data-view]').forEach(function(s){
      s.hidden = s.dataset.view !== tab.dataset.view;
    });
  });
});
"""


def _e(value):
    return html_mod.escape(str(value if value is not None else ""))


def _link(url, text):
    return f'<a href="{_e(url)}">{_e(text)}</a>' if url else "—"


def _rank_html(rows):
    if not rows:
        return '<p class="empty">No bugs.</p>'
    head = ('<tr><th>Category</th><th class="n">Bugs</th><th class="n">Share</th>'
            '<th class="n">Frontend</th><th class="n">Backend</th><th class="n">No area</th>'
            '<th class="n">Regressions</th><th class="n">PR / Jira</th>'
            '<th class="n">Low conf.</th></tr>')
    body = []
    for r in rows:
        flag = '<span class="new">new</span>' if r["is_new"] else ""
        a = r["areas"]
        body.append(
            f'<tr><td><span class="sub">{_e(r["category"])}</span>{flag}</td>'
            f'<td class="n">{r["count"]}</td><td class="n">{r["share"]:.1%}</td>'
            f'<td class="n">{a["portal"]}</td><td class="n">{a["core"]}</td>'
            f'<td class="n">{a["none"]}</td>'
            f'<td class="n">{r["regression"]} ({r["regression_rate"]:.0%})</td>'
            f'<td class="n">{r["evidence"]["pr"]} / {r["evidence"]["jira"]}</td>'
            f'<td class="n">{r["low_confidence"]}</td></tr>')
    return '<div class="card"><table>' + head + "".join(body) + "</table></div>"


def _bug_table(bugs, with_cause):
    head = "<tr><th>Key</th><th>Area</th>"
    head += "<th>Cause</th><th>PR</th>" if with_cause else ""
    head += "<th>Summary</th></tr>"
    body = []
    for b in bugs:
        tags = " ".join(f'<span class="pill">{t}</span>' for t, on in
                        (("regression", b["regression"]), ("low", b["confidence"] == "low")) if on)
        row = f"<tr><td>{_link(b['url'], b['key'])}</td><td>{_e(AREA_LABEL[b['area']])}</td>"
        if with_cause:
            row += f"<td>{_e(b['cause'])} {tags}</td><td>{_link(b['pr_url'], 'PR')}</td>"
        row += f"<td>{_e(b['summary'])}</td></tr>"
        body.append(row)
    return '<div class="card"><table>' + head + "".join(body) + "</table></div>"


def render_html(model, today=None):
    today = today or date.today().isoformat()
    w, ev = model["window"], model["evidence"]
    title = f"Development-issue root causes — {w['since']} → {w['until']}"
    views = _shown_views(model)

    body = [f"<h1>{_e(title)}</h1>",
            f'<p class="meta">{_e(", ".join(model["projects"]))} · repo {_e(model["repo"])} · '
            f'{model["total"]} bugs · PR evidence {ev["pr"]} · Jira-only {ev["jira"]} · '
            f'regressions {model["regression"]} · insufficient evidence '
            f'{len(model["insufficient"])} · generated {_e(today)}</p>']
    if len(views) > 1:
        body.append('<div class="tabs" role="tablist">' + "".join(
            f'<button class="tab" data-view="{_e(v)}" role="tab" '
            f'aria-selected="{"true" if i == 0 else "false"}">{_e(VIEW_TITLE[v])}</button>'
            for i, (v, _) in enumerate(views)) + "</div>")
    for i, (v, rows) in enumerate(views):
        hidden = " hidden" if i else ""
        body.append(f'<section data-view="{_e(v)}"{hidden}>{_rank_html(rows)}</section>')

    body.append("<h2>Categories</h2>")
    for r in model["views"]["all"]:
        if r["category"] == INSUFFICIENT:
            continue
        flag = '<span class="new">new</span>' if r["is_new"] else ""
        body.append(f'<h3><span class="sub">{_e(r["category"])}</span>{flag} — '
                    f'{r["count"]} bugs</h3><p class="def">{_e(r["definition"])}</p>'
                    + _bug_table(r["examples"], with_cause=True))

    if model["insufficient"]:
        body.append(f'<h2>Insufficient evidence — {len(model["insufficient"])} bugs</h2>'
                    '<p class="meta">Neither Jira nor the PR shows the mistake.</p>'
                    + _bug_table(model["insufficient"], with_cause=False))
    if model["no_area"]:
        body.append(f'<h2>No resolvable area — {len(model["no_area"])} bugs</h2>'
                    + _bug_table(model["no_area"], with_cause=True))

    script = f"<script>{TAB_JS}</script>" if len(views) > 1 else ""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Bug root causes</title><style>{CSS}</style></head><body><main>"
            + "".join(body) + "</main>" + script + "</body></html>\n")


# -------------------------------------------------------------------------- CLI

def _read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank developer root causes and report.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--classify", required=True)
    parser.add_argument("--assignments", required=True, nargs="+",
                        help="one JSON part per classification batch")
    parser.add_argument("--taxonomy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        document = json.load(handle)
    rows = _read_jsonl(args.classify)
    parts = []
    for path in args.assignments:
        with open(path, encoding="utf-8") as handle:
            parts.append(json.load(handle))
    taxonomy = load_taxonomy(args.taxonomy)

    try:
        assignments = merge_assignments(parts)
        new = validate([b["key"] for b in document["bugs"]], assignments, taxonomy)
    except AssignmentError as ex:
        for problem in ex.problems:
            sys.stderr.write(f"{problem}\n")
        sys.stderr.write("Fix the assignments for these bugs and re-run.\n")
        return 2

    model = build_model(document, rows, assignments, taxonomy, new)
    for path in (args.out, args.csv, args.model):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q`
Expected: `57 passed`

- [ ] **Step 5: Commit**

```bash
git add plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/scripts/rc_report.py plugins/common/oc-bug-root-causes/tests/test_rc_report.py
git commit -m "oc-bug-root-causes: Markdown, CSV and HTML reports

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: SKILL.md, CLAUDE.md, and a live read-only run

**Files:**
- Create: `plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/SKILL.md`
- Modify: `plugins/common/oc-bug-root-causes/tests/test_packaging.py` (append)
- Modify: `CLAUDE.md` (Plugin Types list; a new section after `## PR rejection rate`)

**Interfaces:**
- Consumes: every script's CLI (Tasks 3, 5, 7) and the taxonomy (Task 2).

- [ ] **Step 1: Write the failing test** (append to `test_packaging.py`)

```python
def test_skill_md_frontmatter_and_script_references():
    text = (PLUGIN_DIR / "skills" / NAME / "SKILL.md").read_text()
    assert text.startswith(f"---\nname: {NAME}\ndescription: ")
    for script in ("rc_fetch.py", "rc_pr.py", "rc_report.py"):
        assert f"$S/scripts/{script}" in text
    assert "$S/references/dev-root-causes.md" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests/test_packaging.py -q`
Expected: FAIL — `FileNotFoundError` on `SKILL.md`.

- [ ] **Step 3: Write SKILL.md**

`plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes/SKILL.md`:

````markdown
---
name: oc-bug-root-causes
description: Reclassify a period's Jira bugs whose Root cause is "Development issue" onto a granular developer-mistake taxonomy (incomplete-change-propagation, null-handling, dto-payload-mapping, update-overwrites-state, persistence-transaction, ...), judged from each bug's summary, description, last comments and the diff of the PR that fixed it. Regression is a separate flag, not a category. Ranks the categories overall and per area (Frontend/Backend) with share, regression rate, PR-vs-Jira evidence split and a one-line cause per example bug. Prints Markdown and writes a date-stamped HTML + CSV to ./docs/. Read-only. Jira via direct Cloud REST with a mandatory JIRA_API_TOKEN (no Atlassian MCP); Bitbucket via REST with BITBUCKET_ACCESS_TOKEN (optional - without it the run is Jira-only).
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--repo portal|core|both] [--project KEY] [--no-pr] [--out PATH] [--csv PATH]"
---

## Purpose

Jira's **`Root cause`** field (`customfield_10111`) says *that* a bug was the developer's
fault — **"Development issue"**, about half of all INTRD bugs — but not *what kind* of
mistake it was. This command answers that: every such bug in the window gets exactly one
category from `references/dev-root-causes.md`, and the report ranks them, so the team can
see which mistakes recur and where review or tests are missing.

Three properties matter before changing anything:

- **The diff is the main evidence.** For each bug the fixing PR is found on Bitbucket and a
  trimmed diff (tests, lockfiles and i18n removed, 4 KB cap) is read with the Jira text.
  A bug without a PR is classified from Jira alone and the report says so per category.
- **Regression is a flag, not a category.** "Regression" says *when*, not *what*; every bug
  carries `regression: true|false` and the report shows the rate per category.
- **Classification is fanned out.** A month of evidence does not fit one context, so you
  never read the classification input yourself: one sub-agent per batch file does.

This command is **read-only**: no Jira writes, no Bitbucket writes. It needs no git
checkout and runs from any directory.

## Access

- **`JIRA_API_TOKEN`** (+ optional `JIRA_EMAIL`), mandatory — an Atlassian API token from
  *id.atlassian.com → Security → API tokens*. If unset, relay the script's setup message
  and stop. **Do not use the Atlassian MCP** — its search force-includes full
  descriptions and cannot page through a month of bugs.
- **`BITBUCKET_ACCESS_TOKEN`** (+ `BITBUCKET_EMAIL` for an `ATATT…` token), optional. An
  `ATCTT…` token is sent as Bearer, an `ATATT…` token as Basic `email:token`. If unset, the
  run continues Jira-only and the report shows `PR evidence 0`.

Tokens are read from the environment only — never pass them on the command line.

## Arguments

Parse `$ARGUMENTS` — all optional. A bare `/oc-bug-root-causes` analyses the **last 30
days** of **INTRD** bugs across **both** areas.

| Argument | Default | Meaning |
|---|---|---|
| `--since` | 30 days before `--until` | Start of the window, inclusive, on `created` |
| `--until` | tomorrow | End of the window, **exclusive** |
| `--repo` | `both` | `portal` (component Frontend), `core` (Backend) or `both` |
| `--project` | `INTRD` | Jira project(s), comma-separated |
| `--no-pr` | off | Skip Bitbucket; Jira-only evidence |
| `--out` | `./docs/bug-root-causes-<TODAY>.html` | HTML report |
| `--csv` | `./docs/bug-root-causes-<TODAY>.csv` | One row per bug |

`<TODAY>` is `date -u +%Y-%m-%d`. **Echo the resolved window before doing any work**, e.g.
`Analysing INTRD "Development issue" bugs, both areas, 2026-08-30 → 2026-09-30`.

## Task 1 — Fetch

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/oc-bug-root-causes"
RUN="${TMPDIR:-/tmp}/oc-bug-root-causes/[PROJECT]_[REPO]_[SINCE]_[UNTIL]"
mkdir -p "$RUN"

python3 "$S/scripts/rc_fetch.py" --since [SINCE] --until [UNTIL] \
  --project [PROJECT] --repo [REPO] --out-bugs "$RUN/bugs.json"
```

Exit code `3` means no "Development issue" bug in the window: say so and stop. Exit `2`
is a missing token or an inverted window: relay the message and stop. **Never read
`bugs.json`.**

## Task 2 — PR evidence

```bash
python3 "$S/scripts/rc_pr.py" --bugs "$RUN/bugs.json" --run "$RUN" \
  --out-classify "$RUN/classify_input.jsonl" [--no-pr]
```

It prints how many bugs got PR evidence and how many batch files it wrote to
`$RUN/batches/`. Relay every `WARNING:` line. A Bitbucket 401 is not fatal — the run
continues Jira-only — but tell the user, since the message names both auth schemes.
Evidence is cached per bug in `$RUN/pr/`, so a re-run of the same window is cheap.
**Never read `classify_input.jsonl` or the batch files yourself.**

## Task 3 — Classify (fanned out to sub-agents)

`mkdir -p "$RUN/assignments"`, then for each `$RUN/batches/classify.NNN.jsonl` dispatch one
`general-purpose` sub-agent with the Agent tool, **at most 4 at a time**, each with this
prompt (fill in the paths):

> You classify "Development issue" bugs by the developer mistake their fix corrects.
> 1. Read the taxonomy `$S/references/dev-root-causes.md`. Its `## <name>` headings are the
>    only categories you may use, apart from the rule in step 4.
> 2. Read `$RUN/batches/classify.NNN.jsonl`: one bug per line with `summary`, `excerpt`,
>    `comments`, `evidence` (`pr` or `jira`), `pr_title`, `files` and `diff`.
> 3. For **every** line, decide:
>    - `category` — exactly one. Ask "what did the developer get wrong that the fix
>      corrects?", not "where did the user see it?". When a diff is present, trust it over
>      the prose. A symptom ("error toast", "KO") is never a category.
>    - `confidence` — `high` when the diff or a comment shows the mistake, else `low`.
>    - `regression` — `true` when the bug says so (`[REG]`, "Regression", "since INTRD-…",
>      "no longer") or the diff repairs a recent change; otherwise `false`.
>    - `cause` — one line, at most 120 characters, naming the concrete mistake, e.g.
>      "TaxInvoiceAgregate copy constructor omits accountingCode".
>    Use `insufficient-evidence` only when there is no plausible guess at all; a weak guess
>    is that guess with `low` confidence.
> 4. If you believe a mistake genuinely fits no category, you may use a new lower-kebab-case
>    name, and list it with its bugs at the end of your reply. It is kept only if at least 5
>    bugs across the whole run carry it.
> 5. Write `$RUN/assignments/NNN.json`: one JSON object
>    `{"<KEY>": {"category": "...", "confidence": "high|low", "regression": true|false,
>    "cause": "..."}}` covering every key in your batch. Reply only with the number of bugs
>    written and any new category you used.

Wait for every sub-agent. Collect the new categories they report.

## Task 4 — Report

```bash
python3 "$S/scripts/rc_report.py" --bugs "$RUN/bugs.json" \
  --classify "$RUN/classify_input.jsonl" --assignments "$RUN"/assignments/*.json \
  --taxonomy "$S/references/dev-root-causes.md" \
  --out [OUT] --csv [CSV] --model "$RUN/model.json"
```

It prints the Markdown report — relay it, then say where the HTML and CSV landed.

On exit `2` it lists every problem. Fix them and re-run Task 4:

- `no category assigned for: …` — find which batch files hold those keys and re-dispatch
  them (their `assignments/NNN.json` is rewritten).
- `unknown category '…' on N bug(s)` — a sub-agent coined a category too small to keep.
  Re-dispatch the batches holding those bugs, adding to the prompt that this name is not
  allowed.
- `classified differently in two parts` — a stale part file: delete the older one.

When presenting, point out the **evidence split**: a category ranked mostly on Jira-only
evidence is a weaker finding than one ranked on diffs. Name any new category the report
kept so `dev-root-causes.md` can be updated.

## Failure behaviour

| Condition | What to do |
|---|---|
| `JIRA_API_TOKEN` unset | Relay the setup message and stop. Never fall back to the MCP |
| `must be before` | The dates are inverted or equal. Ask for corrected dates and stop |
| Exit 3 from `rc_fetch.py` | No "Development issue" bug in the window. Report it and stop |
| `BITBUCKET_ACCESS_TOKEN` unset | The run continues Jira-only; say so in the summary |
| Bitbucket 401 warning | Continue; tell the user the credential was rejected and relay the message |
| `WARNING: PR lookup failed for …` | That bug is Jira-only; relay it |
| Exit 2 from `rc_report.py` | Fix as described in Task 4 and re-run it |
````

- [ ] **Step 4: Update CLAUDE.md**

In the **Plugin Types** bullet 1 list, after `` `/oc-bug-clusters`, `` insert `` `/oc-bug-root-causes`, ``.

Insert this section directly before `## MCP Servers Requiring Environment Variables`:

```markdown
## Development root causes (`/oc-bug-root-causes`)

`plugins/common/oc-bug-root-causes` takes a period's bugs whose Jira **`Root cause`**
(`customfield_10111`) is **"Development issue"** and reclassifies each onto a granular
developer-mistake taxonomy (`references/dev-root-causes.md`), judged from the Jira text
and the diff of the PR that fixed the bug. It is **read-only** and ships real Python files
with a pytest suite:

```bash
python3 -m pytest plugins/common/oc-bug-root-causes/tests -q
```

Five things are not obvious from the code:

- **Three scripts are copies, not imports.** `jira_client.py` and `bug_fetch.py` come from
  `oc-bug-clusters`, `bitbucket_client.py` from `oc-pr-rejection-rate`, because
  `${CLAUDE_PLUGIN_ROOT}` cannot reach a sibling plugin in an install. A test asserts they
  are byte-identical: change the original, then re-copy.
- **One taxonomy for both areas, and regression is a flag.** The point is to compare
  Frontend and Backend on the same axis, and a regression can be any kind of mistake.
- **The diff redirect is followed by hand.** `…/diff` answers 302 to a signed URL on another
  host; `urllib` would forward `Authorization` there, so `rc_pr.py` drops it on a host
  change. The per-file list is computed from the diff, not a `…/diffstat` call, to keep a
  month near 600 requests.
- **Classification is fanned out to sub-agents, one per 30-bug batch file.** A month of
  diffs does not fit one context. `rc_report.py` merges the parts and refuses a missing
  key, a key outside the run, a key classified twice, or a coined category under 5 bugs.
- **`insufficient-evidence` is counted and listed, never hidden** — it is the list of
  tickets whose description or PR should be improved.
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest plugins/common/oc-bug-root-causes/tests -q && python3 -m pytest plugins/common/oc-bug-clusters/tests plugins/common/oc-pr-rejection-rate/tests -q`
Expected: `58 passed`, and the two sibling suites still pass unchanged.

- [ ] **Step 6: Live read-only smoke run on a short window**

```bash
S=plugins/common/oc-bug-root-causes/skills/oc-bug-root-causes
RUN=$(mktemp -d)
python3 $S/scripts/rc_fetch.py --since 2026-09-01 --until 2026-09-15 --out-bugs $RUN/bugs.json
python3 $S/scripts/rc_pr.py --bugs $RUN/bugs.json --run $RUN --out-classify $RUN/classify_input.jsonl
python3 - "$RUN" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1] + "/classify_input.jsonl")]
print(len(rows), "bugs;", sum(r["evidence"] == "pr" for r in rows), "with PR evidence")
for r in [r for r in rows if r["evidence"] == "pr"][:3]:
    print(r["key"], r["pr_url"], len(r["diff"].encode()), "bytes;", r["files"][:3])
EOF
```

Expected: `rc_fetch.py` prints a non-zero `kept`; `rc_pr.py` reports PR evidence for most bugs; each sampled diff is ≤ 4096 bytes plus the truncation marker, and each `pr_url` opens a PR whose title or branch carries that exact key. If PR evidence is 0 for every bug, check the `q` query against one known key before going further — the combined `title ~ … OR source.branch.name ~ …` query is the one piece not yet verified live.

Then write a hand-made `$RUN/assignments/001.json` for every key (any seeded category), run `rc_report.py` as in SKILL.md Task 4 with `--out $RUN/r.html --csv $RUN/r.csv`, and open the HTML to check the tabs, the dark theme and the tables at phone width.

- [ ] **Step 7: Commit**

```bash
git add plugins/common/oc-bug-root-causes CLAUDE.md
git commit -m "oc-bug-root-causes: skill orchestration and repo docs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

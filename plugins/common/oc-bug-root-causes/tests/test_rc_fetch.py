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

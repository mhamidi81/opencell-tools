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


def test_retries_429_then_succeeds_on_get(env):
    """Only GET is retried blind -- see test_a_post_503_is_not_retried for why."""
    slept = []
    opener = FakeOpener([http_error(429), {"ok": True}])
    client = jc.JiraClient(opener=opener, env=env, sleep=slept.append)

    assert client.get("/x") == {"ok": True}
    assert slept == [2]


def test_a_post_503_is_not_retried(env):
    """A 429/503 on POST /rest/api/3/issue may arrive AFTER Jira committed the
    create -- retrying it blind would duplicate the issue. POST must fail on the
    first attempt instead."""
    slept = []
    opener = FakeOpener([http_error(503)])
    client = jc.JiraClient(opener=opener, env=env, sleep=slept.append)

    with pytest.raises(jc.JiraError, match="503"):
        client.post("/x", {})
    assert slept == []


def test_post_issue_503_is_not_retried_one_attempt(env):
    """Same rule pinned to the real create endpoint: a 503 there must raise after
    exactly one attempt, never duplicating the issue."""
    opener = FakeOpener([http_error(503)])
    client = jc.JiraClient(opener=opener, env=env, sleep=lambda _s: None)

    with pytest.raises(jc.JiraError, match="503"):
        client.post("/rest/api/3/issue", {})
    assert len(opener.requests) == 1


def test_search_retries_a_transient_429_then_returns_all_pages(env):
    """search() posts to /rest/api/3/search/jql, which is a read despite using
    POST (the JQL body can exceed a GET's URL length). Retryability must follow
    idempotency, not the HTTP method -- a bare method == 'GET' check disables
    retry here and breaks the paginated fetch path on the very first transient
    429/503 it hits."""
    slept = []
    opener = FakeOpener([
        http_error(429),
        {"issues": [{"key": "A-1"}], "nextPageToken": "p2", "isLast": False},
        {"issues": [{"key": "A-2"}], "isLast": True},
    ])
    client = jc.JiraClient(opener=opener, env=env, sleep=slept.append)

    keys = [i["key"] for i in client.search("project = A", ["summary"])]

    assert keys == ["A-1", "A-2"]
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

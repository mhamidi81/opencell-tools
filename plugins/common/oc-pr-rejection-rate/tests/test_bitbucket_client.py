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


def test_an_access_token_uses_bearer_with_no_email(env):
    """ATCTT... is a repository/workspace Access Token. Sent as Basic it returns 401,
    so the scheme must follow the token's type, not the presence of an email."""
    env["BITBUCKET_ACCESS_TOKEN"] = "ATCTT" + "x" * 40
    header = bc.auth_header(env)
    assert header == "Bearer " + env["BITBUCKET_ACCESS_TOKEN"]


def test_an_access_token_uses_bearer_even_when_an_email_is_exported(env):
    """BITBUCKET_EMAIL is commonly exported for other tooling; keying the scheme off
    it rather than off the token picks Basic and 401s against an ATCTT token."""
    env["BITBUCKET_ACCESS_TOKEN"] = "ATCTT" + "y" * 40
    env["BITBUCKET_EMAIL"] = "dev@opencellsoft.com"
    assert bc.auth_header(env).startswith("Bearer ")


def test_an_api_token_still_uses_basic(env):
    env["BITBUCKET_ACCESS_TOKEN"] = "ATATT" + "z" * 40
    header = bc.auth_header(env)
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
    assert decoded == "dev@opencellsoft.com:ATATT" + "z" * 40


def test_an_api_token_without_an_email_says_which_form_needs_one(env):
    env["BITBUCKET_ACCESS_TOKEN"] = "ATATT" + "z" * 40
    env.pop("BITBUCKET_EMAIL")
    with pytest.raises(bc.MissingToken) as ex:
        bc.auth_header(env)
    assert "BITBUCKET_EMAIL" in str(ex.value)


def test_an_access_token_needs_no_email_at_all(env):
    env["BITBUCKET_ACCESS_TOKEN"] = "ATCTT" + "w" * 40
    env.pop("BITBUCKET_EMAIL")
    assert bc.auth_header(env).startswith("Bearer ")


def test_the_client_sends_the_bearer_header_it_built(env):
    env["BITBUCKET_ACCESS_TOKEN"] = "ATCTT" + "v" * 40
    api, opener = client([{"ok": True}], env)
    api.get("/x")
    assert opener.requests[0].get_header("Authorization").startswith("Bearer ")

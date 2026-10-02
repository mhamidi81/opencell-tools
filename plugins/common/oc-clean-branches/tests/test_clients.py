"""Transport: auth scheme per token prefix, and the DELETE path."""
from conftest import FakeOpener

import bitbucket_client as bc


def test_atctt_token_is_sent_as_bearer_even_with_an_email():
    env = {"BITBUCKET_ACCESS_TOKEN": "ATCTTabc", "BITBUCKET_EMAIL": "x@y"}
    assert bc.auth_header(env) == "Bearer ATCTTabc"


def test_atatt_token_is_sent_as_basic(env):
    assert bc.auth_header(env).startswith("Basic ")


def test_delete_branch_keeps_slashes_raw_and_uses_delete(env):
    opener = FakeOpener([None])
    client = bc.BitbucketClient(opener=opener, env=env, sleep=lambda _s: None)
    client.delete_branch("ws", "repo", "fix/INTRD-1 x")
    request = opener.requests[0]
    assert request.get_method() == "DELETE"
    assert request.full_url.endswith("/repositories/ws/repo/refs/branches/fix/INTRD-1%20x")

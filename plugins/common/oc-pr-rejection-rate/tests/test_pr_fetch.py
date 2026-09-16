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
    api, _ = client([listing] + [http_error(500)], env)
    result = pf.fetch_repo(api, "opencellsoft", "opencell-core",
                           "2026-09-10", "2026-09-17", workers=1)
    pr = result["pull_requests"][0]
    assert pr["activity"] == []
    assert pr["warnings"] and "500" in pr["warnings"][0]


def test_fetch_activity_returns_the_feed_oldest_first(env):
    """Bitbucket pages activity newest-first. pr_classify.draft_states reads the
    oldest entry as the PR's initial draft state, so an unsorted feed inverts R3:
    a PR pushed back to draft reads as one merely opened as a draft."""
    newest_first = {"values": [
        {"update": {"date": "2026-09-12T09:00:00+00:00", "draft": True}},
        {"update": {"date": "2026-09-10T09:00:00+00:00", "draft": False}},
    ]}
    api, _ = client([newest_first], env)
    feed = pf.fetch_activity(api, "opencellsoft", "opencell-core", 7)
    assert [e["update"]["date"] for e in feed] == [
        "2026-09-10T09:00:00+00:00", "2026-09-12T09:00:00+00:00"]


def test_sort_oldest_first_puts_undated_entries_last_and_is_stable():
    dated = {"update": {"date": "2026-09-10T09:00:00+00:00"}}
    undated_a, undated_b = {"comment": {}}, {"comment": {"date": None}}
    assert pf.sort_oldest_first([undated_a, dated, undated_b]) == [dated, undated_a, undated_b]


def test_sort_oldest_first_compares_instants_not_strings():
    """A single non-UTC offset reverses the pair, and a reversed feed inverts R3."""
    later_utc = {"update": {"date": "2026-09-11T10:00:00+00:00", "draft": True}}
    earlier_offset = {"update": {"date": "2026-09-11T11:00:00+02:00", "draft": False}}  # 09:00Z
    assert pf.sort_oldest_first([later_utc, earlier_offset]) == [earlier_offset, later_utc]


def test_sort_oldest_first_accepts_a_z_suffix():
    z = {"update": {"date": "2026-09-11T08:00:00Z"}}
    offset = {"update": {"date": "2026-09-11T09:00:00+00:00"}}
    assert pf.sort_oldest_first([offset, z]) == [z, offset]


def test_sort_oldest_first_puts_an_unparseable_date_last_without_raising():
    good = {"update": {"date": "2026-09-11T09:00:00+00:00"}}
    bad = {"update": {"date": "not a date"}}
    assert pf.sort_oldest_first([bad, good]) == [good, bad]


def test_entry_date_ignores_the_pull_request_metadata_sibling():
    """Live entries are {"<kind>": {...}, "pull_request": {...}} and the sibling comes
    first in key order, so it must be skipped rather than merely happen to lack a date."""
    entry = {"pull_request": {"date": "2000-01-01T00:00:00+00:00", "draft": True},
             "update": {"date": "2026-09-15T09:08:12+00:00", "draft": False}}
    assert pf._entry_date(entry) == "2026-09-15T09:08:12+00:00"


def test_entry_date_accepts_created_on_used_by_comments():
    """Comments date themselves with created_on; without this they sort as undated."""
    entry = {"comment": {"created_on": "2026-09-15T10:00:00+00:00"}}
    assert pf._entry_date(entry) == "2026-09-15T10:00:00+00:00"


def test_a_comment_sorts_chronologically_among_updates():
    early = {"update": {"date": "2026-09-15T08:00:00+00:00"}}
    comment = {"comment": {"created_on": "2026-09-15T09:00:00+00:00"}}
    late = {"update": {"date": "2026-09-15T10:00:00+00:00"}}
    assert pf.sort_oldest_first([late, early, comment]) == [early, comment, late]

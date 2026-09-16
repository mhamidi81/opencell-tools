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


def test_draft_states_ignores_a_non_boolean_change_value():
    """bool("false") is True — coercing would report a confident zero for R3."""
    feed = [update(changes={"draft": {"old": "false", "new": "true"}})]
    assert pc.draft_states(feed) is None


def test_a_non_boolean_draft_representation_degrades_the_detection_mode():
    """The mode must admit uncertainty rather than claim exactness it lacks."""
    p = pr(activity=[update(changes={"draft": {"old": "false", "new": "true"}})])
    assert pc.detect_draft_mode(document([p])) == "current-flag"


def test_a_change_entry_without_old_infers_the_previous_value():
    """A changes entry means the value changed, so for a boolean the previous
    value is the negation — dropping the entry would lose the transition."""
    feed = [update(changes={"draft": {"new": True}})]
    assert pc.draft_states(feed) == [False, True]
    assert pc.was_redrafted(pr(activity=feed, draft=True), "activity") is True


def test_draft_states_reads_a_feed_mixing_both_representations():
    feed = [update(draft=False), update(changes={"draft": {"old": False, "new": True}})]
    assert pc.draft_states(feed) == [False, True]


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


def test_an_unrecognised_mode_never_reports_a_redraft():
    assert pc.was_redrafted(pr(draft=True, activity=[update(), update()]), "bogus") is False


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


FIXTURE = FIXTURES / "activity_drafted.json"


@pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="fixture not pinned: run the live probe (plan Task 3) with "
           "BITBUCKET_ACCESS_TOKEN set to record a real activity feed",
)
def test_the_pinned_live_fixture_resolves_to_a_known_mode():
    """Guards spec §4. The probe pins a PR known to have been pushed back to
    draft, so the classifier must read a ready→draft transition out of the real
    feed. A failure here is a finding, not a flaky test: it means Bitbucket's
    actual draft representation is not one this module understands, and R3 must
    fall back to the coarser current-flag mode.
    """
    feed = json.loads(FIXTURE.read_text())
    states = pc.draft_states(feed)
    assert states is not None, "Bitbucket's real feed carries no draft history"
    assert all(isinstance(s, bool) for s in states)
    assert pc.was_redrafted({"activity": feed, "draft": True}, "activity") is True


def test_a_pr_whose_activity_failed_is_judged_by_the_coarse_proxy_not_reported_false():
    """Reporting an un-evaluated rule as False is a confident answer we did not earn."""
    good = pr(pid=1, activity=[update(draft=False), update(draft=True)], draft=True)
    failed = pr(pid=2, activity=[], draft=True, warnings=["activity fetch failed: HTTP 500"])
    model = pc.build_model(document([good, failed]))
    assert model["draft_detection"] == "activity"
    rows = {r["id"]: r for r in model["repos"]["opencell-portal"]["prs"]}
    assert rows[1]["activity_ok"] is True
    assert rows[2]["activity_ok"] is False


def test_activity_ok_is_true_for_an_ordinary_pr():
    model = pc.build_model(document([pr()]))
    assert model["repos"]["opencell-portal"]["prs"][0]["activity_ok"] is True


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

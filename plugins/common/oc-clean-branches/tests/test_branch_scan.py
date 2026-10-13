"""Scanner: every guard, and the fail-safe paths. No network."""
from datetime import datetime, timezone

import pytest
from conftest import FakeBitbucket, FakeJira

import bitbucket_client
import branch_scan

BASE = "/repositories/ws/repo"
BEFORE = datetime(2026, 6, 1, tzinfo=timezone.utc)
RECENT = datetime(2026, 9, 1, tzinfo=timezone.utc)
OLD = "2026-01-10T10:00:00+00:00"


def branch(name, date=OLD, sha=None):
    return {"name": name, "target": {"hash": sha or f"h-{name}", "date": date,
                                     "author": {"raw": "Dev One <d@x>"}}}


def issue(key, kind="Bug", status="Closed"):
    return {"key": key, "fields": {"issuetype": {"name": kind}, "status": {"name": status}}}


def make(branches, open_prs=(), restrictions=(), unmerged=(), merged_into=None, model=None):
    def commits(params):
        return {"values": [{"hash": "x"}] if params["include"] in unmerged else []}

    def merged(params):
        name = params["q"].split('"')[1]
        dest = (merged_into or {}).get(name)
        return {"values": [{"destination": {"branch": {"name": dest}}}] if dest else []}

    return FakeBitbucket({
        BASE: {"mainbranch": {"name": "master"}},
        f"{BASE}/branching-model": model or {"development": {"branch": {"name": "develop"}}},
        f"{BASE}/branch-restrictions": list(restrictions),
        f"{BASE}/refs/branches": [branch("master"), branch("develop")] + branches,
        f"{BASE}/pullrequests": lambda p: (open_prs if p.get("state") == "OPEN" else merged(p)),
        f"{BASE}/commits": commits,
    })


def scan(bb, jira):
    return branch_scan.scan_repo(bb, jira, "ws", "repo", BEFORE, RECENT)


def reasons(result):
    return {r["name"]: r["rule"] for r in result["excluded"]}


def test_happy_path_deletes_an_old_merged_bug_branch():
    bb = make([branch("fix/INTRD-1")])
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert [r["name"] for r in result["deletable"]] == ["fix/INTRD-1"]
    assert result["deletable"][0]["target"] == "develop"


def test_branches_after_the_date_are_not_even_candidates():
    bb = make([branch("fix/INTRD-1", date="2026-07-01T00:00:00+00:00")])
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert result["deletable"] == []
    assert "fix/INTRD-1" not in reasons(result)


def test_r1_structural_and_restricted_branches_are_kept():
    bb = make([branch("release/15"), branch("19.0.x"), branch("hotfix/INTRD-2")],
              restrictions=[{"branch_match_kind": "glob", "pattern": "hotfix/*"}])
    result = scan(bb, FakeJira({"INTRD-2": issue("INTRD-2")}))
    assert reasons(result) == {"master": "R1", "develop": "R1", "release/15": "R1",
                               "19.0.x": "R1", "hotfix/INTRD-2": "R1"}


def test_r2_source_or_destination_of_an_open_pr_is_kept():
    prs = [{"id": 7, "source": {"branch": {"name": "fix/INTRD-1"}},
            "destination": {"branch": {"name": "fix/INTRD-2"}}}]
    bb = make([branch("fix/INTRD-1"), branch("fix/INTRD-2")], open_prs=prs)
    result = scan(bb, FakeJira({k: issue(k) for k in ("INTRD-1", "INTRD-2")}))
    assert reasons(result)["fix/INTRD-1"] == "R2"
    assert reasons(result)["fix/INTRD-2"] == "R2"


def test_r3_unmerged_commits_keep_the_branch():
    bb = make([branch("fix/INTRD-1")], unmerged={"h-fix/INTRD-1"})
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert reasons(result)["fix/INTRD-1"] == "R3"


def test_r3_checks_against_the_merged_pr_destination_when_it_exists():
    bb = make([branch("19.0.x"), branch("fix/INTRD-1")], merged_into={"fix/INTRD-1": "19.0.x"})
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert result["deletable"][0]["target"] == "19.0.x"
    commit_calls = [p for path, p in bb.calls if path.endswith("/commits")]
    assert commit_calls[0]["exclude"] == "19.0.x"
    assert commit_calls[0]["include"] == "h-fix/INTRD-1"


def test_r4_recent_commit_keeps_the_branch_even_if_the_ticket_is_closed():
    bb = make([branch("fix/INTRD-1", date="2026-09-15T00:00:00+00:00")])
    result = branch_scan.scan_repo(bb, FakeJira({"INTRD-1": issue("INTRD-1")}), "ws", "repo",
                                   datetime(2026, 10, 1, tzinfo=timezone.utc), RECENT)
    assert reasons(result)["fix/INTRD-1"] == "R4"


@pytest.mark.parametrize("kind,deleted", [("Bug", True), ("Sub-bug", True), ("Task", True),
                                          ("Sub-task", True), ("Story", False), ("Epic", False)])
def test_r5_only_bug_and_task_types(kind, deleted):
    bb = make([branch("feature/INTRD-1")])
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1", kind)}))
    assert bool(result["deletable"]) is deleted


def test_r5_no_key_or_unknown_ticket_is_kept():
    bb = make([branch("fix/typo"), branch("fix/INTRD-404")])
    result = scan(bb, FakeJira({}))
    assert reasons(result)["fix/typo"] == "R5"
    assert reasons(result)["fix/INTRD-404"] == "R5"


def test_failed_batch_search_falls_back_to_per_key_lookups():
    bb = make([branch("fix/INTRD-1")])
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}, search_fails=True))
    assert len(result["deletable"]) == 1


def test_a_failing_merge_check_keeps_the_branch():
    bb = make([branch("fix/INTRD-1")])
    bb.routes[f"{BASE}/commits"] = bitbucket_client.BitbucketError("HTTP 500", status=500)
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert reasons(result)["fix/INTRD-1"] == "ERR"


def test_unreadable_branch_restrictions_abort_the_repository():
    bb = make([branch("fix/INTRD-1")])
    bb.routes[f"{BASE}/branch-restrictions"] = bitbucket_client.BitbucketError("HTTP 403", status=403)
    with pytest.raises(bitbucket_client.BitbucketError):
        scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))


def test_develop_wins_over_a_stale_branching_model():
    bb = make([branch("fix/INTRD-1")], model={"development": {"branch": {"name": "backlog"}}})
    bb.routes[f"{BASE}/refs/branches"].append(branch("backlog"))
    result = scan(bb, FakeJira({"INTRD-1": issue("INTRD-1")}))
    assert result["dev_branch"] == "develop"

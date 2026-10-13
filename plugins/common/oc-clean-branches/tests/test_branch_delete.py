"""Deletion: confirmation lock and the last-second re-checks."""
import pytest
from conftest import FakeBitbucket

import branch_delete

BASE = "/repositories/ws/repo"


def plan(*rows):
    return {"workspace": "ws", "repos": [{"repo": "repo", "deletable": [
        {"name": n, "hash": h} for n, h in rows]}]}


def bb(tips, open_prs=()):
    routes = {f"{BASE}/pullrequests": list(open_prs)}
    for name, sha in tips.items():
        routes[f"{BASE}/refs/branches/{name}"] = {"target": {"hash": sha}}
    return FakeBitbucket(routes)


def test_a_wrong_confirm_count_deletes_nothing():
    fake = bb({"fix/A-1": "h1"})
    with pytest.raises(SystemExit):
        branch_delete.execute(fake, plan(("fix/A-1", "h1")), confirm=2)
    assert fake.deleted == []


def test_deletes_when_tip_unchanged():
    fake = bb({"fix/A-1": "h1"})
    results = branch_delete.execute(fake, plan(("fix/A-1", "h1")), confirm=1)
    assert fake.deleted == [("repo", "fix/A-1")]
    assert results[0]["status"] == "deleted"


def test_a_moved_tip_is_skipped():
    fake = bb({"fix/A-1": "NEW"})
    results = branch_delete.execute(fake, plan(("fix/A-1", "h1")), confirm=1)
    assert fake.deleted == [] and results[0]["status"] == "skipped"


def test_a_new_open_pr_is_skipped():
    prs = [{"source": {"branch": {"name": "fix/A-1"}}, "destination": {"branch": {"name": "dev"}}}]
    fake = bb({"fix/A-1": "h1"}, open_prs=prs)
    results = branch_delete.execute(fake, plan(("fix/A-1", "h1")), confirm=1)
    assert fake.deleted == [] and results[0]["reason"].startswith("an open PR")


def test_an_already_deleted_branch_is_skipped_not_failed():
    fake = bb({})
    results = branch_delete.execute(fake, plan(("fix/A-1", "h1")), confirm=1)
    assert results[0] == {"repo": "repo", "name": "fix/A-1", "hash": "h1",
                          "status": "skipped", "reason": "already gone"}

"""Pure guard rules."""
import pytest

import branch_rules as rules


@pytest.mark.parametrize("name", ["master", "main", "develop", "dev", "Develop",
                                  "release/15.2", "release-14", "releases/x", "support/13",
                                  "19.0.x", "14.1.0", "v15", "15.x", "integration/19.0.x",
                                  "19.0.x-hotfix"])
def test_structural_names_are_protected(name):
    assert rules.structural_reason(name)


@pytest.mark.parametrize("name", ["fix/INTRD-123", "feature/INTRD-45-foo", "bugfix/2fa-login",
                                  "fix/12345-foo", "developer-tools", "fix/release-notes"])
def test_ticket_branches_are_not_structural(name):
    assert rules.structural_reason(name) is None


def test_glob_restrictions_and_branching_model_types_resolve():
    model = {"development": {"branch": {"name": "develop"}},
             "branch_types": [{"kind": "release", "prefix": "release/"}]}
    restrictions = [{"branch_match_kind": "glob", "pattern": "hotfix/*"},
                    {"branch_match_kind": "branching_model", "branch_type": "development"},
                    {"branch_match_kind": "branching_model", "branch_type": "release"}]
    globs = rules.restriction_patterns(restrictions, model)
    assert globs == ["develop", "hotfix/*", "release/*"]
    assert rules.restricted_by("hotfix/INTRD-1", globs) == "hotfix/*"
    assert rules.restricted_by("fix/INTRD-1", globs) is None


def test_unresolvable_model_restriction_raises_instead_of_being_ignored():
    with pytest.raises(ValueError):
        rules.restriction_patterns(
            [{"branch_match_kind": "branching_model", "branch_type": "hotfix"}], {})


@pytest.mark.parametrize("name,key", [("fix/INTRD-123-foo", "INTRD-123"),
                                      ("feature/macrd-77_bar", "MACRD-77"),
                                      ("INTRD-9", "INTRD-9"), ("fix/typo", None)])
def test_ticket_key(name, key):
    assert rules.ticket_key(name) == key


@pytest.mark.parametrize("issuetype,ok", [("Bug", True), ("Sub-bug", True), ("Task", True),
                                          ("Sub-task", True), ("Subtask", True),
                                          ("Story", False), ("Epic", False),
                                          ("Enabler", False), (None, False)])
def test_type_allowed(issuetype, ok):
    assert rules.type_allowed(issuetype) is ok


def test_parse_ts_handles_bitbucket_and_jira_offsets():
    a = rules.parse_ts("2026-05-01T10:00:00+00:00")
    b = rules.parse_ts("2026-05-01T12:00:00.000+0200")
    assert a == b

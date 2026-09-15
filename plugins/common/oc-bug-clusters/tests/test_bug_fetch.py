import json
from datetime import date

import pytest
from conftest import FakeOpener

import bug_fetch as bf
import jira_client as jc


# ---------------------------------------------------------------- ADF flattening

def test_flatten_adf_joins_paragraph_text():
    doc = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Steps to"},
                                          {"type": "text", "text": " reproduce"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "Open the quote"}]},
    ]}
    assert bf.flatten_adf(doc) == "Steps to reproduce Open the quote"


def test_flatten_adf_reaches_text_inside_lists_and_tables():
    doc = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "first"}]}]}]},
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "cell"}]}]}]}]},
    ]}
    assert bf.flatten_adf(doc) == "first cell"


@pytest.mark.parametrize("bad", [None, "", [], {}, {"content": "not-a-list"}, 42])
def test_flatten_adf_never_raises(bad):
    assert bf.flatten_adf(bad) == ""


def test_flatten_adf_takes_a_plain_string_description_as_is():
    """REST v3 returns ADF, but v2, exports and proxies return a string. Returning
    "" for those silently costs every bug its excerpt, which is invisible in the
    report — it just looks like the bugs had no descriptions."""
    assert bf.flatten_adf("## Problem\n\nContract  not\tapplied") == \
        "## Problem Contract not applied"


def test_flatten_adf_collapses_whitespace():
    doc = {"content": [{"type": "text", "text": "a  \n\t b"}]}
    assert bf.flatten_adf(doc) == "a b"


# ------------------------------------------------------------------- excerpting

def test_excerpt_passes_short_text_through():
    assert bf.excerpt("short") == "short"


def test_excerpt_truncates_with_an_ellipsis_at_the_limit():
    out = bf.excerpt("x" * 500, limit=300)
    assert len(out) == 300 and out.endswith("…")


def test_excerpt_handles_none():
    assert bf.excerpt(None) == ""


# --------------------------------------------------------------- area assignment

@pytest.mark.parametrize("component,expected", [
    ("Frontend", "portal"), ("frontend", "portal"),
    ("Backend", "core"), (" BACKEND ", "core"),
])
def test_component_decides_the_area(component, expected):
    assert bf.area_of({"components": [{"name": component}]}) == expected


def test_component_wins_over_a_contradicting_summary_tag():
    fields = {"components": [{"name": "Backend"}], "summary": "[Front] broken"}
    assert bf.area_of(fields) == "core"


@pytest.mark.parametrize("summary,expected", [
    ("[Front] blank screen", "portal"),
    ("[ back ] NPE on save", "core"),
    ("[BACK] NPE", "core"),
])
def test_summary_tag_is_the_fallback(summary, expected):
    assert bf.area_of({"summary": summary}) == expected


@pytest.mark.parametrize("fields", [
    {}, {"components": []}, {"components": [{"name": "Testing"}]},
    {"summary": "[Rating] contract not applied"},
    {"summary": "front-end issue"},          # tag must be bracketed and leading
    {"summary": "fix [front] later"},
])
def test_unresolvable_area_is_none(fields):
    assert bf.area_of(fields) is None


# ------------------------------------------------------------- resolution filter

@pytest.mark.parametrize("resolution", [None, {}, {"name": "Done"}, {"name": "Fixed"}])
def test_real_defects_are_kept(resolution):
    assert bf.is_real_defect({"resolution": resolution}) is True


@pytest.mark.parametrize("name", ["Invalid", "invalid", "Duplicate", " DUPLICATE ",
                                  "Declined", " declined "])
def test_rejecting_resolutions_are_dropped(name):
    assert bf.is_real_defect({"resolution": {"name": name}}) is False


@pytest.mark.parametrize("name", ["Invalid", "invalid", " INVALID "])
def test_the_invalid_status_is_dropped_even_with_no_resolution(name):
    """Measured: this Jira rejects a bug via the STATUS Invalid, so a
    resolution-only filter would keep every one of them."""
    assert bf.is_real_defect({"status": {"name": name}, "resolution": None}) is False


def test_an_ordinary_status_is_kept():
    assert bf.is_real_defect({"status": {"name": "In Progress"}}) is True


# ------------------------------------------------------------------- the window

def test_window_defaults_to_the_last_30_days_ending_tomorrow():
    since, until = bf.resolve_window(None, None, today=date(2026, 9, 15))
    assert (since, until) == ("2026-08-17", "2026-09-16")


def test_until_is_exclusive_so_a_calendar_month_is_exact():
    since, until = bf.resolve_window("2026-08-01", "2026-09-01")
    assert (since, until) == ("2026-08-01", "2026-09-01")


def test_since_alone_is_honoured():
    since, until = bf.resolve_window("2026-01-01", None, today=date(2026, 9, 15))
    assert (since, until) == ("2026-01-01", "2026-09-16")


def test_until_alone_derives_since_30_days_earlier():
    assert bf.resolve_window(None, "2026-03-31") == ("2026-03-01", "2026-03-31")


def test_an_inverted_window_is_rejected():
    with pytest.raises(ValueError, match="must be before"):
        bf.resolve_window("2026-09-01", "2026-08-01")


# ---------------------------------------------------------------------- the JQL

def test_jql_quotes_sub_bug_and_uses_a_half_open_window():
    jql = bf.build_jql(["INTRD"], "2026-08-01", "2026-09-01")
    assert 'issuetype in (Bug, "Sub-bug")' in jql
    assert 'created >= "2026-08-01"' in jql and 'created < "2026-09-01"' in jql
    assert "project in (INTRD)" in jql


def test_jql_joins_several_projects():
    assert "project in (INTRD, MACRD)" in bf.build_jql(
        ["INTRD", "MACRD"], "2026-08-01", "2026-09-01")


# ----------------------------------------------------------------- normalisation

def issue(key="INTRD-1", **overrides):
    fields = {
        "summary": "[Rating] contract ignored",
        "description": {"content": [{"type": "text", "text": "long story"}]},
        "issuetype": {"name": "Bug"},
        "status": {"name": "In Progress",
                   "statusCategory": {"key": "indeterminate"}},
        "resolution": None,
        "components": [{"name": "Backend"}],
        "labels": ["billing"],
        "created": "2026-09-14T21:47:43.801+0200",
        "priority": {"name": "Major"},
        "assignee": {"displayName": "Adil El Jaouhari"},
        "reporter": {"displayName": "Mohamed Hamidi"},
        "parent": None,
    }
    fields.update(overrides)
    return {"key": key, "fields": fields}


def test_normalize_produces_the_shared_record_shape():
    rec = bf.normalize(issue())
    assert rec["key"] == "INTRD-1"
    assert rec["area"] == "core"
    assert rec["component"] == "Backend"
    assert rec["created"] == "2026-09-14"
    assert rec["status_category"] == "indeterminate"
    assert rec["excerpt"] == "long story"
    assert rec["assignee"] == "Adil El Jaouhari"
    assert rec["url"] == "https://opencellsoft.atlassian.net/browse/INTRD-1"
    assert rec["parent"] is None


def test_normalize_survives_every_optional_field_being_absent():
    rec = bf.normalize({"key": "INTRD-2", "fields": {"summary": "x"}})
    assert rec["area"] is None and rec["assignee"] is None
    assert rec["labels"] == [] and rec["excerpt"] == ""
    assert rec["created"] == ""


def test_normalize_records_the_parent_key_of_a_sub_bug():
    rec = bf.normalize(issue(issuetype={"name": "Sub-bug"},
                             parent={"key": "INTRD-900"}))
    assert rec["issuetype"] == "Sub-bug" and rec["parent"] == "INTRD-900"


# -------------------------------------------------------------------- collection

@pytest.mark.parametrize("repo,expected", [
    ("portal", {"portal"}), ("core", {"core"}), ("both", {"portal", "core"}),
])
def test_areas_in_scope(repo, expected):
    assert bf.areas_in_scope(repo) == expected


def client_for(issues, env):
    return jc.JiraClient(opener=FakeOpener([{"issues": issues, "isLast": True}]), env=env)


def test_collect_keeps_the_area_in_scope_and_all_unclassified(env):
    issues = [
        issue("INTRD-1", components=[{"name": "Frontend"}]),
        issue("INTRD-2", components=[{"name": "Backend"}]),
        issue("INTRD-3", components=[], summary="no tag at all"),
    ]
    doc = bf.collect(client_for(issues, env), "jql", "portal")

    assert [b["key"] for b in doc["bugs"]] == ["INTRD-1", "INTRD-3"]
    assert doc["fetched"] == 3


def test_collect_drops_invalid_and_counts_them(env):
    issues = [
        issue("INTRD-1"),
        issue("INTRD-2", resolution={"name": "Declined"}),
        issue("INTRD-3", status={"name": "Invalid",
                                 "statusCategory": {"key": "done"}}),
    ]
    doc = bf.collect(client_for(issues, env), "jql", "core")

    assert [b["key"] for b in doc["bugs"]] == ["INTRD-1"]
    assert doc["fetched"] == 3 and doc["dropped_invalid"] == 2


def test_classify_rows_are_compact_and_cover_only_classifiable_bugs(env):
    issues = [issue("INTRD-1"), issue("INTRD-2", components=[], summary="untagged")]
    doc = bf.collect(client_for(issues, env), "jql", "both")

    rows = bf.classify_rows(doc)

    assert [r["key"] for r in rows] == ["INTRD-1"], "unclassified bugs are not classified"
    assert set(rows[0]) == {"key", "summary", "excerpt", "component", "labels"}

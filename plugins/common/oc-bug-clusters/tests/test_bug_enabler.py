import pytest

import bug_cluster as bc
import bug_enabler as be
from test_bug_cluster import document, spread


def model_for(repo="portal", sizes=(("quoting", 6),), area="portal"):
    assignments = {}
    bugs = []
    for index, (subject, n) in enumerate(sizes):
        bugs += spread(f"{area[0].upper()}{index}", area, n, subject, assignments)
    for b in bugs:
        b["area"] = area
    return bc.build_model(document(bugs, repo=repo), assignments, min_cluster=5)


def plan_for(**kwargs):
    model = kwargs.pop("model", None) or model_for()
    return be.build_plan(model, project="INTRD",
                         assignees=dict(be.DEFAULT_ASSIGNEE),
                         report_path="./docs/bug-clusters-2026-09-15.html", **kwargs)


# ------------------------------------------------------------------ marker label

def test_marker_label_uses_the_area_token_not_the_component():
    assert be.marker_label("portal", "2026-08-01", "2026-09-01") == \
        "bug-clusters-portal-2026-08-01-2026-09-01"


def test_marker_label_is_a_legal_jira_label():
    label = be.marker_label("core", "2026-08-01", "2026-09-01")
    assert " " not in label and label.islower()


# --------------------------------------------------------------------------- ADF

def test_adf_doc_has_the_shape_rest_v3_demands():
    doc = be.adf_doc([be.adf_para("hello")])
    assert doc["type"] == "doc" and doc["version"] == 1
    assert doc["content"][0]["content"][0]["text"] == "hello"


def test_adf_bullets_makes_one_list_item_per_entry():
    node = be.adf_bullets(["a", "b"])
    assert node["type"] == "bulletList" and len(node["content"]) == 2
    assert node["content"][0]["type"] == "listItem"


# ---------------------------------------------------------------- Enabler fields

def test_enabler_carries_type_project_component_and_assignee():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    assert fields["project"] == {"key": "INTRD"}
    assert fields["issuetype"] == {"id": be.ENABLER_TYPE_ID}
    assert fields["components"] == [{"name": "Frontend"}]
    assert fields["assignee"] == {"id": "5ef5c13914f60e0ac1c9b049"}


def test_enabler_summary_names_the_component_and_the_window():
    summary = plan_for()["areas"][0]["enabler"]["fields"]["summary"]
    assert summary == "Bug clusters — Frontend — 2026-08-01 → 2026-09-01"


def test_enabler_carries_the_marker_label():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    assert "bug-clusters-portal-2026-08-01-2026-09-01" in fields["labels"]


def test_enabler_description_mentions_the_clusters_and_the_report():
    fields = plan_for()["areas"][0]["enabler"]["fields"]
    text = str(fields["description"])
    assert "quoting" in text and "bug-clusters-2026-09-15.html" in text


def test_backend_enabler_gets_the_backend_defaults():
    plan = plan_for(model=model_for(repo="core", area="core"))
    fields = plan["areas"][0]["enabler"]["fields"]
    assert fields["components"] == [{"name": "Backend"}]
    assert fields["assignee"] == {"id": "63369fa788ed2ebef97cddfb"}


def test_an_assignee_override_is_honoured():
    model = model_for()
    plan = be.build_plan(model, project="INTRD",
                         assignees={"portal": "acc-999", "core": "x"},
                         report_path="r.html")
    assert plan["areas"][0]["enabler"]["fields"]["assignee"] == {"id": "acc-999"}


# ---------------------------------------------------------------- Sub-task fields

def test_one_subtask_per_cluster_named_subject_and_count():
    plan = plan_for(model=model_for(sizes=(("quoting", 7), ("rating", 5))))
    summaries = [s["fields"]["summary"] for s in plan["areas"][0]["subtasks"]]
    assert summaries == ["quoting — 7 bugs", "rating — 5 bugs"]


def test_subtask_inherits_the_enabler_assignee():
    area = plan_for()["areas"][0]
    assert area["subtasks"][0]["fields"]["assignee"] == area["enabler"]["fields"]["assignee"]


def test_subtask_has_no_parent_at_plan_time():
    assert "parent" not in plan_for()["areas"][0]["subtasks"][0]["fields"]


def test_subtask_uses_the_subtask_type_id():
    fields = plan_for()["areas"][0]["subtasks"][0]["fields"]
    assert fields["issuetype"] == {"id": be.SUBTASK_TYPE_ID}


def test_subtask_lists_every_bug_of_its_cluster_and_links_them():
    plan = plan_for(model=model_for(sizes=(("quoting", 6),)))
    subtask = plan["areas"][0]["subtasks"][0]
    assert len(subtask["links"]) == 6
    text = str(subtask["fields"]["description"])
    for key in subtask["links"]:
        assert key in text


# ------------------------------------------------------------------- plan shape

def test_near_clusters_never_become_subtasks():
    plan = plan_for(model=model_for(sizes=(("quoting", 6), ("rating", 2))))
    assert [s["subject"] for s in plan["areas"][0]["subtasks"]] == ["quoting"]


def test_an_area_with_no_cluster_is_absent_from_the_plan():
    plan = plan_for(model=model_for(sizes=(("quoting", 2),)))
    assert plan["areas"] == []


def test_both_areas_each_get_their_own_enabler():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    plan = be.build_plan(model, "INTRD", dict(be.DEFAULT_ASSIGNEE), "r.html")

    assert [a["component"] for a in plan["areas"]] == ["Frontend", "Backend"]
    assert len({a["marker"] for a in plan["areas"]}) == 2


def test_call_count_is_one_enabler_plus_subtasks_plus_links():
    plan = plan_for(model=model_for(sizes=(("quoting", 6), ("rating", 5))))
    assert plan["calls"] == 1 + 2 + 11


def test_render_plan_shows_every_summary_and_the_call_count():
    text = be.render_plan(plan_for(model=model_for(sizes=(("quoting", 6),))))
    assert "Bug clusters — Frontend" in text
    assert "quoting — 6 bugs" in text
    assert "8" in text            # 1 enabler + 1 subtask + 6 links


# ------------------------------------------------------------- createmeta guard

def test_required_fields_ignore_those_with_a_default():
    meta = {"fields": [
        {"fieldId": "summary", "required": True},
        {"fieldId": "reporter", "required": True, "hasDefaultValue": True},
        {"fieldId": "labels", "required": False},
    ]}
    assert be.required_field_ids(meta) == {"summary"}


def test_missing_required_names_what_the_payload_lacks():
    meta = {"fields": [{"fieldId": "summary", "required": True},
                       {"fieldId": "customfield_1", "required": True}]}
    assert be.missing_required(meta, {"summary": "x"}) == {"customfield_1"}


def test_missing_required_is_empty_when_the_payload_covers_everything():
    meta = {"fields": [{"fieldId": "summary", "required": True}]}
    assert be.missing_required(meta, {"summary": "x", "labels": []}) == set()

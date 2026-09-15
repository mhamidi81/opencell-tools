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


# ============================================================ applier behaviour

import jira_client as jc


def test_subtask_inherits_an_OVERRIDDEN_enabler_assignee():
    """Closes a gap in Task 6's tests: inheritance was only ever checked with the
    DEFAULT assignees, so an implementation that hardcoded the area default would
    have passed. Sub-task inheritance is behaviour the user asked for explicitly,
    so it is asserted against a value that cannot come from a constant."""
    model = model_for()
    plan = be.build_plan(model, project="INTRD",
                         assignees={"portal": "acc-override-1", "core": "acc-override-2"},
                         report_path="r.html")
    area = plan["areas"][0]
    assert area["enabler"]["fields"]["assignee"] == {"id": "acc-override-1"}
    for subtask in area["subtasks"]:
        assert subtask["fields"]["assignee"] == {"id": "acc-override-1"}


class RecordingClient:
    """Stands in for JiraClient. `fail_on` maps a call signature to an exception."""

    def __init__(self, search_results=(), fail_on=None, meta=None):
        self.search_results = list(search_results)
        self.fail_on = dict(fail_on or {})
        self.meta = meta or {"fields": [{"fieldId": "summary", "required": True}]}
        self.posts = []
        self.gets = []
        self._n = 0

    def search(self, jql, fields, page_size=100):
        self.searches = getattr(self, "searches", [])
        self.searches.append(jql)
        return iter(self.search_results.pop(0) if self.search_results else [])

    def get(self, path):
        self.gets.append(path)
        if path in self.fail_on:
            raise self.fail_on[path]
        return self.meta

    def post(self, path, body):
        self.posts.append((path, body))
        summary = (body.get("fields") or {}).get("summary")
        if summary in self.fail_on:
            # One-shot: a retry that changes the payload (e.g. drops a rejected
            # assignee) must be allowed to succeed, not hit the same guard again.
            raise self.fail_on.pop(summary)
        if path == "/rest/api/3/issue":
            self._n += 1
            return {"key": f"INTRD-{900 + self._n}"}
        return {}


def created_issues(client):
    return [b["fields"]["summary"] for p, b in client.posts if p == "/rest/api/3/issue"]


def link_count(client):
    return sum(1 for p, _ in client.posts if p == "/rest/api/3/issueLink")


# ------------------------------------------------------------ assignee resolution

def test_an_account_id_passes_straight_through():
    client = RecordingClient()
    assert be.resolve_assignee(client, "5ef5c13914f60e0ac1c9b049") == \
        "5ef5c13914f60e0ac1c9b049"
    assert client.gets == []


def test_an_email_is_resolved_to_an_account_id():
    client = RecordingClient()
    client.meta = [{"accountId": "acc-1", "emailAddress": "a@opencellsoft.com"}]
    assert be.resolve_assignee(client, "a@opencellsoft.com") == "acc-1"
    assert "user/search" in client.gets[0]


def test_an_unresolvable_email_raises_before_anything_is_written():
    client = RecordingClient()
    client.meta = []
    with pytest.raises(jc.JiraError, match="no Jira user"):
        be.resolve_assignee(client, "ghost@opencellsoft.com")


# ------------------------------------------------------------------ idempotency

def test_an_existing_marker_label_is_found():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    assert be.existing_enabler(client, "INTRD", "bug-clusters-portal-a-b") == "INTRD-500"
    assert 'labels = "bug-clusters-portal-a-b"' in client.searches[0]


def test_no_marker_means_no_existing_enabler():
    assert be.existing_enabler(RecordingClient(), "INTRD", "m") is None


def test_apply_skips_an_area_whose_marker_already_exists():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    state = be.apply_plan(client, plan_for(), be.new_state())

    assert created_issues(client) == []
    assert any("INTRD-500" in w for w in state["warnings"])


def test_force_creates_anyway():
    client = RecordingClient(search_results=[[{"key": "INTRD-500"}]])
    be.apply_plan(client, plan_for(), be.new_state(), force=True)
    assert len(created_issues(client)) == 2      # 1 enabler + 1 subtask


# ---------------------------------------------------------------------- preflight

def test_preflight_passes_when_every_required_field_is_present():
    client = RecordingClient()
    be.preflight(client, "INTRD", plan_for())     # must not raise


def test_preflight_stops_on_an_unexpected_required_field():
    client = RecordingClient(meta={"fields": [
        {"fieldId": "summary", "required": True},
        {"fieldId": "customfield_777", "required": True}]})
    with pytest.raises(jc.JiraError, match="customfield_777"):
        be.preflight(client, "INTRD", plan_for())


# ------------------------------------------------------------------ creation flow

def test_apply_creates_the_enabler_then_its_subtasks():
    client = RecordingClient()
    be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                  be.new_state())
    assert created_issues(client) == ["Bug clusters — Frontend — 2026-08-01 → 2026-09-01",
                                      "quoting — 6 bugs"]


def test_subtask_is_given_the_enabler_as_its_parent():
    client = RecordingClient()
    be.apply_plan(client, plan_for(), be.new_state())
    subtask_body = [b for p, b in client.posts if p == "/rest/api/3/issue"][1]
    assert subtask_body["fields"]["parent"] == {"key": "INTRD-901"}


def test_every_bug_of_a_cluster_is_linked_to_its_subtask():
    client = RecordingClient()
    state = be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                          be.new_state())
    assert link_count(client) == 6
    assert len(state["links"]) == 6


def test_a_link_uses_the_relates_type_and_points_at_the_subtask():
    client = RecordingClient()
    be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 5),))),
                  be.new_state())
    body = next(b for p, b in client.posts if p == "/rest/api/3/issueLink")
    assert body["type"] == {"name": "Relates"}
    assert body["outwardIssue"] == {"key": "INTRD-902"}


def test_state_records_what_was_created():
    client = RecordingClient()
    state = be.apply_plan(client, plan_for(), be.new_state())
    assert state["enablers"]["portal"] == "INTRD-901"
    assert state["subtasks"]["portal/quoting"] == "INTRD-902"


# --------------------------------------------------------------------- resumption

def test_a_rerun_with_existing_state_creates_nothing_twice():
    plan = plan_for()
    first = be.apply_plan(RecordingClient(), plan, be.new_state())

    client = RecordingClient()
    be.apply_plan(client, plan, first)

    assert created_issues(client) == [] and link_count(client) == 0


def test_a_rerun_completes_a_partially_created_area():
    plan = plan_for(model=model_for(sizes=(("quoting", 5),)))
    state = be.new_state()
    state["enablers"]["portal"] = "INTRD-500"

    client = RecordingClient()
    be.apply_plan(client, plan, state)

    assert created_issues(client) == ["quoting — 5 bugs"]
    assert link_count(client) == 5


# ----------------------------------------------------------- failure containment

def test_a_failed_link_is_warned_about_and_does_not_stop_the_run():
    client = RecordingClient()
    original = client.post

    def post(path, body):
        if path == "/rest/api/3/issueLink":
            client.posts.append((path, body))
            raise jc.JiraError("HTTP 404 on POST /rest/api/3/issueLink: no such issue")
        return original(path, body)

    client.post = post
    state = be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 5),))),
                          be.new_state())

    assert state["subtasks"]["portal/quoting"]
    assert len(state["warnings"]) == 5
    assert state["links"] == []


def test_a_rejected_assignee_retries_the_create_unassigned():
    summary = "Bug clusters — Frontend — 2026-08-01 → 2026-09-01"
    client = RecordingClient(fail_on={
        summary: jc.JiraError("HTTP 400 on POST /rest/api/3/issue: "
                              '{"errors":{"assignee":"not permitted"}}')})
    state = be.apply_plan(client, plan_for(), be.new_state())

    bodies = [b for p, b in client.posts if p == "/rest/api/3/issue"]
    assert "assignee" not in bodies[1]["fields"], "retry drops the assignee"
    assert state["enablers"]["portal"]
    assert any("assignee" in w for w in state["warnings"])


def test_a_failed_subtask_leaves_the_enabler_and_the_state_intact():
    client = RecordingClient(fail_on={
        "quoting — 6 bugs": jc.JiraError("HTTP 500 on POST /rest/api/3/issue: boom")})
    with pytest.raises(jc.JiraError):
        be.apply_plan(client, plan_for(model=model_for(sizes=(("quoting", 6),))),
                      be.new_state())

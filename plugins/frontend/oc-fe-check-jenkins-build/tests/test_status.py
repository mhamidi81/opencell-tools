import json

import jenkins_common as jc
import jenkins_status as st
from conftest import FakeClient, describe, job, load


def failed_routes(**stages):
    return {
        "/job/dev/api/json": job(result="FAILURE"),
        "/job/dev/4970/api/json": load("build_4970.json"),
        "/job/dev/4970/wfapi/describe": describe("FAILED", **stages),
    }


def run(capsys, client, *argv):
    code = st.main(list(argv), client=client)
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


def test_first_failed_stage_and_front_match():
    stages = describe("FAILED", **{"Build Front": "FAILED"})["stages"]
    stage = st.first_failed_stage(stages)
    assert stage["name"] == "Build Front" and stage["id"] == "132"
    assert st.is_front(stage)
    assert st.is_front({"name": "  checkout FRONT "})
    assert not st.is_front({"name": "Build Meveo"})
    assert not st.is_front(None)


def test_build_params_and_portal_sha():
    build = load("build_4970.json")
    params = st.build_params(build)
    assert params["version"] == "dev" and params["build_front"] is True
    assert params["cc_mail"] == ""
    assert st.portal_sha(build) == "e8dbdc60285b7032862e78b44ebabea626c41bca"
    assert st.portal_sha({"actions": [{}]}) is None


def test_timer_extras_are_only_undeclared_keys():
    build = load("build_4970.json")
    extras = st.timer_extras(build, st.declared_params(load("job_dev.json")))
    assert extras == {"ASSETS_URL": "/opencell/frontend/DEMO/portal/",
                      "VITE_APP_BASE_URL": "/opencell/frontend/DEMO/portal/"}


def test_timer_extras_keeps_comma_values():
    build = {"actions": [{"causes": [{"shortDescription":
        "Started by timer with parameters: {a=1, LIST=x@e.com,y@e.com, z@e.com, b=2}"}]}]}
    assert st.timer_extras(build, ["a"]) == {"LIST": "x@e.com,y@e.com, z@e.com", "b": "2"}


def test_timer_extras_empty_for_manual_build():
    build = {"actions": [{"causes": [{"shortDescription": "Started by user Jane"}]}]}
    assert st.timer_extras(build, []) == {}


def test_green_does_not_fetch_the_build(capsys):
    client = FakeClient({"/job/dev/api/json": job()})
    code, out = run(capsys, client, "--branch", "dev")
    assert code == 0 and out["action"] == "green" and out["build"] == 4970
    assert len(client.calls) == 1, "a green build needs only the job call"


def test_running(capsys):
    code, out = run(capsys, FakeClient({"/job/dev/api/json": job(building=True, result=None)}))
    assert out["action"] == "running"


def test_no_builds(capsys):
    j = job()
    j["lastBuild"] = None
    code, out = run(capsys, FakeClient({"/job/dev/api/json": j}))
    assert out["action"] == "no_builds" and out["build"] is None


def test_build_front_failure_is_fix(capsys):
    code, out = run(capsys, FakeClient(failed_routes(**{"Build Front": "FAILED"})))
    assert code == 0
    assert out["action"] == "fix"
    assert out["failed_stage"] == "Build Front" and out["failed_stage_id"] == "132"
    assert out["portal_sha"].startswith("e8dbdc6")
    assert out["params"]["to_mail"] == "dev1@example.com,dev2@example.com, dev3@example.com"
    assert set(out["timer_extras"]) == {"ASSETS_URL", "VITE_APP_BASE_URL"}


def test_checkout_front_failure_is_fix(capsys):
    _, out = run(capsys, FakeClient(failed_routes(**{"Checkout Front": "FAILED"})))
    assert out["action"] == "fix" and out["failed_stage"] == "Checkout Front"


def test_core_failure_is_out_of_scope(capsys):
    _, out = run(capsys, FakeClient(failed_routes(**{"Build Meveo": "FAILED"})))
    assert out["action"] == "out_of_scope" and out["failed_stage"] == "Build Meveo"
    assert out["is_front"] is False


def test_failure_without_failed_stage_is_out_of_scope(capsys):
    _, out = run(capsys, FakeClient(failed_routes()))
    assert out["action"] == "out_of_scope" and out["failed_stage"] is None


def test_aborted_is_not_failed(capsys):
    routes = failed_routes(**{"Build Front": "ABORTED"})
    routes["/job/dev/api/json"] = job(result="ABORTED")
    _, out = run(capsys, FakeClient(routes))
    assert out["action"] == "not_failed"


def test_branch_is_encoded_in_calls(capsys):
    client = FakeClient({"/job/release%2F15.0/api/json": job()})
    code, _ = run(capsys, client, "--branch", "release/15.0")
    assert code == 0 and client.calls[0].startswith("/job/release%2F15.0/api/json")


def test_main_missing_job_exits_3(capsys):
    code = st.main(["--branch", "nope"], client=FakeClient({}))
    assert code == jc.EXIT_NOT_FOUND
    assert "/job/nope" in capsys.readouterr().err


def test_main_auth_exits_2(capsys):
    client = FakeClient({"/job/dev/api/json": jc.JenkinsError("HTTP 401", status=401)})
    assert st.main([], client=client) == jc.EXIT_AUTH

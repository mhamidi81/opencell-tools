import itertools
import json

import pytest

import jenkins_common as jc
import jenkins_rebuild as rb
from conftest import FakeClient, describe, load, seq

QUEUE = "https://jenkins.example/queue/item/9/"


def test_form_from_params():
    form = rb.form_from_params({"build_front": True, "force_kc": False, "cc_mail": "",
                                "x": None, "to_mail": "a@e.com,b@e.com, c@e.com"})
    assert form == [("build_front", "true"), ("force_kc", "false"), ("cc_mail", ""),
                    ("x", ""), ("to_mail", "a@e.com,b@e.com, c@e.com")]


def test_trigger_posts_and_returns_queue_url():
    client = FakeClient({"POST /job/dev/buildWithParameters": {"location": QUEUE}})
    assert rb.trigger(client, "dev", {"version": "dev"}) == QUEUE
    assert client.posts == [("/job/dev/buildWithParameters", [("version", "dev")])]


def test_trigger_without_location_fails():
    with pytest.raises(jc.JenkinsError):
        rb.trigger(FakeClient({}), "dev", {"version": "dev"})


def test_wait_for_start_waits_while_queued():
    sleeps = []
    client = FakeClient({QUEUE + "api/json": seq(
        {"why": "Build #4971 is already in progress"}, {"executable": {"number": 4972}})})
    assert rb.wait_for_start(client, QUEUE, 100, sleeps.append, lambda: 0) == (4972, None)
    assert sleeps == [10]


def test_wait_for_start_times_out_with_reason():
    client = FakeClient({QUEUE + "api/json": lambda: {"why": "Build #4971 is already in progress"}})
    clock = itertools.count(0, 50).__next__
    number, why = rb.wait_for_start(client, QUEUE, 100, lambda s: None, clock)
    assert number is None and "already in progress" in why


def test_wait_for_start_cancelled():
    client = FakeClient({QUEUE + "api/json": {"cancelled": True}})
    with pytest.raises(jc.JenkinsError):
        rb.wait_for_start(client, QUEUE, 100, lambda s: None, lambda: 0)


def test_front_status():
    assert rb.front_status(describe("SUCCESS")) == "SUCCESS"
    assert rb.front_status(describe("FAILED", **{"Build Front": "FAILED"})) == "FAILED"
    assert rb.front_status(describe("FAILED", **{"Checkout Front": "FAILED"})) == "FAILED"
    assert rb.front_status(describe("IN_PROGRESS", **{"Build Front": "IN_PROGRESS"})) is None
    assert rb.front_status(describe("FAILED", **{"Build Meveo": "FAILED"})) == "NOT_EXECUTED"


def test_watch_times_out():
    client = FakeClient({"/job/dev/4972/wfapi/describe":
                         lambda: describe("IN_PROGRESS", **{"Build Front": "IN_PROGRESS"})})
    clock = itertools.count(0, 50).__next__
    assert rb.watch(client, "dev", 4972, 100, lambda s: None, clock) == "TIMEOUT"


def test_main_replays_params_and_watches(capsys):
    sleeps = []
    client = FakeClient({
        "/job/dev/4970/api/json": load("build_4970.json"),
        "POST /job/dev/buildWithParameters": {"location": QUEUE},
        QUEUE + "api/json": seq({"why": "waiting"}, {"executable": {"number": 4972}}),
        "/job/dev/4972/wfapi/describe": seq(
            describe("IN_PROGRESS", **{"Build Front": "IN_PROGRESS"}), describe("SUCCESS")),
    })
    code = rb.main(["--branch", "dev", "--from-build", "4970", "--watch"],
                   client=client, sleep=sleeps.append, clock=lambda: 0)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["build"] == 4972 and out["front_status"] == "SUCCESS"
    assert out["url"] == "https://jenkins.example/job/dev/4972/"
    form = dict(client.posts[0][1])
    assert form["to_mail"] == "dev1@example.com,dev2@example.com, dev3@example.com"
    assert form["build_front"] == "true" and form["cc_mail"] == ""
    assert "ASSETS_URL" not in form


def test_main_without_params_refuses(capsys):
    client = FakeClient({"/job/dev/4970/api/json": {"actions": []}})
    assert rb.main(["--from-build", "4970"], client=client) == jc.EXIT_ERROR
    assert client.posts == []

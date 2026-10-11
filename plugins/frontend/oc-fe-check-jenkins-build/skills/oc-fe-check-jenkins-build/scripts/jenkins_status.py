#!/usr/bin/env python3
"""Decide what /oc-fe-check-jenkins-build should do about a branch's latest build.

Prints one JSON object. `action` is what the skill branches on:
  no_builds     the job has never run
  running       the latest build is still running (never analyse an older one)
  green         the latest build succeeded
  not_failed    ABORTED / UNSTABLE / NOT_BUILT — a person's call, not a build break
  out_of_scope  FAILURE outside the frontend stages (or no failed stage at all)
  fix           FAILURE in `Checkout Front` or `Build Front`

`params` are the failed build's actual values (replayed by jenkins_rebuild.py).
`timer_extras` are key=value pairs that only exist in a timer cause's text: the
job does not declare them, so they cannot be replayed and are reported instead.
"""
import argparse
import json
import re
import sys

from jenkins_common import JenkinsError, api, client_from_env, fail, job_path

FRONT_STAGES = ("checkout front", "build front")
PORTAL_REPO = "opencell-portal"
JOB_TREE = "lastBuild[number,building,result,url],property[parameterDefinitions[name]]"
BUILD_TREE = ("number,result,building,url,actions[parameters[name,value],"
              "causes[shortDescription],remoteUrls,lastBuiltRevision[SHA1]]")
TIMER_PREFIX = "Started by timer with parameters:"
KEY_SPLIT = re.compile(r",\s*(?=[A-Za-z_][A-Za-z0-9_]*=)")


def first_failed_stage(stages):
    return next((s for s in stages if s.get("status") == "FAILED"), None)


def is_front(stage):
    return bool(stage) and stage.get("name", "").strip().lower() in FRONT_STAGES


def declared_params(job):
    return [d["name"] for prop in job.get("property") or []
            for d in prop.get("parameterDefinitions") or []]


def _actions(build):
    return [a for a in build.get("actions") or [] if a]


def build_params(build):
    for action in _actions(build):
        if "parameters" in action:
            return {p["name"]: p.get("value") for p in action["parameters"]}
    return {}


def portal_sha(build):
    for action in _actions(build):
        if any(PORTAL_REPO in url for url in action.get("remoteUrls") or []):
            return (action.get("lastBuiltRevision") or {}).get("SHA1")
    return None


def timer_extras(build, declared):
    for action in _actions(build):
        for cause in action.get("causes") or []:
            text = cause.get("shortDescription") or ""
            if text.startswith(TIMER_PREFIX):
                body = text[len(TIMER_PREFIX):].strip().strip("{}")
                pairs = (p.split("=", 1) for p in KEY_SPLIT.split(body) if "=" in p)
                return {k.strip(): v.strip() for k, v in pairs if k.strip() not in declared}
    return {}


def decide(branch, job, build=None, describe=None):
    out = {"branch": branch, "action": None, "build": None, "url": None, "result": None,
           "failed_stage": None, "failed_stage_id": None, "is_front": False,
           "params": {}, "portal_sha": None, "timer_extras": {}}
    last = job.get("lastBuild")
    if not last:
        out["action"] = "no_builds"
        return out
    out.update(build=last["number"], url=last.get("url"), result=last.get("result"))
    if last.get("building"):
        out["action"] = "running"
        return out
    if last.get("result") == "SUCCESS":
        out["action"] = "green"
        return out
    build = build or {}
    stage = first_failed_stage((describe or {}).get("stages") or [])
    out.update(params=build_params(build), portal_sha=portal_sha(build),
               timer_extras=timer_extras(build, declared_params(job)),
               failed_stage=stage["name"] if stage else None,
               failed_stage_id=stage["id"] if stage else None,
               is_front=is_front(stage))
    if last.get("result") != "FAILURE":
        out["action"] = "not_failed"
    else:
        out["action"] = "fix" if out["is_front"] else "out_of_scope"
    return out


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description="Latest Jenkins build of a branch → decision JSON.")
    parser.add_argument("--branch", default="dev", help="Jenkins job / git branch (default: dev)")
    args = parser.parse_args(argv)
    try:
        client = client or client_from_env()
        path = job_path(args.branch)
        job = client.get_json(api(path, JOB_TREE))
        last = job.get("lastBuild")
        build = describe = None
        if last and not last.get("building") and last.get("result") != "SUCCESS":
            build = client.get_json(api(f"{path}/{last['number']}", BUILD_TREE))
            describe = client.get_json(f"{path}/{last['number']}/wfapi/describe")
    except JenkinsError as e:
        return fail(e)
    print(json.dumps(decide(args.branch, job, build, describe), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

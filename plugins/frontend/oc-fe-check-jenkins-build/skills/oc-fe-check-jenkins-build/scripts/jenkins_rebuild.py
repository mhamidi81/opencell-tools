#!/usr/bin/env python3
"""Re-run a Jenkins build with the same parameters, optionally watching its frontend stages.

The parameters are re-read from the source build's ParametersAction and POSTed to
`buildWithParameters`; booleans go as true/false and strings byte-for-byte (to_mail
holds commas and spaces). Values that only appear in a timer cause (ASSETS_URL,
VITE_APP_BASE_URL) are not declared by the job and cannot be replayed.

Concurrent builds are disabled on these jobs, so a queue item may wait for a running
build. That is reported as `queue_why`, never treated as an error.

front_status: SUCCESS | FAILED | ABORTED | UNSTABLE | NOT_EXECUTED | TIMEOUT | null
"""
import argparse
import json
import sys
import time

from jenkins_common import JenkinsError, api, client_from_env, fail, job_path
from jenkins_status import BUILD_TREE, build_params

FRONT_BAD = ("FAILED", "ABORTED", "UNSTABLE")
RUN_FINISHED = ("SUCCESS", "FAILED", "ABORTED", "UNSTABLE", "NOT_EXECUTED")


def form_from_params(params):
    form = []
    for name, value in params.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif value is None:
            value = ""
        form.append((name, str(value)))
    return form


def trigger(client, branch, params):
    headers = client.post_form(f"{job_path(branch)}/buildWithParameters", form_from_params(params))
    location = headers.get("location")
    if not location:
        raise JenkinsError("Jenkins accepted the build but returned no queue Location header")
    return location


def wait_for_start(client, queue_url, deadline, sleep=time.sleep, clock=time.monotonic, poll=10):
    while True:
        item = client.get_json(queue_url.rstrip("/") + "/api/json")
        if item.get("cancelled"):
            raise JenkinsError(f"queue item was cancelled: {queue_url}")
        executable = item.get("executable") or {}
        if executable.get("number"):
            return executable["number"], None
        if clock() >= deadline:
            return None, item.get("why")
        sleep(poll)


def front_status(describe):
    stages = {s.get("name", "").strip().lower(): s.get("status") for s in describe.get("stages") or []}
    for name in ("checkout front", "build front"):
        if stages.get(name) in FRONT_BAD:
            return stages[name]
    if stages.get("build front") == "SUCCESS":
        return "SUCCESS"
    if describe.get("status") in RUN_FINISHED:
        return "NOT_EXECUTED"
    return None


def watch(client, branch, number, deadline, sleep=time.sleep, clock=time.monotonic, poll=30):
    path = f"{job_path(branch)}/{number}/wfapi/describe"
    while True:
        status = front_status(client.get_json(path))
        if status:
            return status
        if clock() >= deadline:
            return "TIMEOUT"
        sleep(poll)


def main(argv=None, client=None, sleep=time.sleep, clock=time.monotonic):
    parser = argparse.ArgumentParser(description="Re-run a build with the same parameters.")
    parser.add_argument("--branch", default="dev")
    parser.add_argument("--from-build", type=int, required=True, help="build whose parameters to replay")
    parser.add_argument("--watch", action="store_true", help="wait for the frontend stages' outcome")
    parser.add_argument("--timeout", type=int, default=2700, help="seconds, queue + watch (default 2700)")
    parser.add_argument("--poll", type=int, default=30, help="seconds between watch polls (default 30)")
    args = parser.parse_args(argv)
    try:
        client = client or client_from_env()
        path = job_path(args.branch)
        params = build_params(client.get_json(api(f"{path}/{args.from_build}", BUILD_TREE)))
        if not params:
            raise JenkinsError(f"build #{args.from_build} has no parameters to replay")
        deadline = clock() + args.timeout
        queue_url = trigger(client, args.branch, params)
        out = {"branch": args.branch, "from_build": args.from_build, "params": params,
               "queue_url": queue_url, "build": None, "url": None, "queue_why": None,
               "front_status": None}
        number, why = wait_for_start(client, queue_url, deadline if args.watch else clock() + 60,
                                     sleep, clock)
        out.update(build=number, queue_why=why)
        if number:
            out["url"] = f"{client.base}{path}/{number}/"
            if args.watch:
                out["front_status"] = watch(client, args.branch, number, deadline,
                                            sleep, clock, args.poll)
    except JenkinsError as e:
        return fail(e)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

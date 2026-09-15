#!/usr/bin/env python3
"""Stage 5 of /oc-bug-clusters: create one Enabler per area, one Sub-task per cluster.

Split deliberately in two. `--plan` computes every payload and prints them, touching
nothing; `--apply` executes a plan. The confirmation gate therefore lives in the skill
between the two calls, rather than as an interactive prompt inside a script that
Claude Code runs non-interactively.
"""
import argparse
import json
import os
import sys
import urllib.parse

from jira_client import JiraClient, JiraError, MissingToken

ENABLER_TYPE_ID = "10076"
SUBTASK_TYPE_ID = "10003"

# Standing owner per area. Pinned by accountId: the Jira assignee field accepts
# nothing else, and display names drift.
DEFAULT_ASSIGNEE = {
    "portal": "5ef5c13914f60e0ac1c9b049",   # Mohamed Hamidi
    "core": "63369fa788ed2ebef97cddfb",     # Adil El Jaouhari
}

LINK_TYPE = "Relates"


def marker_label(area, since, until):
    """The label that makes a re-run of the same window a no-op.

    Built from the area TOKEN (portal/core), never the component name, so the label
    matches the --repo value a user would type.
    """
    return f"bug-clusters-{area}-{since}-{until}"


# ------------------------------------------------------------------------- ADF

def adf_para(text):
    node = {"type": "paragraph"}
    if text:
        node["content"] = [{"type": "text", "text": text}]
    return node


def adf_bullets(items):
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [adf_para(i)]} for i in items]}


def adf_doc(blocks):
    return {"type": "doc", "version": 1, "content": list(blocks)}


# --------------------------------------------------------------------- payloads

def enabler_fields(project, area, model, assignee, report_path):
    window = model["window"]
    data = model["areas"][area]
    overview = [
        f"{c['subject']} — {c['count']} bugs "
        f"({c['open']} open, {c['closed']} closed), "
        f"{c['first_created']} → {c['last_created']}"
        for c in data["clusters"]
    ]
    return {
        "project": {"key": project},
        "issuetype": {"id": ENABLER_TYPE_ID},
        "summary": (f"Bug clusters — {data['component']} — "
                    f"{window['since']} → {window['until']}"),
        "components": [{"name": data["component"]}],
        "assignee": {"id": assignee},
        "labels": [marker_label(area, window["since"], window["until"])],
        "description": adf_doc([
            adf_para(f"Bugs created {window['since']} → {window['until']} "
                     f"(exclusive) in {', '.join(model['projects'])}, "
                     f"component {data['component']}."),
            adf_para(f"{data['clustered_bugs']} of {data['bugs']} bugs fall into "
                     f"{len(data['clusters'])} cluster(s) of at least "
                     f"{model['min_cluster']} bugs on one subject."),
            adf_bullets(overview),
            adf_para(f"Full report: {report_path}"),
        ]),
    }


def subtask_fields(project, cluster, assignee):
    """Sub-task payload WITHOUT `parent` — the applier injects it once the Enabler
    key exists."""
    return {
        "project": {"key": project},
        "issuetype": {"id": SUBTASK_TYPE_ID},
        "summary": f"{cluster['subject']} — {cluster['count']} bugs",
        "assignee": {"id": assignee},
        "description": adf_doc([
            adf_para(f"{cluster['count']} bugs classified as "
                     f"'{cluster['subject']}' "
                     f"({cluster['open']} open, {cluster['closed']} closed), "
                     f"raised {cluster['first_created']} → {cluster['last_created']}."),
            adf_bullets([f"{b['key']} — {b['summary']}" for b in cluster["bugs"]]),
        ]),
    }


def build_plan(model, project, assignees, report_path):
    areas, calls = [], 0
    for area, data in model["areas"].items():
        if not data["clusters"]:
            continue
        assignee = assignees[area]
        subtasks = [{"subject": c["subject"],
                     "fields": subtask_fields(project, c, assignee),
                     "links": [b["key"] for b in c["bugs"]]}
                    for c in data["clusters"]]
        areas.append({
            "area": area,
            "component": data["component"],
            "marker": marker_label(area, model["window"]["since"],
                                   model["window"]["until"]),
            "assignee": assignee,
            "enabler": {"fields": enabler_fields(project, area, model, assignee,
                                                 report_path)},
            "subtasks": subtasks,
        })
        calls += 1 + len(subtasks) + sum(len(s["links"]) for s in subtasks)
    return {"project": project, "calls": calls, "areas": areas}


def render_plan(plan):
    if not plan["areas"]:
        return "No cluster reached the threshold — nothing to create.\n"
    out = [f"Will create in {plan['project']} ({plan['calls']} API calls):", ""]
    for area in plan["areas"]:
        out.append(f"  Enabler  {area['enabler']['fields']['summary']}")
        out.append(f"           component {area['component']} · "
                   f"assignee {area['assignee']} · label {area['marker']}")
        for subtask in area["subtasks"]:
            out.append(f"    Sub-task  {subtask['fields']['summary']}  "
                       f"(+{len(subtask['links'])} '{LINK_TYPE}' links)")
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- createmeta guard

def required_field_ids(meta):
    """Field ids Jira demands and will not fill in itself."""
    return {f["fieldId"] for f in meta.get("fields") or []
            if f.get("required") and not f.get("hasDefaultValue")}


def missing_required(meta, fields):
    return required_field_ids(meta) - set(fields)


# --------------------------------------------------------------- assignee lookup

def resolve_assignee(client, value):
    """Accept an accountId or an email. An email that matches no user raises — a
    silent fallback here would assign the Enabler to nobody without saying so."""
    if "@" not in value:
        return value
    query = urllib.parse.quote(value)
    users = client.get(f"/rest/api/3/user/search?query={query}") or []
    exact = [u for u in users
             if (u.get("emailAddress") or "").lower() == value.lower()]
    for candidate in (exact, users):
        if len(candidate) == 1:
            return candidate[0]["accountId"]
    raise JiraError(f"'{value}' matches no Jira user (or several); "
                    f"pass an accountId instead")


# ------------------------------------------------------------------ idempotency

def existing_enabler(client, project, marker):
    jql = (f'project = {project} AND issuetype = Enabler '
           f'AND labels = "{marker}" ORDER BY created DESC')
    for issue in client.search(jql, ["summary"]):
        return issue["key"]
    return None


# --------------------------------------------------------------------- preflight

def _createmeta(client, project, type_id):
    return client.get(
        f"/rest/api/3/issue/createmeta/{project}/issuetypes/{type_id}")


def preflight(client, project, plan):
    """Fail before the first write if Jira wants a field the payload has no value for."""
    checks = []
    for area in plan["areas"]:
        checks.append((ENABLER_TYPE_ID, area["enabler"]["fields"]))
        for subtask in area["subtasks"]:
            # `parent` is injected at creation time; declare it so the guard
            # does not report it as missing.
            checks.append((SUBTASK_TYPE_ID, dict(subtask["fields"], parent=True)))
    for type_id, fields in checks:
        missing = missing_required(_createmeta(client, project, type_id), fields)
        if missing:
            raise JiraError(
                f"issue type {type_id} in {project} requires "
                f"{sorted(missing)}, which /oc-bug-clusters does not set. "
                f"Nothing was created.")


# ------------------------------------------------------------------------- apply

def new_state():
    return {"enablers": {}, "subtasks": {}, "links": [], "warnings": [],
            "project": None, "markers": []}


def _create(client, fields, state):
    """Create an issue, retrying once without the assignee if Jira refuses it."""
    try:
        return client.post("/rest/api/3/issue", {"fields": fields})["key"]
    except JiraError as ex:
        if "assignee" not in str(ex).lower() or "assignee" not in fields:
            raise
        state["warnings"].append(
            f"Jira refused assignee {fields['assignee']} on "
            f"'{fields['summary']}' — created unassigned. ({ex})")
        retry = {k: v for k, v in fields.items() if k != "assignee"}
        return client.post("/rest/api/3/issue", {"fields": retry})["key"]


def apply_plan(client, plan, state, force=False):
    plan_markers = sorted(a["marker"] for a in plan["areas"])

    if state["enablers"] or state["subtasks"]:
        if (state.get("project") is not None
                and (state.get("project") != plan["project"]
                     or state.get("markers") != plan_markers)):
            raise JiraError(
                f"--state was created for project {state.get('project')!r} "
                f"(markers {state.get('markers')!r}), but this plan targets "
                f"project {plan['project']!r} (markers {plan_markers!r}). "
                f"This state file belongs to a different run — point --state "
                f"at a state file for this window instead.")

    if state.get("project") is None:
        state["project"] = plan["project"]
        state["markers"] = plan_markers

    for area in plan["areas"]:
        token = area["area"]

        if token not in state["enablers"]:
            if not force:
                found = existing_enabler(client, plan["project"], area["marker"])
                if found:
                    state["warnings"].append(
                        f"{area['component']}: {found} already carries label "
                        f"{area['marker']} — skipped. Use --force to create another.")
                    continue
            state["enablers"][token] = _create(client, area["enabler"]["fields"], state)

        enabler_key = state["enablers"][token]

        for subtask in area["subtasks"]:
            slot = f"{token}/{subtask['subject']}"
            if slot not in state["subtasks"]:
                fields = dict(subtask["fields"], parent={"key": enabler_key})
                state["subtasks"][slot] = _create(client, fields, state)
            subtask_key = state["subtasks"][slot]

            for bug_key in subtask["links"]:
                edge = f"{bug_key}->{subtask_key}"
                if edge in state["links"]:
                    continue
                try:
                    client.post("/rest/api/3/issueLink", {
                        "type": {"name": LINK_TYPE},
                        "inwardIssue": {"key": bug_key},
                        "outwardIssue": {"key": subtask_key}})
                    state["links"].append(edge)
                except JiraError as ex:
                    # Best effort: a missing link is cosmetic, a half-created
                    # Enabler is not. Collect and carry on.
                    state["warnings"].append(f"link {edge} failed: {ex}")
    return state


# --------------------------------------------------------------------------- CLI

def _load_state(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    return new_state()


def _save_state(path, state):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create Enablers from a cluster model.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--project", default="INTRD")
    parser.add_argument("--report-path", default="")
    parser.add_argument("--assignee-portal", default=DEFAULT_ASSIGNEE["portal"])
    parser.add_argument("--assignee-core", default=DEFAULT_ASSIGNEE["core"])
    parser.add_argument("--state", required=True)
    parser.add_argument("--force", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if "," in args.project:
        sys.stderr.write(
            f"--project must be a single key (got {args.project!r}); an Enabler "
            f"is created in exactly one project. Pass e.g. --project INTRD.\n")
        return 2

    with open(args.model, encoding="utf-8") as handle:
        model = json.load(handle)

    try:
        client = JiraClient()
        assignees = {"portal": resolve_assignee(client, args.assignee_portal),
                     "core": resolve_assignee(client, args.assignee_core)}
    except (MissingToken, JiraError) as ex:
        sys.stderr.write(f"{ex}\n")
        return 2

    plan = build_plan(model, args.project, assignees, args.report_path)

    if args.plan:
        sys.stdout.write(render_plan(plan))
        return 0

    if not plan["areas"]:
        sys.stdout.write(render_plan(plan))
        return 0

    state = _load_state(args.state)
    try:
        preflight(client, args.project, plan)
        state = apply_plan(client, plan, state, force=args.force)
    finally:
        _save_state(args.state, state)

    for area, key in state["enablers"].items():
        sys.stdout.write(f"{area}: {model['areas'][area]['component']} Enabler {key}\n")
    for slot, key in state["subtasks"].items():
        sys.stdout.write(f"  {slot}: {key}\n")
    sys.stdout.write(f"{len(state['links'])} bug links created\n")
    for warning in state["warnings"]:
        sys.stderr.write(f"WARNING: {warning}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

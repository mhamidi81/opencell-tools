#!/usr/bin/env python3
"""Stage 5 of /oc-bug-clusters: create one Enabler per area, one Sub-task per cluster.

Split deliberately in two. `--plan` computes every payload and prints them, touching
nothing; `--apply` executes a plan. The confirmation gate therefore lives in the skill
between the two calls, rather than as an interactive prompt inside a script that
Claude Code runs non-interactively.
"""
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

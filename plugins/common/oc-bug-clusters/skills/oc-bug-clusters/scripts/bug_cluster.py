#!/usr/bin/env python3
"""Stage 4 of /oc-bug-clusters: bugs + subject assignments -> the cluster model.

No network, no rendering. The model is the one shape the Markdown/CSV/HTML
renderers and the Jira writer all read, so it is built once and asserted here.
"""
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
from collections import Counter
from datetime import date

from bug_fetch import AREA_COMPONENT, areas_in_scope

AREA_ORDER = ["portal", "core"]
SUBJECT_HEADING = re.compile(r"^## ([a-z0-9-]+)$", re.M)
TOP_LABELS = 3


class MissingAssignments(RuntimeError):
    """A classifiable bug came back with no subject.

    Raised rather than dropped: a silently missing bug is one that never reaches a
    cluster and never reaches the report, which is indistinguishable from a bug that
    genuinely had no peers.
    """

    def __init__(self, keys):
        self.keys = list(keys)
        shown = ", ".join(self.keys[:10])
        more = f" (+{len(self.keys) - 10} more)" if len(self.keys) > 10 else ""
        super().__init__(f"no subject assigned for: {shown}{more}")


def seeded_subjects(path):
    with open(path, encoding="utf-8") as handle:
        return SUBJECT_HEADING.findall(handle.read())


def _group(subject, bugs, seeded):
    bugs = sorted(bugs, key=lambda b: (b["created"], b["key"]), reverse=True)
    labels = Counter(label for b in bugs for label in b["labels"])
    dates = sorted(b["created"] for b in bugs if b["created"])
    closed = sum(1 for b in bugs if b["status_category"] == "done")
    return {
        "subject": subject,
        "count": len(bugs),
        "bugs": bugs,
        "open": len(bugs) - closed,
        "closed": closed,
        "labels": [[name, n] for name, n in labels.most_common(TOP_LABELS)],
        "first_created": dates[0] if dates else "",
        "last_created": dates[-1] if dates else "",
        "is_new": subject not in set(seeded),
    }


def build_model(document, assignments, min_cluster, seeded=()):
    bugs = document["bugs"]
    classifiable = [b for b in bugs if b["area"] is not None]
    missing = [b["key"] for b in classifiable if b["key"] not in assignments]
    if missing:
        raise MissingAssignments(missing)

    scope = [a for a in AREA_ORDER if a in areas_in_scope(document["repo"])]

    areas = {}
    for area in scope:
        mine = [b for b in classifiable if b["area"] == area]
        by_subject = {}
        for b in mine:
            by_subject.setdefault(assignments[b["key"]], []).append(b)
        groups = [_group(subject, members, seeded)
                  for subject, members in by_subject.items()]
        groups.sort(key=lambda g: (-g["count"], g["subject"]))
        clusters = [g for g in groups if g["count"] >= min_cluster]
        areas[area] = {
            "component": AREA_COMPONENT[area],
            "bugs": len(mine),
            "clustered_bugs": sum(g["count"] for g in clusters),
            "clusters": clusters,
            "near": [g for g in groups if g["count"] < min_cluster],
        }

    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "min_cluster": min_cluster,
        "fetched": document["fetched"],
        "dropped_invalid": document["dropped_invalid"],
        "kept": len(bugs),
        "areas": areas,
        "unclassified": sorted((b for b in bugs if b["area"] is None),
                               key=lambda b: b["key"]),
    }


# --------------------------------------------------------------------- Markdown

def _window_line(model):
    w = model["window"]
    return (f"**{', '.join(model['projects'])}** · bugs created "
            f"`{w['since']}` → `{w['until']}` (exclusive) · "
            f"cluster threshold **{model['min_cluster']}**")


def _counter_line(model):
    unclassified = len(model["unclassified"])
    # "rejected", not "Invalid/Duplicate": the filter also drops resolution
    # Declined and status Invalid, and on real data every dropped bug was
    # Declined — naming only two of the four reasons misinforms the reader.
    return (f"Fetched **{model['fetched']}** · dropped as rejected "
            f"**{model['dropped_invalid']}** · kept **{model['kept']}** · "
            f"no resolvable area **{unclassified}**")


def _group_line(group):
    labels = ", ".join(f"{name} ×{n}" for name, n in group["labels"]) or "—"
    flag = " **(new subject)**" if group["is_new"] else ""
    return (f"| `{group['subject']}`{flag} | {group['count']} | {group['open']} | "
            f"{group['closed']} | {labels} | {group['first_created']} → "
            f"{group['last_created']} |")


def render_markdown(model):
    out = ["# Bug clusters", "", _window_line(model), "", _counter_line(model), ""]

    for area, data in model["areas"].items():
        out += [f"## {data['component']} (`{area}`) — {data['bugs']} bugs", ""]
        if not data["clusters"]:
            out += [f"_No cluster reached {model['min_cluster']} bugs._", ""]
        else:
            out += [f"{data['clustered_bugs']} of {data['bugs']} bugs fall into "
                    f"{len(data['clusters'])} cluster(s).", "",
                    "| Subject | Bugs | Open | Closed | Top labels | Span |",
                    "|---|---:|---:|---:|---|---|"]
            out += [_group_line(g) for g in data["clusters"]]
            out.append("")
            for cluster in data["clusters"]:
                out += [f"### `{cluster['subject']}` — {cluster['count']} bugs", ""]
                for b in cluster["bugs"]:
                    out.append(f"- [{b['key']}]({b['url']}) · {b['status']} · "
                               f"{b['created']} · {b['assignee'] or '—'} · "
                               f"{b['summary']}")
                out.append("")
        if data["near"]:
            out += [f"**Near-clusters** (below {model['min_cluster']}): "
                    + ", ".join(f"`{g['subject']}` {g['count']}" for g in data["near"]),
                    ""]

    if model["unclassified"]:
        out += [f"## Unclassified — {len(model['unclassified'])} bugs", "",
                "_No Jira component and no leading `[front]`/`[back]` tag, so these "
                "were not clustered._", ""]
        out += [f"- [{b['key']}]({b['url']}) · {b['summary']}"
                for b in model["unclassified"]]
        out.append("")

    return "\n".join(out)


# -------------------------------------------------------------------------- CSV

CSV_HEADER = ["key", "area", "component", "subject", "in_cluster", "status",
              "created", "assignee", "labels", "summary", "url"]


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]

    def row(bug, area, subject, in_cluster):
        return [bug["key"], area or "", bug["component"] or "", subject or "",
                "yes" if in_cluster else "no", bug["status"] or "", bug["created"],
                bug["assignee"] or "", " ".join(bug["labels"]), bug["summary"],
                bug["url"]]

    for area, data in model["areas"].items():
        for group in data["clusters"]:
            rows += [row(b, area, group["subject"], True) for b in group["bugs"]]
        for group in data["near"]:
            rows += [row(b, area, group["subject"], False) for b in group["bugs"]]
    rows += [row(b, None, None, False) for b in model["unclassified"]]
    return rows


# ------------------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f7f7f8;--fg:#1d1d1f;--mut:#6b6b72;--line:#e3e3e6;--card:#fff;--accent:#2f6fd0}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
h3{font-size:14px;margin:20px 0 6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.meta{color:var(--mut);margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:16px 18px;margin-bottom:18px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);
 vertical-align:top}
th{color:var(--mut);font-weight:600;white-space:nowrap}
td.n,th.n{text-align:right}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.sub{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.new{background:#fde7c7;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.pill{background:#eef1f5;border-radius:4px;padding:1px 6px;font-size:12px;color:var(--mut)}
.tabs{display:flex;gap:6px;margin:18px 0 12px}
.tab{padding:7px 14px;border:1px solid var(--line);border-radius:8px;cursor:pointer;
 background:var(--card)}
.tab[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--mut);font-style:italic}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ededf0;--mut:#9a9aa3;
 --line:#2c2c31;--card:#1c1c20;--accent:#6ea8ff}.new{background:#5a4420}
 .pill{background:#26262b}}
"""

TAB_JS = """
document.querySelectorAll('.tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(t){
      t.setAttribute('aria-selected', String(t === tab));
    });
    document.querySelectorAll('section[data-area]').forEach(function(s){
      s.hidden = s.dataset.area !== tab.dataset.area;
    });
  });
});
"""


def _e(value):
    return html_mod.escape(str(value if value is not None else ""))


def _bug_rows_html(bugs):
    out = []
    for b in bugs:
        out.append(
            f'<tr><td><a href="{_e(b["url"])}">{_e(b["key"])}</a></td>'
            f'<td>{_e(b["summary"])}</td><td>{_e(b["status"])}</td>'
            f'<td>{_e(b["created"])}</td><td>{_e(b["assignee"] or "—")}</td></tr>')
    return "".join(out)


def _area_html(model, area, data):
    parts = [f'<section data-area="{_e(area)}">',
             f'<h2>{_e(data["component"])} — {data["bugs"]} bugs</h2>']

    if not data["clusters"]:
        parts.append(f'<p class="empty">No cluster reached '
                     f'{model["min_cluster"]} bugs.</p>')
    else:
        parts.append('<div class="card"><table><tr><th>Subject</th>'
                     '<th class="n">Bugs</th><th class="n">Open</th>'
                     '<th class="n">Closed</th><th>Top labels</th><th>Span</th></tr>')
        for g in data["clusters"]:
            flag = '<span class="new">new</span>' if g["is_new"] else ""
            labels = ", ".join(f"{_e(n)} ×{c}" for n, c in g["labels"]) or "—"
            parts.append(
                f'<tr><td><span class="sub">{_e(g["subject"])}</span>{flag}</td>'
                f'<td class="n">{g["count"]}</td><td class="n">{g["open"]}</td>'
                f'<td class="n">{g["closed"]}</td><td>{labels}</td>'
                f'<td>{_e(g["first_created"])} → {_e(g["last_created"])}</td></tr>')
        parts.append("</table></div>")

        for g in data["clusters"]:
            parts.append(f'<h3>{_e(g["subject"])} — {g["count"]} bugs</h3>'
                         '<div class="card"><table><tr><th>Key</th><th>Summary</th>'
                         '<th>Status</th><th>Created</th><th>Assignee</th></tr>'
                         + _bug_rows_html(g["bugs"]) + "</table></div>")

    if data["near"]:
        pills = " ".join(f'<span class="pill">{_e(g["subject"])} {g["count"]}</span>'
                         for g in data["near"])
        parts.append(f'<h3>Near-clusters (below {model["min_cluster"]})</h3>'
                     f'<div class="card">{pills}</div>')

    parts.append("</section>")
    return "".join(parts)


def render_html(model):
    w = model["window"]
    title = f"Bug clusters {w['since']} → {w['until']}"
    areas = list(model["areas"].items())

    body = [f"<h1>{_e(title)}</h1>",
            f'<p class="meta">{_e(", ".join(model["projects"]))} · threshold '
            f'{model["min_cluster"]} · fetched {model["fetched"]} · dropped '
            f'{model["dropped_invalid"]} rejected · kept {model["kept"]} · generated '
            f'{_e(date.today().isoformat())}</p>']

    if len(areas) > 1:
        body.append('<div class="tabs">' + "".join(
            f'<div class="tab" data-area="{_e(a)}" role="tab" '
            f'aria-selected="{"true" if i == 0 else "false"}">{_e(d["component"])}'
            f'</div>' for i, (a, d) in enumerate(areas)) + "</div>")

    for index, (area, data) in enumerate(areas):
        section = _area_html(model, area, data)
        if len(areas) > 1 and index > 0:
            section = section.replace(f'<section data-area="{_e(area)}">',
                                      f'<section data-area="{_e(area)}" hidden>', 1)
        body.append(section)

    if model["unclassified"]:
        body.append(f'<h2>Unclassified — {len(model["unclassified"])} bugs</h2>'
                    '<p class="meta">No Jira component and no leading '
                    '<code>[front]</code>/<code>[back]</code> tag, so these were not '
                    'clustered.</p><div class="card"><table>'
                    '<tr><th>Key</th><th>Summary</th><th>Status</th><th>Created</th>'
                    '<th>Assignee</th></tr>'
                    + _bug_rows_html(model["unclassified"]) + "</table></div>")

    script = f"<script>{TAB_JS}</script>" if len(areas) > 1 else ""
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_e(title)}</title><style>{CSS}</style></head><body>"
            + "".join(body) + script + "</body></html>\n")


# -------------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="Cluster classified bugs and report.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--assignments", required=True)
    parser.add_argument("--subjects", required=True)
    parser.add_argument("--min-cluster", type=int, default=5)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        document = json.load(handle)
    with open(args.assignments, encoding="utf-8") as handle:
        assignments = json.load(handle)

    try:
        model = build_model(document, assignments, args.min_cluster,
                            seeded_subjects(args.subjects))
    except MissingAssignments as ex:
        sys.stderr.write(f"{ex}\nClassify these and re-run.\n")
        return 2

    for path in (args.out, args.csv, args.model):
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)

    with open(args.model, "w", encoding="utf-8") as handle:
        json.dump(model, handle, ensure_ascii=False, indent=1)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render_html(model))
    with open(args.csv, "w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(render_csv_rows(model))

    sys.stdout.write(render_markdown(model))
    sys.stderr.write(f"\nHTML: {args.out}\nCSV:  {args.csv}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

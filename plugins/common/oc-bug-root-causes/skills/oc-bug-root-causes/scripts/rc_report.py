#!/usr/bin/env python3
"""Stage 4 of /oc-bug-root-causes: assignments + evidence -> the ranking model -> reports.

No network. The classification is the only LLM judgement in the command, and it arrives
in several parts (one per sub-agent batch), so this module refuses to report on anything
it cannot account for: a missing key, a key outside the run, a key classified two ways,
or a coined category too small to be one. A silently missing bug would look exactly like
a category that did not happen.
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

from bug_fetch import areas_in_scope

INSUFFICIENT = "insufficient-evidence"
MIN_NEW = 5
CAUSE_LIMIT = 120
EXAMPLES = 5
AREA_ORDER = ["portal", "core"]
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
NEW_DEFINITION = "New category coined in this run — add it to references/dev-root-causes.md."


class AssignmentError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def load_taxonomy(path):
    """Ordered {name: definition}; the definition is the first paragraph under the heading."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    taxonomy = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        name = heading.strip()
        if not KEBAB.fullmatch(name):
            continue
        paragraph = body.strip().split("\n\n", 1)[0]
        taxonomy[name] = " ".join(paragraph.split())
    return taxonomy


def _shown(keys):
    keys = list(keys)
    more = f" (+{len(keys) - 10} more)" if len(keys) > 10 else ""
    return ", ".join(keys[:10]) + more


def merge_assignments(parts):
    merged, conflicts = {}, set()
    for part in parts:
        for key, value in part.items():
            if key in merged and merged[key] != value:
                conflicts.add(key)
            merged[key] = value
    if conflicts:
        raise AssignmentError([f"classified differently in two parts: {_shown(sorted(conflicts))}"])
    return merged


def validate(keys, assignments, taxonomy, min_new=MIN_NEW):
    """Raise AssignmentError listing every problem; return the new categories."""
    problems = []
    known = set(keys)
    missing = [k for k in keys if k not in assignments]
    if missing:
        problems.append(f"no category assigned for: {_shown(missing)}")
    outside = sorted(k for k in assignments if k not in known)
    if outside:
        problems.append(f"assignments for bugs not in this run: {_shown(outside)}")

    coined = Counter()
    for key in keys:
        if key not in assignments:
            continue
        entry = assignments[key]
        if not isinstance(entry, dict):
            problems.append(f"{key}: the assignment must be an object")
            continue
        category = entry.get("category")
        if not isinstance(category, str) or not KEBAB.fullmatch(category):
            problems.append(f"{key}: category must be lower-kebab-case, got {category!r}")
        elif category not in taxonomy:
            coined[category] += 1
        if entry.get("confidence") not in ("high", "low"):
            problems.append(f"{key}: confidence must be 'high' or 'low'")
        if not isinstance(entry.get("regression"), bool):
            problems.append(f"{key}: regression must be true or false")
        cause = entry.get("cause")
        if not isinstance(cause, str) or not cause.strip():
            problems.append(f"{key}: cause must be a non-empty line")

    for category, count in sorted(coined.items()):
        if count < min_new:
            problems.append(f"unknown category '{category}' on {count} bug(s): use a seeded "
                            f"category, or coin a new one only for >= {min_new} bugs")
    if problems:
        raise AssignmentError(problems)
    return sorted(coined)


def _merge(bugs, rows, assignments):
    evidence = {r["key"]: r for r in rows}
    merged = []
    for b in bugs:
        entry = assignments[b["key"]]
        row = evidence.get(b["key"]) or {}
        merged.append({**b, "category": entry["category"], "confidence": entry["confidence"],
                       "regression": entry["regression"],
                       "cause": entry["cause"].strip()[:CAUSE_LIMIT],
                       "evidence": row.get("evidence") or "jira",
                       "pr_url": row.get("pr_url")})
    return merged


def _examples(members):
    newest = sorted(members, key=lambda b: (b["created"], b["key"]), reverse=True)
    return sorted(newest, key=lambda b: b["evidence"] != "pr")[:EXAMPLES]


def ranking(bugs, taxonomy, new=()):
    total = len(bugs)
    groups = {}
    for b in bugs:
        groups.setdefault(b["category"], []).append(b)
    rows = []
    for category, members in groups.items():
        count = len(members)
        regressions = sum(1 for b in members if b["regression"])
        rows.append({
            "category": category,
            "definition": taxonomy.get(category, NEW_DEFINITION),
            "is_new": category in set(new),
            "count": count,
            "share": count / total if total else 0.0,
            "areas": {"portal": sum(1 for b in members if b["area"] == "portal"),
                      "core": sum(1 for b in members if b["area"] == "core"),
                      "none": sum(1 for b in members if b["area"] is None)},
            "regression": regressions,
            "regression_rate": regressions / count,
            "evidence": {"pr": sum(1 for b in members if b["evidence"] == "pr"),
                         "jira": sum(1 for b in members if b["evidence"] != "pr")},
            "low_confidence": sum(1 for b in members if b["confidence"] == "low"),
            "examples": _examples(members),
        })
    rows.sort(key=lambda r: (r["category"] == INSUFFICIENT, -r["count"], r["category"]))
    return rows


def build_model(document, rows, assignments, taxonomy, new=()):
    bugs = _merge(document["bugs"], rows, assignments)
    views = {"all": ranking(bugs, taxonomy, new)}
    for area in AREA_ORDER:
        if area in areas_in_scope(document["repo"]):
            views[area] = ranking([b for b in bugs if b["area"] == area], taxonomy, new)
    return {
        "window": document["window"],
        "projects": document["projects"],
        "repo": document["repo"],
        "total": len(bugs),
        "evidence": {"pr": sum(1 for b in bugs if b["evidence"] == "pr"),
                     "jira": sum(1 for b in bugs if b["evidence"] != "pr")},
        "regression": sum(1 for b in bugs if b["regression"]),
        "new_categories": list(new),
        "views": views,
        "insufficient": sorted((b for b in bugs if b["category"] == INSUFFICIENT),
                               key=lambda b: (b["created"], b["key"]), reverse=True),
        "no_area": [b for b in bugs if b["area"] is None],
        "bugs": bugs,
    }


# --------------------------------------------------------------------- Markdown

AREA_LABEL = {"portal": "Frontend", "core": "Backend", None: "No area"}
VIEW_TITLE = {"all": "all areas", "portal": "Frontend", "core": "Backend"}
RANK_HEAD = ["| Category | Bugs | Share | Frontend | Backend | No area | Regressions "
             "| Evidence (PR / Jira) | Low conf. |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]


def _md(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _shown_views(model):
    """A single-area run has views {all, <area>} holding the same bugs: show one."""
    views = model["views"]
    return [(v, rows) for v, rows in views.items() if v == "all" or len(views) > 2]


def _rank_row(r):
    flag = " **(new)**" if r["is_new"] else ""
    areas = r["areas"]
    return (f"| `{r['category']}`{flag} | {r['count']} | {r['share']:.1%} | "
            f"{areas['portal']} | {areas['core']} | {areas['none']} | "
            f"{r['regression']} ({r['regression_rate']:.0%}) | "
            f"{r['evidence']['pr']} / {r['evidence']['jira']} | {r['low_confidence']} |")


def _example_line(b):
    parts = [f"[{b['key']}]({b['url']})", AREA_LABEL[b["area"]]]
    if b["regression"]:
        parts.append("regression")
    if b["confidence"] == "low":
        parts.append("low confidence")
    if b["pr_url"]:
        parts.append(f"[PR]({b['pr_url']})")
    return f"- {' · '.join(parts)} — {_md(b['cause'])} — _{_md(b['summary'])}_"


def render_markdown(model):
    w, ev = model["window"], model["evidence"]
    out = ["# Development-issue root causes", "",
           f"**{', '.join(model['projects'])}** · \"Development issue\" bugs created "
           f"`{w['since']}` → `{w['until']}` (exclusive) · repo **{model['repo']}**", "",
           f"**{model['total']}** bugs · PR evidence **{ev['pr']}** · Jira-only "
           f"**{ev['jira']}** · regressions **{model['regression']}** · insufficient "
           f"evidence **{len(model['insufficient'])}**", ""]

    for view, rows in _shown_views(model):
        out += [f"## Ranking — {VIEW_TITLE[view]}", ""]
        out += (RANK_HEAD + [_rank_row(r) for r in rows]) if rows else ["_No bugs._"]
        out.append("")

    out += ["## Categories", ""]
    for r in model["views"]["all"]:
        if r["category"] == INSUFFICIENT:
            continue
        out += [f"### `{r['category']}` — {r['count']} bugs", "", f"_{_md(r['definition'])}_", ""]
        out += [_example_line(b) for b in r["examples"]]
        out.append("")

    if model["insufficient"]:
        out += [f"## Insufficient evidence — {len(model['insufficient'])} bugs", "",
                "_Neither Jira nor the PR shows the mistake. Filling in these tickets makes "
                "the next run sharper._", ""]
        out += [f"- [{b['key']}]({b['url']}) · {AREA_LABEL[b['area']]} · {_md(b['summary'])}"
                for b in model["insufficient"]]
        out.append("")

    if model["no_area"]:
        out += [f"## No resolvable area — {len(model['no_area'])} bugs", "",
                "_No Jira component and no leading `[front]`/`[back]` tag. They are ranked "
                "under \"No area\"._", ""]
        out += [f"- [{b['key']}]({b['url']}) · `{b['category']}` · {_md(b['summary'])}"
                for b in model["no_area"]]
        out.append("")

    if model["new_categories"]:
        out += ["## New categories", "",
                "Coined in this run — add them to `references/dev-root-causes.md` to keep them: "
                + ", ".join(f"`{c}`" for c in model["new_categories"]), ""]
    return "\n".join(out)


# -------------------------------------------------------------------------- CSV

CSV_HEADER = ["key", "area", "category", "confidence", "regression", "evidence", "pr_url",
              "cause", "status", "created", "assignee", "summary", "url"]


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]
    for b in model["bugs"]:
        rows.append([b["key"], b["area"] or "", b["category"], b["confidence"],
                     "yes" if b["regression"] else "no", b["evidence"], b["pr_url"] or "",
                     b["cause"], b.get("status") or "", b.get("created") or "",
                     b.get("assignee") or "", b.get("summary") or "", b.get("url") or ""])
    return rows


# ------------------------------------------------------------------------- HTML

CSS = """
:root{color-scheme:light dark;--bg:#f7f7f8;--fg:#1d1d1f;--mut:#6b6b72;--line:#e3e3e6;--card:#fff;--accent:#2f6fd0;
 --newbg:#fde7c7;--pill:#eef1f5}
*{box-sizing:border-box}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);
 font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1100px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
h3{font-size:14px;margin:20px 0 4px}
.meta,.def{color:var(--mut)}.meta{margin-bottom:18px}.def{margin:0 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:12px 16px;margin-bottom:18px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.sub{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.new{background:var(--newbg);border-radius:4px;padding:1px 6px;font-size:11px;margin-left:6px}
.pill{background:var(--pill);border-radius:4px;padding:1px 6px;font-size:12px;color:var(--mut)}
.tabs{display:flex;gap:6px;margin:18px 0 12px;flex-wrap:wrap}
.tab{font:inherit;padding:7px 14px;border:1px solid var(--line);border-radius:8px;
 cursor:pointer;background:var(--card);color:var(--fg)}
.tab[aria-selected="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--mut);font-style:italic}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ededf0;--mut:#9a9aa3;
 --line:#2c2c31;--card:#1c1c20;--accent:#6ea8ff;--newbg:#5a4420;--pill:#26262b}}
"""

TAB_JS = """
document.querySelectorAll('.tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(t){
      t.setAttribute('aria-selected', String(t === tab));
    });
    document.querySelectorAll('section[data-view]').forEach(function(s){
      s.hidden = s.dataset.view !== tab.dataset.view;
    });
  });
});
"""


def _e(value):
    return html_mod.escape(str(value if value is not None else ""))


def _link(url, text):
    return f'<a href="{_e(url)}">{_e(text)}</a>' if url else "—"


def _rank_html(rows):
    if not rows:
        return '<p class="empty">No bugs.</p>'
    head = ('<tr><th>Category</th><th class="n">Bugs</th><th class="n">Share</th>'
            '<th class="n">Frontend</th><th class="n">Backend</th><th class="n">No area</th>'
            '<th class="n">Regressions</th><th class="n">PR / Jira</th>'
            '<th class="n">Low conf.</th></tr>')
    body = []
    for r in rows:
        flag = '<span class="new">new</span>' if r["is_new"] else ""
        a = r["areas"]
        body.append(
            f'<tr><td><span class="sub">{_e(r["category"])}</span>{flag}</td>'
            f'<td class="n">{r["count"]}</td><td class="n">{r["share"]:.1%}</td>'
            f'<td class="n">{a["portal"]}</td><td class="n">{a["core"]}</td>'
            f'<td class="n">{a["none"]}</td>'
            f'<td class="n">{r["regression"]} ({r["regression_rate"]:.0%})</td>'
            f'<td class="n">{r["evidence"]["pr"]} / {r["evidence"]["jira"]}</td>'
            f'<td class="n">{r["low_confidence"]}</td></tr>')
    return '<div class="card"><table>' + head + "".join(body) + "</table></div>"


def _bug_table(bugs, with_cause):
    head = "<tr><th>Key</th><th>Area</th>"
    head += "<th>Cause</th><th>PR</th>" if with_cause else ""
    head += "<th>Summary</th></tr>"
    body = []
    for b in bugs:
        tags = " ".join(f'<span class="pill">{t}</span>' for t, on in
                        (("regression", b["regression"]), ("low", b["confidence"] == "low")) if on)
        row = f"<tr><td>{_link(b['url'], b['key'])}</td><td>{_e(AREA_LABEL[b['area']])}</td>"
        if with_cause:
            row += f"<td>{_e(b['cause'])} {tags}</td><td>{_link(b['pr_url'], 'PR')}</td>"
        row += f"<td>{_e(b['summary'])}</td></tr>"
        body.append(row)
    return '<div class="card"><table>' + head + "".join(body) + "</table></div>"


def render_html(model, today=None):
    today = today or date.today().isoformat()
    w, ev = model["window"], model["evidence"]
    title = f"Development-issue root causes — {w['since']} → {w['until']}"
    views = _shown_views(model)

    body = [f"<h1>{_e(title)}</h1>",
            f'<p class="meta">{_e(", ".join(model["projects"]))} · repo {_e(model["repo"])} · '
            f'{model["total"]} bugs · PR evidence {ev["pr"]} · Jira-only {ev["jira"]} · '
            f'regressions {model["regression"]} · insufficient evidence '
            f'{len(model["insufficient"])} · generated {_e(today)}</p>']
    if len(views) > 1:
        body.append('<div class="tabs" role="tablist">' + "".join(
            f'<button class="tab" data-view="{_e(v)}" role="tab" '
            f'aria-selected="{"true" if i == 0 else "false"}">{_e(VIEW_TITLE[v])}</button>'
            for i, (v, _) in enumerate(views)) + "</div>")
    for i, (v, rows) in enumerate(views):
        hidden = " hidden" if i else ""
        body.append(f'<section data-view="{_e(v)}"{hidden}>{_rank_html(rows)}</section>')

    body.append("<h2>Categories</h2>")
    for r in model["views"]["all"]:
        if r["category"] == INSUFFICIENT:
            continue
        flag = '<span class="new">new</span>' if r["is_new"] else ""
        body.append(f'<h3><span class="sub">{_e(r["category"])}</span>{flag} — '
                    f'{r["count"]} bugs</h3><p class="def">{_e(r["definition"])}</p>'
                    + _bug_table(r["examples"], with_cause=True))

    if model["insufficient"]:
        body.append(f'<h2>Insufficient evidence — {len(model["insufficient"])} bugs</h2>'
                    '<p class="meta">Neither Jira nor the PR shows the mistake.</p>'
                    + _bug_table(model["insufficient"], with_cause=False))
    if model["no_area"]:
        body.append(f'<h2>No resolvable area — {len(model["no_area"])} bugs</h2>'
                    + _bug_table(model["no_area"], with_cause=True))

    script = f"<script>{TAB_JS}</script>" if len(views) > 1 else ""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Bug root causes</title><style>{CSS}</style></head><body><main>"
            + "".join(body) + "</main>" + script + "</body></html>\n")


# -------------------------------------------------------------------------- CLI

def _read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank developer root causes and report.")
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--classify", required=True)
    parser.add_argument("--assignments", required=True, nargs="+",
                        help="one JSON part per classification batch")
    parser.add_argument("--taxonomy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    with open(args.bugs, encoding="utf-8") as handle:
        document = json.load(handle)
    rows = _read_jsonl(args.classify)
    parts = []
    for path in args.assignments:
        with open(path, encoding="utf-8") as handle:
            parts.append(json.load(handle))
    taxonomy = load_taxonomy(args.taxonomy)

    try:
        assignments = merge_assignments(parts)
        new = validate([b["key"] for b in document["bugs"]], assignments, taxonomy)
    except AssignmentError as ex:
        for problem in ex.problems:
            sys.stderr.write(f"{problem}\n")
        sys.stderr.write("Fix the assignments for these bugs and re-run.\n")
        return 2

    model = build_model(document, rows, assignments, taxonomy, new)
    for path in (args.out, args.csv, args.model):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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

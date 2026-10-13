#!/usr/bin/env python3
"""Stage 2 of /oc-clean-branches: render the plan as Markdown (stdout), HTML and CSV.

The report is what the user confirms, so it must show exactly what branch_delete.py
will delete: the deletable list here and the plan's `deletable` arrays are one source.
"""
import argparse
import csv
import html
import json

from branch_rules import RULES

MD_LIST_LIMIT = 60
CSV_HEADER = ["repo", "branch", "decision", "rule", "reason", "last_commit", "author",
              "ticket", "issuetype", "status", "target", "hash"]


def _md(value):
    return str(value if value is not None else "-").replace("|", "\\|")


def total_deletable(plan):
    return sum(len(r["deletable"]) for r in plan["repos"])


def render_markdown(plan):
    out = [f"# Branch clean-up — `{plan['workspace']}`, last commit before {plan['before']}", "",
           f"Recent-commit guard (R4): anything committed since {plan['recent_cutoff']} "
           f"({plan['recent_days']} days) is kept.", "",
           "| Repository | Branches | Before date | R1 | R2 | R3 | R4 | R5 | ERR | **To delete** |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for repo in plan["repos"]:
        by = repo["excluded_by_rule"]
        out.append(f"| {repo['repo']} | {repo['total_branches']} | {repo['candidates']} | "
                   + " | ".join(str(by.get(r, 0)) for r in RULES)
                   + f" | **{len(repo['deletable'])}** |")
    out += ["", "Rules: " + "; ".join(f"**{k}** {v}" for k, v in RULES.items()) + "."]

    for repo in plan["repos"]:
        rows = repo["deletable"]
        out += ["", f"## {repo['repo']} — {len(rows)} branch(es) to delete "
                    f"(merge check against `{repo['dev_branch']}` unless a merged PR says otherwise)"]
        if not rows:
            out.append("_Nothing to delete._")
            continue
        out += ["", "| Branch | Last commit | Author | Ticket | Type | Status | Merged into |",
                "|---|---|---|---|---|---|---|"]
        for r in rows[:MD_LIST_LIMIT]:
            out.append(f"| `{_md(r['name'])}` | {_md((r['date'] or '')[:10])} | {_md(r['author'])} | "
                       f"{_md(r['ticket'])} | {_md(r.get('issuetype'))} | {_md(r.get('status'))} | "
                       f"`{_md(r.get('target'))}` |")
        if len(rows) > MD_LIST_LIMIT:
            out.append(f"| … {len(rows) - MD_LIST_LIMIT} more — see the HTML / CSV | | | | | | |")

    if plan.get("errors"):
        out += ["", "## Repositories skipped"]
        out += [f"- **{e['repo']}**: {e['error']}" for e in plan["errors"]]
    out += ["", f"**Total to delete: {total_deletable(plan)} branch(es).**"]
    return "\n".join(out)


def write_csv(plan, path):
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for repo in plan["repos"]:
            for decision, key in (("delete", "deletable"), ("keep", "excluded")):
                for r in repo[key]:
                    writer.writerow([repo["repo"], r["name"], decision, r.get("rule", ""),
                                     r.get("reason", ""), r.get("date", ""), r.get("author", ""),
                                     r.get("ticket") or "", r.get("issuetype") or "",
                                     r.get("status") or "", r.get("target") or "", r.get("hash", "")])


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--red:#c0262d;--redbg:#fdecec}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--muted:#9a9aa2;
--line:#2c2c31;--red:#ff6b6b;--redbg:#3a1416}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:24px 16px;}
h1{font-size:22px}h2{font-size:17px;margin-top:28px}
table{border-collapse:collapse;width:100%;margin:8px 0;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;white-space:nowrap}
th{color:var(--muted);font-weight:600}.num{text-align:right}
.warn{background:var(--redbg);color:var(--red);border:2px solid var(--red);
padding:12px 14px;border-radius:8px;font-weight:700}
details{margin:10px 0}code{font-size:12.5px}
"""


def write_html(plan, path):
    e = lambda v: html.escape(str(v if v is not None else "-"))
    n = total_deletable(plan)
    parts = ["<!doctype html><html><head><meta charset=\"utf-8\">"
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
             f"<title>Branch clean-up</title><style>{CSS}</style></head><body>",
             f"<h1>Branch clean-up — {e(plan['workspace'])}</h1>",
             f"<p>Last commit before <b>{e(plan['before'])}</b>; anything committed since "
             f"{e(plan['recent_cutoff'])} is kept. Generated {e(plan['generated_at'])}.</p>",
             f"<p class=\"warn\">{n} branch(es) listed below will be PERMANENTLY deleted from "
             "Bitbucket once confirmed.</p>",
             "<table><tr><th>Repository</th><th class=num>Branches</th><th class=num>Before date</th>"
             + "".join(f"<th class=num title=\"{e(v)}\">{k}</th>" for k, v in RULES.items())
             + "<th class=num>To delete</th></tr>"]
    for repo in plan["repos"]:
        by = repo["excluded_by_rule"]
        parts.append(f"<tr><td>{e(repo['repo'])}</td><td class=num>{repo['total_branches']}</td>"
                     f"<td class=num>{repo['candidates']}</td>"
                     + "".join(f"<td class=num>{by.get(r, 0)}</td>" for r in RULES)
                     + f"<td class=num><b>{len(repo['deletable'])}</b></td></tr>")
    parts.append("</table><p>" + " · ".join(f"<b>{k}</b> {e(v)}" for k, v in RULES.items()) + "</p>")
    for repo in plan["repos"]:
        parts.append(f"<h2>{e(repo['repo'])} — {len(repo['deletable'])} to delete</h2>")
        parts.append("<table><tr><th>Branch</th><th>Last commit</th><th>Author</th><th>Ticket</th>"
                     "<th>Type</th><th>Status</th><th>Merged into</th></tr>")
        for r in repo["deletable"]:
            parts.append(f"<tr><td><code>{e(r['name'])}</code></td><td>{e((r['date'] or '')[:10])}</td>"
                         f"<td>{e(r['author'])}</td><td>{e(r['ticket'])}</td>"
                         f"<td>{e(r.get('issuetype'))}</td><td>{e(r.get('status'))}</td>"
                         f"<td><code>{e(r.get('target'))}</code></td></tr>")
        parts.append("</table>")
        parts.append(f"<details><summary>{len(repo['excluded'])} kept (excluded by a guard)"
                     "</summary><table><tr><th>Branch</th><th>Rule</th><th>Reason</th>"
                     "<th>Last commit</th></tr>")
        for r in repo["excluded"]:
            parts.append(f"<tr><td><code>{e(r['name'])}</code></td><td>{e(r['rule'])}</td>"
                         f"<td>{e(r['reason'])}</td><td>{e((r['date'] or '')[:10])}</td></tr>")
        parts.append("</table></details>")
    for err in plan.get("errors") or []:
        parts.append(f"<p class=\"warn\">{e(err['repo'])} skipped: {e(err['error'])}</p>")
    parts.append("</body></html>")
    with open(path, "w") as handle:
        handle.write("\n".join(parts))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True, help="HTML path")
    ap.add_argument("--csv", required=True)
    args = ap.parse_args(argv)
    with open(args.plan) as handle:
        plan = json.load(handle)
    print(render_markdown(plan))
    write_html(plan, args.out)
    write_csv(plan, args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

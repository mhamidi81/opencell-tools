#!/usr/bin/env python3
"""Stage 3 of /oc-pr-rejection-rate: render the model as Markdown, CSV and HTML.

All formatting lives here and nothing else does. The one rule worth stating: a
repository with no PRs in the window renders `n/a`, never `0.0%` — "we opened nothing"
and "we opened work and none was rejected" are different facts and must not look alike.

Every output states which draft-detection mode produced R3, so a saved file stays
interpretable months later. See the spec's section 4.
"""
import argparse
import csv
import html
import json
import os

from pr_classify import REASONS

DETECTION_NOTE = {
    "activity": "R3 read ready-to-draft transitions from the activity feed (exact).",
    "current-flag": "R3 is **approximate**: the activity feed carried no draft history, "
                    "so a PR currently in draft with post-creation activity was counted. "
                    "Both over- and under-counting are possible.",
    "unavailable": "R3 **could not be measured**: no draft data was available from "
                   "Bitbucket. The re-drafted column is not a real zero.",
}

CSV_HEADER = (["repo", "id", "title", "author", "created_on", "state", "rejected"]
              + [f"r_{reason}" for reason in REASONS]
              + ["activity_ok", "url", "draft_detection"])


def format_rate(rate):
    return "n/a" if rate is None else f"{rate:.1f}%"


def _reasons(row):
    return ", ".join(reason for reason in REASONS if row[f"r_{reason}"]) or "-"


def _md(value):
    """Escape a value for a Markdown table cell.

    A `|` in a Bitbucket PR title does not merely misalign the row: in a
    five-column table it shifts every later cell one to the left, so the author
    column shows part of the title and the reasons column shows the author.
    Misattributed data is worse than a broken table.
    """
    return str(value).replace("|", "\\|")


def render_markdown(model):
    window = model.get("window", {})
    out = [f"# PR rejection rate — {window.get('since')} → {window.get('until')} "
           f"(on `created_on`; the end date is exclusive)", ""]

    out += ["| Repository | Total PRs | Rejected | Rejection rate |",
            "|---|---:|---:|---:|"]
    for slug, repo in model["repos"].items():
        out.append(f"| {slug} | {repo['total']} | {repo['rejected']} | "
                   f"{format_rate(repo['rate'])} |")
    totals = model["totals"]
    out.append(f"| **All** | **{totals['total']}** | **{totals['rejected']}** | "
               f"**{format_rate(totals['rate'])}** |")

    mode = model["draft_detection"]
    note = DETECTION_NOTE[mode]
    if mode == "activity":
        out += ["", f"*{note}*", ""]
    else:
        out += ["", f"> ⚠️ {note}", ""]

    out += ["## Rejection reasons", "",
            "A PR counts once in the rejected total above, so these columns **overlap** "
            "and may sum past it.", "",
            "| Repository | Declined | Changes requested | Re-drafted |",
            "|---|---:|---:|---:|"]
    for slug, repo in model["repos"].items():
        r = repo["reasons"]
        out.append(f"| {slug} | {r['declined']} | {r['changes_requested']} | "
                   f"{r['redrafted']} |")

    out.append("")

    for slug, repo in model["repos"].items():
        rejected = [row for row in repo["prs"] if row["rejected"]]
        if not rejected:
            continue
        out += [f"## Rejected PRs — {slug}", "",
                "| PR | Title | Author | State | Reasons |", "|---|---|---|---|---|"]
        for row in rejected:
            out.append(f"| [#{row['id']}]({row['url']}) | {_md(row['title'])} | "
                       f"{_md(row['author'])} | {row['state']} | {_reasons(row)} |")
        out.append("")

    if model.get("warnings"):
        out += ["## Warnings", ""] + [f"- {_md(w)}" for w in model["warnings"]] + [""]
    return "\n".join(out)


def render_csv_rows(model):
    rows = [list(CSV_HEADER)]
    mode = model["draft_detection"]
    for slug, repo in model["repos"].items():
        for row in repo["prs"]:
            rows.append([slug, row["id"], row["title"], row["author"],
                         row["created_on"], row["state"], row["rejected"]]
                        + [row[f"r_{reason}"] for reason in REASONS]
                        + [row["activity_ok"], row["url"], mode])
    return rows


CSS = """
body { font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem auto;
       max-width: 62rem; color: #1b1b1b; }
h1 { font-size: 1.5rem; margin-bottom: .2rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
.window { color: #666; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }
th, td { border-bottom: 1px solid #e3e3e3; padding: .45rem .6rem; text-align: left; }
th { background: #f6f7f9; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.total td { font-weight: 700; border-top: 2px solid #ccc; }
.note { background: #f6f7f9; border-left: 3px solid #999; padding: .6rem .9rem;
        margin: 1rem 0; color: #444; }
.note.warn { background: #fff6e5; border-left-color: #e0a300; }
.reasons { color: #666; font-size: .9em; }
a { color: #0b5cad; text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def _e(value):
    return html.escape(str(value), quote=True)


def render_html(model):
    window = model.get("window", {})
    mode = model["draft_detection"]
    note_class = "note warn" if mode != "activity" else "note"
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<title>PR rejection rate</title>", f"<style>{CSS}</style></head><body>",
        "<h1>PR rejection rate</h1>",
        f"<p class=\"window\">{_e(window.get('since'))} &rarr; {_e(window.get('until'))} "
        "on <code>created_on</code>; the end date is exclusive.</p>",
        "<table><tr><th>Repository</th><th class=\"num\">Total PRs</th>"
        "<th class=\"num\">Rejected</th><th class=\"num\">Rejection rate</th></tr>",
    ]
    for slug, repo in model["repos"].items():
        parts.append(f"<tr><td>{_e(slug)}</td><td class=\"num\">{repo['total']}</td>"
                     f"<td class=\"num\">{repo['rejected']}</td>"
                     f"<td class=\"num\">{_e(format_rate(repo['rate']))}</td></tr>")
    totals = model["totals"]
    parts.append(f"<tr class=\"total\"><td>All</td><td class=\"num\">{totals['total']}</td>"
                 f"<td class=\"num\">{totals['rejected']}</td>"
                 f"<td class=\"num\">{_e(format_rate(totals['rate']))}</td></tr></table>")

    detection_html = DETECTION_NOTE[mode].replace("**", "")
    parts.append(f"<p class=\"{note_class}\">{_e(detection_html)}</p>")

    parts.append("<h2>Rejection reasons</h2><p class=\"reasons\">A PR counts once in the "
                 "rejected total above, so these columns overlap and may sum past it.</p>")
    parts.append("<table><tr><th>Repository</th><th class=\"num\">Declined</th>"
                 "<th class=\"num\">Changes requested</th>"
                 "<th class=\"num\">Re-drafted</th></tr>")
    for slug, repo in model["repos"].items():
        r = repo["reasons"]
        parts.append(f"<tr><td>{_e(slug)}</td><td class=\"num\">{r['declined']}</td>"
                     f"<td class=\"num\">{r['changes_requested']}</td>"
                     f"<td class=\"num\">{r['redrafted']}</td></tr>")
    parts.append("</table>")

    for slug, repo in model["repos"].items():
        rejected = [row for row in repo["prs"] if row["rejected"]]
        if not rejected:
            continue
        parts.append(f"<h2>Rejected PRs &mdash; {_e(slug)}</h2>")
        parts.append("<table><tr><th>PR</th><th>Title</th><th>Author</th><th>State</th>"
                     "<th>Reasons</th></tr>")
        for row in rejected:
            parts.append(
                f"<tr><td><a href=\"{_e(row['url'])}\">#{_e(row['id'])}</a></td>"
                f"<td>{_e(row['title'])}</td><td>{_e(row['author'])}</td>"
                f"<td>{_e(row['state'])}</td><td>{_e(_reasons(row))}</td></tr>")
        parts.append("</table>")

    if model.get("warnings"):
        parts.append("<h2>Warnings</h2><ul>")
        parts.extend(f"<li>{_e(w)}</li>" for w in model["warnings"])
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def _ensure_parent(path):
    """Create the output directory if needed.

    The default output path is ./docs/, and the skill advertises that the command
    runs from any directory. Failing here would waste every API call the fetch
    already spent.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the PR rejection-rate report.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--csv", required=True)
    args = parser.parse_args(argv)

    with open(args.model) as handle:
        model = json.load(handle)

    print(render_markdown(model))
    _ensure_parent(args.out)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(render_html(model))
    _ensure_parent(args.csv)
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(render_csv_rows(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

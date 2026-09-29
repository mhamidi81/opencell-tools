import pytest

import rc_report as rr

TAXONOMY_MD = """# t

Intro paragraph.

## null-handling
A missing value was not guarded.
Second line of the same paragraph.

Examples: INTRD-1

## api-contract
Wrong HTTP status.

Examples: INTRD-2

## insufficient-evidence
Too little signal.

Examples: INTRD-3
"""

TAX = {"null-handling": "A missing value was not guarded.",
       "api-contract": "Wrong HTTP status.",
       "insufficient-evidence": "Too little signal."}


def bug(key, area="portal", created="2026-09-01", summary="A bug"):
    return {"key": key, "area": area, "component": None, "summary": summary, "excerpt": "",
            "comments": [], "status": "Done", "status_category": "done", "created": created,
            "assignee": "Dev One", "labels": [],
            "url": f"https://opencellsoft.atlassian.net/browse/{key}"}


def a(category, conf="high", reg=False, cause="the cause"):
    return {"category": category, "confidence": conf, "regression": reg, "cause": cause}


def model_for(bugs, asg, rows=None, repo="both", new=()):
    doc = {"repo": repo, "window": {"since": "2026-09-01", "until": "2026-10-01"},
           "projects": ["INTRD"], "bugs": bugs}
    rows = rows or [{"key": b["key"], "evidence": "jira", "pr_url": None} for b in bugs]
    return rr.build_model(doc, rows, asg, TAX, new)


def test_load_taxonomy_reads_names_and_first_paragraph(tmp_path):
    path = tmp_path / "t.md"
    path.write_text(TAXONOMY_MD)
    tax = rr.load_taxonomy(str(path))
    assert list(tax) == ["null-handling", "api-contract", "insufficient-evidence"]
    assert tax["null-handling"] == ("A missing value was not guarded. "
                                    "Second line of the same paragraph.")


def test_missing_assignments_are_named():
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1", "A-2"], {"A-1": a("null-handling")}, TAX)
    assert "A-2" in str(ex.value)


def test_assignments_for_keys_outside_the_run_are_rejected():
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1"], {"A-1": a("api-contract"), "Z-9": a("api-contract")}, TAX)
    assert "Z-9" in str(ex.value)


def test_malformed_fields_are_each_reported():
    bad = {"A-1": {"category": "api-contract", "confidence": "medium", "regression": "yes",
                   "cause": " "}}
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(["A-1"], bad, TAX)
    assert len(ex.value.problems) == 3


def test_an_unknown_category_needs_five_bugs():
    keys = [f"A-{i}" for i in range(5)]
    four = {k: a("brand-new") for k in keys[:4]}
    four[keys[4]] = a("null-handling")
    with pytest.raises(rr.AssignmentError) as ex:
        rr.validate(keys, four, TAX)
    assert "brand-new" in str(ex.value)
    assert rr.validate(keys, {k: a("brand-new") for k in keys}, TAX) == ["brand-new"]


def test_merge_assignments_rejects_a_key_classified_two_ways():
    assert rr.merge_assignments([{"A-1": a("api-contract")}, {"A-2": a("null-handling")}]) \
        == {"A-1": a("api-contract"), "A-2": a("null-handling")}
    with pytest.raises(rr.AssignmentError) as ex:
        rr.merge_assignments([{"A-1": a("api-contract")}, {"A-1": a("null-handling")}])
    assert "A-1" in str(ex.value)


def test_ranking_counts_shares_regressions_and_evidence():
    bugs = [bug("A-1", "portal"), bug("A-2", "core"), bug("A-3", None), bug("A-4", "portal")]
    asg = {"A-1": a("null-handling", reg=True), "A-2": a("null-handling", conf="low"),
           "A-3": a("null-handling"), "A-4": a("api-contract")}
    rows = [{"key": "A-1", "evidence": "pr", "pr_url": "p1"}] + [
        {"key": k, "evidence": "jira", "pr_url": None} for k in ("A-2", "A-3", "A-4")]

    m = model_for(bugs, asg, rows)

    top = m["views"]["all"][0]
    assert top["category"] == "null-handling" and top["count"] == 3
    assert top["share"] == 0.75
    assert top["areas"] == {"portal": 1, "core": 1, "none": 1}
    assert top["regression"] == 1 and top["regression_rate"] == pytest.approx(1 / 3)
    assert top["evidence"] == {"pr": 1, "jira": 2} and top["low_confidence"] == 1
    assert m["total"] == 4 and m["evidence"] == {"pr": 1, "jira": 3}
    assert m["regression"] == 1
    assert m["views"]["portal"][0]["count"] == 1
    assert [b["key"] for b in m["no_area"]] == ["A-3"]


def test_insufficient_evidence_ranks_last_even_when_largest():
    bugs = [bug(f"A-{i}") for i in range(4)]
    asg = {"A-0": a("api-contract"), **{f"A-{i}": a("insufficient-evidence") for i in (1, 2, 3)}}
    m = model_for(bugs, asg)
    assert [r["category"] for r in m["views"]["all"]] == ["api-contract", "insufficient-evidence"]
    assert len(m["insufficient"]) == 3


def test_examples_prefer_pr_evidence_then_newest_and_stop_at_five():
    bugs = [bug(f"A-{i}", created=f"2026-09-{10 + i:02d}") for i in range(7)]
    asg = {b["key"]: a("null-handling") for b in bugs}
    rows = [{"key": b["key"], "evidence": "pr" if b["key"] == "A-0" else "jira",
             "pr_url": None} for b in bugs]
    examples = model_for(bugs, asg, rows)["views"]["all"][0]["examples"]
    assert [b["key"] for b in examples] == ["A-0", "A-6", "A-5", "A-4", "A-3"]


def test_single_area_run_has_no_other_area_view():
    m = model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal")
    assert set(m["views"]) == {"all", "portal"}


def test_cause_is_trimmed_and_new_categories_are_labelled():
    m = model_for([bug("A-1")], {"A-1": a("brand-new", cause="z" * 300)}, new=["brand-new"])
    row = m["views"]["all"][0]
    assert row["is_new"] and "dev-root-causes.md" in row["definition"]
    assert len(m["bugs"][0]["cause"]) == rr.CAUSE_LIMIT
    assert m["new_categories"] == ["brand-new"]


import json


def sample_model():
    bugs = [bug("A-1", "portal", summary="Grid | broken <script>"), bug("A-2", "core"),
            bug("A-3", None)]
    asg = {"A-1": a("null-handling", reg=True, cause="guard missing on `cfg`"),
           "A-2": a("brand-new"), "A-3": a("insufficient-evidence")}
    rows = [{"key": "A-1", "evidence": "pr", "pr_url": "https://bb/pr/1"},
            {"key": "A-2", "evidence": "jira", "pr_url": None},
            {"key": "A-3", "evidence": "jira", "pr_url": None}]
    return model_for(bugs, asg, rows, new=["brand-new"])


def test_markdown_header_ranking_and_sections():
    md = rr.render_markdown(sample_model())
    assert md.startswith("# Development-issue root causes")
    assert "**3** bugs · PR evidence **1** · Jira-only **2** · regressions **1**" in md
    assert "| `null-handling` | 1 | 33.3% | 1 | 0 | 0 | 1 (100%) | 1 / 0 | 0 |" in md
    assert "`brand-new` **(new)**" in md
    assert "## Ranking — Frontend" in md and "## Ranking — Backend" in md
    assert "Grid \\| broken" in md
    assert "[PR](https://bb/pr/1)" in md
    assert "## Insufficient evidence — 1 bugs" in md
    assert "## No resolvable area — 1 bugs" in md
    assert "## New categories" in md


def test_single_area_markdown_shows_one_ranking():
    md = rr.render_markdown(model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal"))
    assert md.count("## Ranking") == 1


def test_csv_has_one_row_per_bug():
    rows = rr.render_csv_rows(sample_model())
    assert rows[0] == rr.CSV_HEADER
    assert len(rows) == 4
    first = dict(zip(rows[0], rows[1]))
    assert first["key"] == "A-1" and first["regression"] == "yes"
    assert first["evidence"] == "pr" and first["pr_url"] == "https://bb/pr/1"
    assert first["cause"] == "guard missing on `cfg`"
    assert dict(zip(rows[0], rows[3]))["area"] == ""


def test_html_escapes_content_and_offers_area_tabs():
    page = rr.render_html(sample_model(), today="2026-09-29")
    assert "Grid | broken &lt;script&gt;" in page
    assert 'data-view="portal"' in page and 'data-view="core"' in page
    assert 'class="tab"' in page
    assert "prefers-color-scheme:dark" in page


def test_single_area_html_has_no_tabs():
    page = rr.render_html(model_for([bug("A-1")], {"A-1": a("api-contract")}, repo="portal"),
                          today="2026-09-29")
    assert 'class="tab"' not in page


def write_run(tmp_path, parts):
    (tmp_path / "bugs.json").write_text(json.dumps({
        "repo": "both", "window": {"since": "2026-09-01", "until": "2026-10-01"},
        "projects": ["INTRD"], "bugs": [bug("A-1"), bug("A-2", "core")]}))
    (tmp_path / "ci.jsonl").write_text(
        json.dumps({"key": "A-1", "evidence": "jira", "pr_url": None}) + "\n"
        + json.dumps({"key": "A-2", "evidence": "jira", "pr_url": None}) + "\n")
    (tmp_path / "tax.md").write_text(TAXONOMY_MD)
    paths = []
    for i, part in enumerate(parts, 1):
        p = tmp_path / f"{i:03d}.json"
        p.write_text(json.dumps(part))
        paths.append(str(p))
    return (["--bugs", str(tmp_path / "bugs.json"), "--classify", str(tmp_path / "ci.jsonl"),
             "--assignments", *paths, "--taxonomy", str(tmp_path / "tax.md"),
             "--out", str(tmp_path / "docs" / "r.html"), "--csv", str(tmp_path / "docs" / "r.csv"),
             "--model", str(tmp_path / "model.json")])


def test_main_merges_parts_and_writes_every_report(tmp_path, capsys):
    args = write_run(tmp_path, [{"A-1": a("null-handling")}, {"A-2": a("api-contract")}])
    assert rr.main(args) == 0
    assert (tmp_path / "docs" / "r.html").exists()
    assert (tmp_path / "docs" / "r.csv").exists()
    assert json.loads((tmp_path / "model.json").read_text())["total"] == 2
    assert "# Development-issue root causes" in capsys.readouterr().out


def test_main_exits_2_and_names_the_missing_bug(tmp_path, capsys):
    args = write_run(tmp_path, [{"A-1": a("null-handling")}])
    assert rr.main(args) == 2
    err = capsys.readouterr().err
    assert "A-2" in err and "re-run" in err

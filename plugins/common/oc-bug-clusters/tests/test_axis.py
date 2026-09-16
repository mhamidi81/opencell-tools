"""The --axis switch: technical (default) vs functional clustering.

The axis changes only the vocabulary and the identity of what gets written. It must
NOT change which bugs are fetched, the threshold, or the Enabler shape.

The load-bearing test here is `test_the_two_axes_get_different_marker_labels`: without
the axis in the marker, a technical run over a window already clustered functionally is
silently skipped as a duplicate — the exact defect this feature would otherwise add.
"""
import json

import pytest

import bug_cluster as bc
import bug_enabler as be
from test_bug_cluster import document, spread


# --------------------------------------------------------------- the taxonomies

def test_functional_taxonomy_ships_under_its_new_name():
    from pathlib import Path
    refs = Path(bc.__file__).resolve().parent.parent / "references"
    assert (refs / "functional-subjects.md").is_file()
    assert not (refs / "subjects.md").exists(), "renamed, not copied"


@pytest.mark.parametrize("name", ["technical-portal.md", "technical-core.md"])
def test_technical_taxonomies_ship(name):
    from pathlib import Path
    refs = Path(bc.__file__).resolve().parent.parent / "references"
    subjects = bc.seeded_subjects(refs / name)
    assert len(subjects) >= 6, f"{name} too thin"
    assert subjects == sorted(set(subjects), key=subjects.index), "duplicate heading"


def test_the_two_technical_taxonomies_do_not_overlap():
    """A portal cause and a core cause must not share a name — the report would be
    ambiguous about which area a cluster came from."""
    from pathlib import Path
    refs = Path(bc.__file__).resolve().parent.parent / "references"
    portal = set(bc.seeded_subjects(refs / "technical-portal.md"))
    core = set(bc.seeded_subjects(refs / "technical-core.md"))
    assert portal and core
    assert portal & core == set(), f"shared: {sorted(portal & core)}"


def test_seeded_subjects_merges_several_files(tmp_path):
    a = tmp_path / "a.md"; a.write_text("## ag-grid\nGrids.\n")
    b = tmp_path / "b.md"; b.write_text("## dto-mapping\nMapping.\n")
    assert bc.seeded_subjects([a, b]) == ["ag-grid", "dto-mapping"]


def test_seeded_subjects_still_accepts_a_single_path(tmp_path):
    p = tmp_path / "s.md"; p.write_text("## rating\nPrices.\n")
    assert bc.seeded_subjects(p) == ["rating"]


def test_seeded_subjects_deduplicates_across_files(tmp_path):
    a = tmp_path / "a.md"; a.write_text("## i18n-locale\nx.\n")
    b = tmp_path / "b.md"; b.write_text("## i18n-locale\ny.\n## api\nz.\n")
    assert bc.seeded_subjects([a, b]) == ["i18n-locale", "api"]


# ------------------------------------------------------------- axis in the model

def test_model_records_the_axis():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="technical")
    assert m["axis"] == "technical"


def test_axis_defaults_to_technical():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    assert bc.build_model(document(bugs), assignments, 5)["axis"] == "technical"


def test_axis_does_not_change_clustering():
    """Same bugs, same labels, both axes -> identical cluster shape."""
    a1, a2 = {}, {}
    b1 = spread("P", "portal", 6, "x", a1)
    b2 = spread("P", "portal", 6, "x", a2)
    t = bc.build_model(document(b1), a1, 5, axis="technical")
    f = bc.build_model(document(b2), a2, 5, axis="functional")
    assert t["areas"]["portal"]["clusters"][0]["count"] == \
           f["areas"]["portal"]["clusters"][0]["count"] == 6


# --------------------------------------------------------- axis in the renderings

def test_markdown_states_which_axis_produced_it():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="technical")
    assert "technical" in bc.render_markdown(m).lower()


def test_html_states_which_axis_produced_it():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="functional")
    assert "functional" in bc.render_html(m).lower()


def test_csv_carries_an_axis_column():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="technical")
    rows = bc.render_csv_rows(m)
    assert "axis" in rows[0]
    idx = rows[0].index("axis")
    assert {r[idx] for r in rows[1:]} == {"technical"}


# ------------------------------------------------- axis in the Jira write identity

def test_marker_label_includes_the_axis():
    assert be.marker_label("technical", "portal", "2026-08-01", "2026-09-01") == \
        "bug-clusters-technical-portal-2026-08-01-2026-09-01"


def test_the_two_axes_get_different_marker_labels():
    """THE load-bearing test. Without the axis in the marker, a technical run over a
    window already clustered functionally is skipped as a duplicate and creates nothing."""
    t = be.marker_label("technical", "portal", "2026-08-01", "2026-09-01")
    f = be.marker_label("functional", "portal", "2026-08-01", "2026-09-01")
    assert t != f


def test_enabler_summary_names_the_axis():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="technical")
    plan = be.build_plan(m, "INTRD", dict(be.DEFAULT_ASSIGNEE), "r.html")
    assert plan["areas"][0]["enabler"]["fields"]["summary"] == \
        "Bug clusters — Frontend — technical — 2026-08-01 → 2026-09-01"


def test_plan_carries_the_axis_marker_onto_the_enabler():
    assignments = {}
    bugs = spread("P", "portal", 5, "ag-grid", assignments)
    m = bc.build_model(document(bugs), assignments, 5, axis="technical")
    plan = be.build_plan(m, "INTRD", dict(be.DEFAULT_ASSIGNEE), "r.html")
    labels = plan["areas"][0]["enabler"]["fields"]["labels"]
    assert any(l.startswith("bug-clusters-technical-portal-") for l in labels)

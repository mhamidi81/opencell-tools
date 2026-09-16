import pytest

import bug_cluster as bc


def bug(key, area, created="2026-08-20", category="indeterminate", labels=()):
    return {"key": key, "area": area, "component": None, "summary": f"s {key}",
            "excerpt": "", "issuetype": "Bug", "status": "In Progress",
            "status_category": category, "resolution": None, "created": created,
            "assignee": None, "reporter": None, "labels": list(labels),
            "priority": "Major", "parent": None,
            "url": f"https://opencellsoft.atlassian.net/browse/{key}"}


def document(bugs, repo="portal", **extra):
    doc = {"window": {"since": "2026-08-01", "until": "2026-09-01"},
           "projects": ["INTRD"], "repo": repo, "fetched": len(bugs),
           "dropped_invalid": 0, "bugs": bugs}
    doc.update(extra)
    return doc


def spread(prefix, area, n, subject, assignments):
    bugs = []
    for i in range(n):
        key = f"{prefix}-{i}"
        bugs.append(bug(key, area))
        assignments[key] = subject
    return bugs


# --------------------------------------------------------------- the threshold

def test_a_subject_at_the_threshold_becomes_a_cluster():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert [c["subject"] for c in portal["clusters"]] == ["quoting"]
    assert portal["clusters"][0]["count"] == 5
    assert portal["near"] == []


def test_a_subject_one_below_the_threshold_is_a_near_cluster():
    assignments = {}
    bugs = spread("P", "portal", 4, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert portal["clusters"] == []
    assert [(g["subject"], g["count"]) for g in portal["near"]] == [("quoting", 4)]


def test_the_threshold_is_configurable():
    assignments = {}
    bugs = spread("P", "portal", 3, "quoting", assignments)
    model = bc.build_model(document(bugs), assignments, min_cluster=3)
    assert [c["subject"] for c in model["areas"]["portal"]["clusters"]] == ["quoting"]


# ------------------------------------------------------------------- ordering

def test_clusters_are_ordered_by_size_then_subject():
    assignments = {}
    bugs = (spread("A", "portal", 5, "rating", assignments)
            + spread("B", "portal", 7, "quoting", assignments)
            + spread("C", "portal", 5, "invoicing", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    assert [c["subject"] for c in model["areas"]["portal"]["clusters"]] == [
        "quoting", "invoicing", "rating"]


def test_bugs_inside_a_cluster_are_newest_first():
    assignments = {"P-1": "quoting", "P-2": "quoting", "P-3": "quoting",
                   "P-4": "quoting", "P-5": "quoting"}
    bugs = [bug("P-1", "portal", created="2026-08-01"),
            bug("P-2", "portal", created="2026-08-30"),
            bug("P-3", "portal", created="2026-08-15"),
            bug("P-4", "portal", created="2026-08-10"),
            bug("P-5", "portal", created="2026-08-20")]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    keys = [b["key"] for b in model["areas"]["portal"]["clusters"][0]["bugs"]]
    assert keys == ["P-2", "P-5", "P-3", "P-4", "P-1"]


# --------------------------------------------------------------- area isolation

def test_areas_never_share_a_cluster():
    assignments = {}
    bugs = (spread("P", "portal", 3, "quoting", assignments)
            + spread("C", "core", 3, "quoting", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)

    assert model["areas"]["portal"]["clusters"] == []
    assert model["areas"]["core"]["clusters"] == []
    assert model["areas"]["portal"]["near"][0]["count"] == 3
    assert model["areas"]["core"]["near"][0]["count"] == 3


def test_only_areas_in_scope_appear():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments)
    model = bc.build_model(document(bugs, repo="portal"), assignments, min_cluster=5)
    assert list(model["areas"]) == ["portal"]


def test_both_lists_portal_before_core():
    assignments = {}
    bugs = (spread("C", "core", 5, "rating", assignments)
            + spread("P", "portal", 5, "quoting", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    assert list(model["areas"]) == ["portal", "core"]
    assert model["areas"]["portal"]["component"] == "Frontend"
    assert model["areas"]["core"]["component"] == "Backend"


# ------------------------------------------------------------- unclassified tail

def test_unclassified_bugs_are_carried_but_never_clustered():
    assignments = {}
    bugs = spread("P", "portal", 5, "quoting", assignments) + [bug("U-1", None)]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    assert [b["key"] for b in model["unclassified"]] == ["U-1"]
    assert model["areas"]["portal"]["bugs"] == 5


def test_an_unclassified_bug_needs_no_assignment():
    model = bc.build_model(document([bug("U-1", None)]), {}, min_cluster=5)
    assert len(model["unclassified"]) == 1


# ------------------------------------------------------------ missing assignment

def test_a_bug_without_an_assignment_fails_loudly():
    bugs = [bug("P-1", "portal"), bug("P-2", "portal")]
    with pytest.raises(bc.MissingAssignments) as ex:
        bc.build_model(document(bugs), {"P-1": "quoting"}, min_cluster=5)
    assert ex.value.keys == ["P-2"]
    assert "P-2" in str(ex.value)


# ------------------------------------------------------------------ group stats

def test_group_counts_open_and_closed_by_status_category():
    assignments = {f"P-{i}": "quoting" for i in range(5)}
    bugs = [bug("P-0", "portal", category="done"),
            bug("P-1", "portal", category="done"),
            bug("P-2", "portal", category="new"),
            bug("P-3", "portal", category="indeterminate"),
            bug("P-4", "portal", category=None)]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    cluster = model["areas"]["portal"]["clusters"][0]
    assert cluster["closed"] == 2 and cluster["open"] == 3


def test_group_reports_its_top_labels_and_date_span():
    assignments = {f"P-{i}": "quoting" for i in range(5)}
    bugs = [bug("P-0", "portal", created="2026-08-02", labels=["billing", "TNR"]),
            bug("P-1", "portal", created="2026-08-09", labels=["billing"]),
            bug("P-2", "portal", created="2026-08-21", labels=["billing"]),
            bug("P-3", "portal", created="2026-08-11", labels=["TNR"]),
            bug("P-4", "portal", created="2026-08-15", labels=[])]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    cluster = model["areas"]["portal"]["clusters"][0]
    assert cluster["labels"][0] == ["billing", 3]
    assert cluster["first_created"] == "2026-08-02"
    assert cluster["last_created"] == "2026-08-21"


def test_clustered_bug_count_excludes_near_clusters():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 2, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)

    portal = model["areas"]["portal"]
    assert portal["bugs"] == 8 and portal["clustered_bugs"] == 6


# ------------------------------------------------------------------ new subjects

def test_a_subject_outside_the_taxonomy_is_flagged_new():
    assignments = {}
    bugs = (spread("A", "portal", 5, "quoting", assignments)
            + spread("B", "portal", 5, "webhooks", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5,
                           seeded=["quoting", "rating"])

    flags = {c["subject"]: c["is_new"] for c in model["areas"]["portal"]["clusters"]}
    assert flags == {"quoting": False, "webhooks": True}


def test_seeded_subjects_reads_the_taxonomy_headings(tmp_path):
    path = tmp_path / "subjects.md"
    path.write_text("# Title\n\n## rating\nPrices.\n\n## quoting\nQuotes.\n")
    assert bc.seeded_subjects(path) == ["rating", "quoting"]


def test_model_carries_the_window_and_counters_through():
    model = bc.build_model(
        document([], **{"fetched": 149, "dropped_invalid": 14}), {}, min_cluster=5)
    assert model["window"]["since"] == "2026-08-01"
    assert model["fetched"] == 149 and model["dropped_invalid"] == 14
    assert model["kept"] == 0 and model["min_cluster"] == 5

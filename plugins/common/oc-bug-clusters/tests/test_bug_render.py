import bug_cluster as bc
from test_bug_cluster import bug, document, spread


def model_with(repo="portal", n=6, subject="quoting", extra_bugs=(), assignments=None):
    assignments = {} if assignments is None else assignments
    bugs = spread("P", "portal", n, subject, assignments) + list(extra_bugs)
    return bc.build_model(document(bugs, repo=repo), assignments, min_cluster=5)


# -------------------------------------------------------------------- Markdown

def test_markdown_states_the_window_and_the_counters():
    text = bc.render_markdown(model_with())
    assert "2026-08-01" in text and "2026-09-01" in text
    assert "INTRD" in text


def test_markdown_does_not_claim_dropped_bugs_were_invalid_or_duplicate():
    """The filter also drops resolution Declined and status Invalid — on real
    INTRD data every dropped bug was Declined. Naming two of the four reasons
    tells the reader something false about their own data."""
    text = bc.render_markdown(model_with())
    assert "Invalid/Duplicate" not in text
    assert "rejected" in text


def test_markdown_shows_each_cluster_with_its_size():
    text = bc.render_markdown(model_with(subject="quoting", n=7))
    assert "quoting" in text and "7" in text


def test_markdown_lists_every_bug_key_of_a_cluster():
    assignments = {}
    text = bc.render_markdown(model_with(n=5, assignments=assignments))
    for key in assignments:
        assert key in text


def test_markdown_names_the_near_clusters_with_their_counts():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 3, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    text = bc.render_markdown(model)
    assert "rating" in text and "Near-clusters" in text


def test_markdown_bullet_includes_the_assignee():
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal")]
    bugs[0]["assignee"] = "Adil El Jaouhari"
    model = bc.build_model(document(bugs), assignments, min_cluster=1)
    assert "Adil El Jaouhari" in bc.render_markdown(model)


def test_markdown_bullet_uses_an_em_dash_when_the_assignee_is_absent():
    """Gives the bug a label so the cluster table's own "—" (for empty top
    labels) can't make this pass for the wrong reason; checks the bullet line
    specifically, not just that "—" appears somewhere in the document."""
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal", labels=["billing"])]
    model = bc.build_model(document(bugs), assignments, min_cluster=1)
    assert bugs[0]["assignee"] is None
    bullet = next(line for line in bc.render_markdown(model).splitlines()
                 if line.startswith("- [P-0]"))
    assert "· — ·" in bullet


def test_markdown_lists_unclassified_bugs():
    text = bc.render_markdown(model_with(extra_bugs=[bug("U-1", None)]))
    assert "U-1" in text and "Unclassified" in text


def test_markdown_says_so_when_an_area_has_no_cluster():
    model = bc.build_model(document([]), {}, min_cluster=5)
    assert "No cluster" in bc.render_markdown(model)


def test_markdown_marks_a_subject_coined_outside_the_taxonomy():
    assignments = {}
    bugs = spread("A", "portal", 5, "webhooks", assignments)
    model = bc.build_model(document(bugs), assignments, 5, seeded=["quoting"])
    assert "new" in bc.render_markdown(model).lower()


def test_markdown_covers_both_areas():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    text = bc.render_markdown(model)
    assert "Frontend" in text and "Backend" in text


# ------------------------------------------------------------------------- CSV

def test_csv_starts_with_a_header_row():
    rows = bc.render_csv_rows(model_with())
    assert rows[0] == ["key", "axis", "area", "component", "subject", "in_cluster",
                       "status", "created", "assignee", "labels", "summary", "url"]


def test_csv_has_one_row_per_kept_bug_including_unclassified():
    rows = bc.render_csv_rows(model_with(n=6, extra_bugs=[bug("U-1", None)]))
    assert len(rows) == 1 + 7


def test_csv_marks_whether_a_bug_reached_a_cluster():
    assignments = {}
    bugs = (spread("A", "portal", 6, "quoting", assignments)
            + spread("B", "portal", 2, "rating", assignments))
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    flags = {r[0]: r[5] for r in bc.render_csv_rows(model)[1:]}
    assert flags["A-0"] == "yes" and flags["B-0"] == "no"


def test_csv_leaves_an_unclassified_bug_without_a_subject():
    rows = bc.render_csv_rows(model_with(extra_bugs=[bug("U-1", None)]))
    row = next(r for r in rows if r[0] == "U-1")
    assert row[2] == "" and row[4] == "" and row[5] == "no"   # area, subject, in_cluster


def test_csv_joins_labels_with_a_space():
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal", labels=["billing", "TNR"])]
    model = bc.build_model(document(bugs), assignments, min_cluster=5)
    assert bc.render_csv_rows(model)[1][9] == "billing TNR"


# ------------------------------------------------------------------------ HTML

def test_html_is_a_complete_document():
    html = bc.render_html(model_with())
    assert html.lstrip().startswith("<!doctype html>")
    assert "</html>" in html and "<style>" in html


def test_html_escapes_markup_in_a_summary():
    """min_cluster=1 so the bug forms a CLUSTER, not a near-cluster: summaries are
    only rendered in the cluster detail table, and escaping is what matters there.
    At min_cluster=5 this bug lands in `near`, whose pills render subject and count
    only, so the assertion could never see a summary at all."""
    assignments = {"P-0": "quoting"}
    bugs = [bug("P-0", "portal")]
    bugs[0]["summary"] = "<script>alert(1)</script> & co"
    model = bc.build_model(document(bugs), assignments, min_cluster=1)
    html = bc.render_html(model)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "&amp; co" in html


def test_html_links_every_bug_key_to_jira():
    html = bc.render_html(model_with(n=5))
    assert 'href="https://opencellsoft.atlassian.net/browse/P-0"' in html


def test_html_has_one_tab_per_area_when_both_are_in_scope():
    assignments = {}
    bugs = (spread("P", "portal", 5, "quoting", assignments)
            + spread("C", "core", 5, "rating", assignments))
    model = bc.build_model(document(bugs, repo="both"), assignments, min_cluster=5)
    html = bc.render_html(model)
    assert html.count('class="tab"') == 2


def test_html_omits_the_tab_bar_for_a_single_area():
    assert 'class="tab"' not in bc.render_html(model_with())

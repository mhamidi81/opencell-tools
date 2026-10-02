"""Report rendering."""
import csv

import branch_report

PLAN = {"workspace": "ws", "before": "2026-06-01", "recent_days": 30,
        "recent_cutoff": "2026-09-01", "generated_at": "2026-10-02T00:00:00+00:00",
        "errors": [{"repo": "other", "error": "HTTP 403"}],
        "repos": [{"repo": "repo", "dev_branch": "develop", "total_branches": 5, "candidates": 3,
                   "excluded_by_rule": {"R1": 1, "R2": 1},
                   "deletable": [{"name": "fix/A|1", "hash": "h", "date": "2026-01-01T00:00",
                                  "author": "Dev", "ticket": "A-1", "issuetype": "Bug",
                                  "status": "Done", "target": "develop"}],
                   "excluded": [{"name": "master", "hash": "m", "date": "2026-01-01T00:00",
                                 "author": "Dev", "ticket": None, "rule": "R1",
                                 "reason": "main"}]}]}


def test_markdown_states_total_skipped_repos_and_escapes_pipes():
    md = branch_report.render_markdown(PLAN)
    assert "**Total to delete: 1 branch(es).**" in md
    assert "fix/A\\|1" in md
    assert "**other**: HTTP 403" in md


def test_csv_holds_kept_and_deleted_rows(tmp_path):
    path = tmp_path / "r.csv"
    branch_report.write_csv(PLAN, path)
    rows = list(csv.DictReader(open(path)))
    assert {r["decision"] for r in rows} == {"delete", "keep"}


def test_html_carries_the_red_warning(tmp_path):
    path = tmp_path / "r.html"
    branch_report.write_html(PLAN, path)
    text = path.read_text()
    assert 'class="warn"' in text and "PERMANENTLY deleted" in text

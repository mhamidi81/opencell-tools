"""Report rendering. Pure string work over a model dict."""
import re

import pr_report as pr


def model(**overrides):
    base = {
        "window": {"since": "2026-09-10", "until": "2026-09-17"},
        "workspace": "opencellsoft",
        "draft_detection": "activity",
        "repos": {
            "opencell-portal": {
                "total": 4, "rejected": 1, "rate": 25.0,
                "reasons": {"declined": 1, "changes_requested": 1, "redrafted": 0},
                "prs": [{"id": 11, "title": "Fix totals", "author": "Dev",
                         "created_on": "2026-09-11T09:00:00+00:00", "state": "DECLINED",
                         "url": "https://bitbucket.org/pr/11", "rejected": True,
                         "r_declined": True, "r_changes_requested": True,
                         "r_redrafted": False, "activity_ok": True}],
            },
        },
        "totals": {"total": 4, "rejected": 1, "rate": 25.0},
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_markdown_shows_the_window_and_that_until_is_exclusive():
    text = pr.render_markdown(model())
    assert "2026-09-10" in text and "2026-09-17" in text
    assert "exclusive" in text.lower()


def test_markdown_reports_the_rate_with_one_decimal_and_a_percent_sign():
    assert "25.0%" in pr.render_markdown(model())


def test_markdown_renders_an_empty_repo_as_n_a_not_zero_percent():
    m = model()
    m["repos"]["opencell-core"] = {"total": 0, "rejected": 0, "rate": None,
                                   "reasons": {"declined": 0, "changes_requested": 0,
                                               "redrafted": 0}, "prs": []}
    text = pr.render_markdown(m)
    assert "n/a" in text
    assert "0.0%" not in text


def test_markdown_says_reason_columns_may_overlap():
    assert "overlap" in pr.render_markdown(model()).lower()


def test_markdown_always_states_the_draft_detection_mode():
    assert "activity" in pr.render_markdown(model())


def test_markdown_warns_loudly_when_r3_could_not_be_measured():
    text = pr.render_markdown(model(draft_detection="unavailable"))
    assert "could not be measured" in text.lower()


def test_markdown_flags_the_current_flag_mode_as_approximate():
    assert "approximate" in pr.render_markdown(model(draft_detection="current-flag")).lower()


def test_markdown_lists_the_rejected_prs_with_their_reasons():
    text = pr.render_markdown(model())
    assert "11" in text and "Fix totals" in text and "declined" in text


def test_markdown_relays_warnings():
    text = pr.render_markdown(model(warnings=["opencell-core PR 3: activity fetch failed"]))
    assert "activity fetch failed" in text


def test_csv_header_carries_one_column_per_rule():
    header = pr.render_csv_rows(model())[0]
    for column in ("repo", "id", "title", "author", "created_on", "state",
                   "rejected", "r_declined", "r_changes_requested", "r_redrafted", "url"):
        assert column in header


def test_csv_has_one_row_per_pr_plus_the_header():
    rows = pr.render_csv_rows(model())
    assert len(rows) == 2
    assert rows[1][0] == "opencell-portal"


def test_csv_carries_the_detection_mode_so_a_saved_file_stays_interpretable():
    rows = pr.render_csv_rows(model())
    assert "draft_detection" in rows[0]
    assert rows[1][rows[0].index("draft_detection")] == "activity"


def test_every_csv_row_has_one_cell_per_header_column():
    rows = pr.render_csv_rows(model())
    assert all(len(row) == len(rows[0]) for row in rows[1:])


def test_csv_carries_the_activity_ok_column_so_a_degraded_row_is_auditable():
    rows = pr.render_csv_rows(model())
    assert "activity_ok" in rows[0]
    assert rows[1][rows[0].index("activity_ok")] is True


def test_a_degraded_detection_mode_is_flagged_above_the_reason_table():
    """The safety argument for the degraded modes is that the mode travels with
    the number. Below a second table is where nobody reads it."""
    text = pr.render_markdown(model(draft_detection="unavailable"))
    assert text.index("could not be measured") < text.index("## Rejection reasons")


def test_format_rate_handles_none():
    assert pr.format_rate(None) == "n/a"
    assert pr.format_rate(25.0) == "25.0%"


def test_html_is_self_contained():
    """No external CSS, JS or fonts: these files get emailed and opened offline.

    Checking for "http://" alone would not catch this — the realistic regression
    is an https-hosted CDN stylesheet or web font, which is how such references
    are written today.
    """
    out = pr.render_html(model())
    assert out.startswith("<!doctype html>")
    assert "<style>" in out
    assert "<link" not in out
    assert "<script" not in out
    assert "@import" not in out
    # The only external reference the report may carry is a PR's own Bitbucket link.
    external = {url for url in re.findall(r'(?:href|src)="([^"]+)"', out)
                if url.startswith("http")}
    assert all(url.startswith("https://bitbucket.org/") for url in external), external


def test_html_escapes_a_title_containing_markup():
    m = model()
    m["repos"]["opencell-portal"]["prs"][0]["title"] = "<script>alert(1)</script>"
    html = pr.render_html(m)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_states_the_detection_mode():
    assert "activity feed" in pr.render_html(model())


def test_html_renders_n_a_for_an_empty_repo():
    m = model()
    m["repos"]["opencell-core"] = {"total": 0, "rejected": 0, "rate": None,
                                   "reasons": {"declined": 0, "changes_requested": 0,
                                               "redrafted": 0}, "prs": []}
    assert "n/a" in pr.render_html(m)


def test_main_writes_both_files_and_prints_markdown(tmp_path, capsys):
    import json
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(model()))
    html, csv_path = tmp_path / "r.html", tmp_path / "r.csv"
    assert pr.main(["--model", str(model_path), "--out", str(html),
                    "--csv", str(csv_path)]) == 0
    assert "25.0%" in capsys.readouterr().out
    assert html.read_text().startswith("<!doctype html>")
    assert "r_declined" in csv_path.read_text()


def test_a_degraded_detection_mode_is_flagged_above_the_reason_table_in_html():
    """Same reasoning as the Markdown: a caveat below a second table is unread."""
    out = pr.render_html(model(draft_detection="unavailable"))
    assert out.index("could not be measured") < out.index("Rejection reasons")


def test_markdown_escapes_a_pipe_in_a_title_so_columns_do_not_shift():
    m = model()
    m["repos"]["opencell-portal"]["prs"][0]["title"] = "INTRD-1 | fix a|b mapping"
    line = [l for l in pr.render_markdown(m).splitlines() if "#11" in l][0]
    assert r"INTRD-1 \| fix a\|b mapping" in line
    # A markdown table parser splits on an unescaped `|` only. Splitting the same
    # way must still yield exactly 5 real cells (7 segments counting the leading
    # and trailing empty strings from the outer pipes) - proof the title's own
    # pipes no longer act as column delimiters.
    cells = re.split(r"(?<!\\)\|", line)
    assert len(cells) == 7, line


def test_main_creates_a_missing_output_directory(tmp_path, capsys):
    import json as _json
    model_path = tmp_path / "model.json"
    model_path.write_text(_json.dumps(model()))
    out = tmp_path / "docs" / "sub" / "r.html"
    csv_path = tmp_path / "docs" / "sub" / "r.csv"
    assert pr.main(["--model", str(model_path), "--out", str(out),
                    "--csv", str(csv_path)]) == 0
    assert out.exists() and csv_path.exists()


def test_main_writes_utf8_author_names(tmp_path, capsys):
    import json as _json
    m = model()
    m["repos"]["opencell-portal"]["prs"][0]["author"] = "Rémi Lefèvre"
    model_path = tmp_path / "model.json"
    model_path.write_text(_json.dumps(m), encoding="utf-8")
    out, csv_path = tmp_path / "r.html", tmp_path / "r.csv"
    assert pr.main(["--model", str(model_path), "--out", str(out),
                    "--csv", str(csv_path)]) == 0
    assert "Rémi Lefèvre" in csv_path.read_text(encoding="utf-8")

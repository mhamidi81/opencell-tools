import json

from conftest import SAMPLE_DIFF

import rc_pr as rp


def pr(id, title="", branch="", state="MERGED", dest="dev", updated="2026-09-01T00:00:00"):
    return {"id": id, "title": title, "state": state, "updated_on": updated,
            "source": {"branch": {"name": branch}},
            "destination": {"branch": {"name": dest}},
            "links": {"html": {"href": f"https://bitbucket.org/opencellsoft/x/pull-requests/{id}"}}}


def test_key_must_match_whole_not_as_a_prefix():            # Review Focus 1
    assert rp.mentions(pr(1, title="INTRD-45162 fix rating"), "INTRD-45162")
    assert not rp.mentions(pr(2, title="INTRD-45162 fix rating"), "INTRD-4516")
    assert rp.mentions(pr(3, branch="fix/INTRD-4516"), "INTRD-4516")
    assert rp.mentions(pr(4, title="[intrd-4516] lower case"), "INTRD-4516")


def test_select_prefers_merged_into_dev_then_newest_merged_then_newest_any():
    dev = pr(1, dest="dev", updated="2026-08-01")
    other = pr(2, dest="17.x", updated="2026-09-01")
    open_ = pr(3, state="OPEN", updated="2026-09-10")
    assert rp.select_pr([other, dev, open_])["id"] == 1
    assert rp.select_pr([other, open_])["id"] == 2
    assert rp.select_pr([open_, pr(4, state="DECLINED", updated="2026-01-01")])["id"] == 3
    assert rp.select_pr([]) is None


def test_trim_keeps_production_files_in_order_and_drops_noise():
    out = rp.trim_diff(SAMPLE_DIFF)
    assert "src/app/Grid.tsx" in out and "src/main/java/Foo.java" in out
    assert out.index("Grid.tsx") < out.index("Foo.java")
    for noise in ("Grid.test.tsx", "package-lock.json", "translation.json", "FooTest.java"):
        assert noise not in out


def test_trim_caps_bytes_without_splitting_a_character():
    big = "diff --git a/a.java b/a.java\n" + "+é\n" * 5000
    out = rp.trim_diff(big, cap=100)
    body, sep, _ = out.partition("\n… [diff truncated")
    assert sep, "truncation must be announced"
    assert len(body.encode("utf-8")) <= 100
    assert "\ufffd" not in body


def test_file_stats_cover_every_file_including_tests():
    stats = rp.diff_filestats(SAMPLE_DIFF)
    assert "src/app/Grid.test.tsx +1 -0" in stats
    assert "opencell-admin/src/main/java/Foo.java +1 -1" in stats
    assert len(stats) == 6


def test_file_stats_ignore_the_plus_plus_plus_header():
    diff = "diff --git a/x.java b/x.java\n--- a/x.java\n+++ b/x.java\n+new\n-old\n"
    assert rp.diff_filestats(diff) == ["x.java +1 -1"]


def test_file_stats_are_capped():
    many = "".join(f"diff --git a/f{i}.java b/f{i}.java\n+x\n"
                   for i in range(rp.FILESTAT_CAP + 5))
    stats = rp.diff_filestats(many)
    assert len(stats) == rp.FILESTAT_CAP + 1
    assert stats[-1] == "… 5 more files"


def test_a_diff_without_file_headers_yields_nothing():    # Review Focus 4
    assert rp.trim_diff("") == ""
    assert rp.trim_diff("Binary files differ\n") == ""
    assert rp.diff_filestats("") == []


def test_jira_evidence_shape():
    assert rp.jira_evidence("no PR found") == {
        "evidence": "jira", "pr_url": None, "pr_title": None, "files": [], "diff": "",
        "note": "no PR found"}


def test_write_batches_splits_rows_and_removes_stale_files(tmp_path):
    (tmp_path / "classify.009.jsonl").write_text("stale\n")
    rows = [{"key": f"INTRD-{i}"} for i in range(65)]

    paths = rp.write_batches(rows, str(tmp_path), size=30)

    assert [p.rsplit("/", 1)[1] for p in paths] == [
        "classify.001.jsonl", "classify.002.jsonl", "classify.003.jsonl"]
    assert not (tmp_path / "classify.009.jsonl").exists()
    lines = (tmp_path / "classify.003.jsonl").read_text().splitlines()
    assert [json.loads(l)["key"] for l in lines] == [f"INTRD-{i}" for i in range(60, 65)]

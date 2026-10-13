import json
import re

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


def row(key, diff="", evidence="jira"):
    return {"key": key, "area": "portal", "summary": "s", "excerpt": "e", "comments": ["c1"],
            "evidence": evidence, "pr_url": None, "pr_title": None, "files": [], "diff": diff}


def test_write_batches_splits_rows_and_removes_stale_files(tmp_path):
    (tmp_path / "classify.009.jsonl").write_text("stale\n")
    rows = [row(f"INTRD-{i}") for i in range(65)]

    paths = rp.write_batches(rows, str(tmp_path), size=30)

    assert [p.rsplit("/", 1)[1] for p in paths] == [
        "classify.001.md", "classify.002.md", "classify.003.md"]
    assert not (tmp_path / "classify.009.jsonl").exists()
    text = (tmp_path / "classify.003.md").read_text()
    assert re.findall(r"^## (INTRD-\d+)$", text, re.M) == [f"INTRD-{i}" for i in range(60, 65)]
import pytest

from conftest import FakeOpener, http_error
from bitbucket_client import BitbucketError, MissingToken


class StubClient:
    """Stands in for BitbucketClient.paginate; records (path, params)."""

    def __init__(self, by_slug):
        self.by_slug = by_slug
        self.calls = []

    def paginate(self, path, params=None):
        self.calls.append((path, params))
        return iter(self.by_slug.get(path.split("/")[3], []))


def fetcher(by_slug, raw_results, sleep=None):
    opener = FakeOpener(raw_results)
    f = rp.EvidenceFetcher(StubClient(by_slug), opener=opener, auth="Bearer ATCTTtok",
                           sleep=sleep or (lambda s: None))
    return f, opener


def test_diff_redirect_to_another_host_is_followed_without_credentials():  # Review Focus 2
    f, opener = fetcher({}, [
        http_error(302, headers={"Location": "https://bbuseruploads.s3.amazonaws.com/d?sig=1"}),
        b"diff body"])

    assert f.get_raw("https://api.bitbucket.org/2.0/repositories/w/r/pullrequests/1/diff") \
        == b"diff body"
    first, second = opener.requests
    assert first.get_header("Authorization") == "Bearer ATCTTtok"
    assert second.full_url.startswith("https://bbuseruploads.s3.amazonaws.com/")
    assert second.get_header("Authorization") is None


def test_same_host_redirect_keeps_credentials():
    f, opener = fetcher({}, [http_error(302, headers={"Location": "/2.0/other"}), b"ok"])
    f.get_raw("https://api.bitbucket.org/2.0/x")
    assert opener.requests[1].full_url == "https://api.bitbucket.org/2.0/other"
    assert opener.requests[1].get_header("Authorization") == "Bearer ATCTTtok"


def test_raw_fetch_retries_rate_limits():                  # Review Focus 3
    slept = []
    f, _ = fetcher({}, [http_error(429), http_error(503), b"ok"], sleep=slept.append)
    assert f.get_raw("https://api.bitbucket.org/2.0/x") == b"ok"
    assert slept == [2, 4]


def test_raw_fetch_401_names_both_schemes():
    f, _ = fetcher({}, [http_error(401)])
    with pytest.raises(BitbucketError) as ex:
        f.get_raw("https://api.bitbucket.org/2.0/x")
    message = str(ex.value)
    assert message.startswith("HTTP 401")
    assert "Bearer" in message and "ATATT" in message


def test_evidence_picks_the_dev_pr_and_trims_its_diff():
    prs = [pr(7, title="INTRD-1 fix", dest="17.x", updated="2026-09-05"),
           pr(8, title="INTRD-1 fix", dest="dev", updated="2026-09-01"),
           pr(9, title="INTRD-10 unrelated")]
    f, opener = fetcher({"opencell-portal": prs}, [SAMPLE_DIFF.encode()])

    ev = f.evidence_for({"key": "INTRD-1", "area": "portal"})

    assert ev["evidence"] == "pr" and ev["note"] is None
    assert ev["pr_url"].endswith("/pull-requests/8")
    assert opener.urls()[0].endswith(
        "/repositories/opencellsoft/opencell-portal/pullrequests/8/diff")
    assert "Grid.test.tsx" not in ev["diff"]
    assert "src/app/Grid.test.tsx +1 -0" in ev["files"]
    _, params = f.client.calls[0]
    assert params["q"] == '(title ~ "INTRD-1" OR source.branch.name ~ "INTRD-1")'
    assert params["state"] == rp.PR_STATES


def test_an_arealess_bug_is_looked_up_in_both_repositories():  # Review Focus 5
    f, opener = fetcher({
        "opencell-portal": [pr(1, title="INTRD-5", state="OPEN", updated="2026-09-09")],
        "opencell-core": [pr(2, title="INTRD-5", updated="2026-09-01")]}, [b""])

    ev = f.evidence_for({"key": "INTRD-5", "area": None})

    assert [path.split("/")[3] for path, _ in f.client.calls] == [
        "opencell-portal", "opencell-core"]
    assert opener.urls()[0].endswith("/opencell-core/pullrequests/2/diff")  # merged wins
    assert ev["evidence"] == "pr"


def test_no_matching_pr_falls_back_to_jira():
    f, _ = fetcher({"opencell-core": [pr(3, title="INTRD-10 not this one")]}, [])
    assert f.evidence_for({"key": "INTRD-1", "area": "core"}) == rp.jira_evidence("no PR found")


class StubFetcher:
    def __init__(self, outcomes):
        self.outcomes = dict(outcomes)
        self.seen = []

    def evidence_for(self, bug):
        self.seen.append(bug["key"])
        outcome = self.outcomes[bug["key"]]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


PR_EV = {"evidence": "pr", "pr_url": "u", "pr_title": "t", "files": ["a +1 -0"],
         "diff": "d", "note": None}
BUGS = [{"key": f"INTRD-{i}", "area": "portal"} for i in (1, 2, 3)]


def test_a_401_stops_all_further_lookups(tmp_path):
    warnings = []
    f = StubFetcher({"INTRD-1": BitbucketError("HTTP 401 on GET x: rejected")})

    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)

    assert f.seen == ["INTRD-1"]
    assert all(e["evidence"] == "jira" for e in ev.values())
    assert ev["INTRD-3"]["note"] == "Bitbucket 401"
    assert "Jira-only" in warnings[0]


def test_one_failed_lookup_does_not_stop_the_others(tmp_path):
    warnings = []
    f = StubFetcher({"INTRD-1": BitbucketError("HTTP 500 on GET x"), "INTRD-2": PR_EV,
                     "INTRD-3": rp.jira_evidence("no PR found")})

    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)

    assert ev["INTRD-1"]["note"] == "PR lookup failed"
    assert ev["INTRD-2"] == PR_EV
    assert "INTRD-1" in warnings[0]


def test_pr_evidence_is_cached_and_jira_fallbacks_are_not(tmp_path):
    rp.gather_all(BUGS, StubFetcher({"INTRD-1": PR_EV, "INTRD-2": rp.jira_evidence("no PR found"),
                                     "INTRD-3": PR_EV}), str(tmp_path))
    again = StubFetcher({"INTRD-2": rp.jira_evidence("no PR found")})

    ev = rp.gather_all(BUGS, again, str(tmp_path))

    assert again.seen == ["INTRD-2"]
    assert ev["INTRD-1"] == PR_EV


def test_no_fetcher_means_jira_only_without_reading_the_cache(tmp_path):
    (tmp_path / "INTRD-1.json").write_text(json.dumps(PR_EV))
    ev = rp.gather_all(BUGS, None, str(tmp_path), disabled_reason="--no-pr")
    assert ev["INTRD-1"] == rp.jira_evidence("--no-pr")


FULL = [{"key": "INTRD-1", "area": "portal", "summary": "s", "excerpt": "e",
         "comments": ["c"]}]


def run_main(tmp_path, extra, factory, warnings=None):
    bugs = tmp_path / "bugs.json"
    bugs.write_text(json.dumps({"repo": "both", "bugs": FULL}))
    out = tmp_path / "classify_input.jsonl"
    code = rp.main(["--bugs", str(bugs), "--run", str(tmp_path), "--out-classify", str(out)]
                   + extra, fetcher_factory=factory,
                   warn=(warnings.append if warnings is not None else lambda m: None))
    return code, [json.loads(l) for l in out.read_text().splitlines()]


def test_main_without_a_token_continues_jira_only(tmp_path):
    warnings = []

    def no_token():
        raise MissingToken("BITBUCKET_ACCESS_TOKEN must be set")

    code, rows = run_main(tmp_path, [], no_token, warnings)

    assert code == 0
    assert rows[0]["evidence"] == "jira"
    assert rows[0]["summary"] == "s" and rows[0]["comments"] == ["c"]
    assert "Jira-only" in warnings[0]
    assert (tmp_path / "batches" / "classify.001.md").exists()


def test_main_no_pr_never_builds_a_fetcher(tmp_path):
    def boom():
        raise AssertionError("must not be called with --no-pr")

    code, rows = run_main(tmp_path, ["--no-pr"], boom)
    assert code == 0 and rows[0]["evidence"] == "jira"


# ------------------------------------------------------------ final-review fixes


def test_batches_are_readable_text_with_the_diff_unescaped(tmp_path):
    r = dict(row("INTRD-1", diff='diff --git a/a.ts b/a.ts\n+x = "q"\n', evidence="pr"),
             pr_url="https://bb/pr/1", pr_title="INTRD-1 fix", files=["a.ts +1 -0"])
    [path] = rp.write_batches([r], str(tmp_path))
    text = open(path, encoding="utf-8").read()
    assert "Keys: INTRD-1" in text and "## INTRD-1" in text
    assert '+x = "q"' in text             # not JSON-escaped
    assert text.index("### Diff") < text.index("### Description")   # evidence before prose
    assert "https://bb/pr/1" in text and "a.ts +1 -0" in text


def test_batch_lines_are_capped_for_the_read_tool(tmp_path):
    [path] = rp.write_batches([row("INTRD-1", diff="diff --git a/a b/a\n+" + "x" * 5000 + "\n",
                                   evidence="pr")], str(tmp_path))
    assert max(len(l) for l in open(path, encoding="utf-8").read().splitlines()) <= rp.LINE_CAP + 1


def test_a_transport_error_on_one_bug_does_not_stop_the_run(tmp_path):
    import urllib.error
    warnings = []
    f = StubFetcher({"INTRD-1": urllib.error.URLError("timed out"), "INTRD-2": PR_EV,
                     "INTRD-3": ValueError("bad JSON")})
    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)
    assert ev["INTRD-1"]["note"] == ev["INTRD-3"]["note"] == "PR lookup failed"
    assert ev["INTRD-2"] == PR_EV
    assert len(warnings) == 2


def test_an_exhausted_rate_limit_stops_lookups_and_asks_for_a_rerun(tmp_path):
    warnings = []
    f = StubFetcher({"INTRD-1": PR_EV, "INTRD-2": BitbucketError("HTTP 429 on GET x: slow down")})
    ev = rp.gather_all(BUGS, f, str(tmp_path), warn=warnings.append)
    assert f.seen == ["INTRD-1", "INTRD-2"]
    assert ev["INTRD-2"]["note"] == ev["INTRD-3"]["note"] == "Bitbucket rate limit"
    assert "re-run" in warnings[0]


def test_main_exits_4_when_a_lookup_failed(tmp_path):
    class Failing:
        def evidence_for(self, bug):
            raise BitbucketError("HTTP 500 on GET x")

    code, rows = run_main(tmp_path, [], lambda: Failing())
    assert code == rp.LOOKUPS_FAILED
    assert rows[0]["evidence"] == "jira"


def test_a_later_pr_that_only_mentions_the_key_does_not_win():
    real = pr(1, title="INTRD-1 fix", branch="fix/INTRD-1", updated="2026-08-01")
    later = pr(2, title="INTRD-9 fix regression from INTRD-1", branch="fix/INTRD-9",
               updated="2026-09-01")
    assert rp.select_pr([later, real], "INTRD-1")["id"] == 1
    assert rp.select_pr([later], "INTRD-1")["id"] == 2      # a mention beats nothing
    assert rp.select_pr([pr(3, title="[INTRD-1] fix"), later], "INTRD-1")["id"] == 3

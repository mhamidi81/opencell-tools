"""Tests for jira_links.py — run: python3 -m unittest test_jira_links (from this directory)."""
import unittest

from jira_links import JIRA_BROWSE, process


def linked(key):
    return f"[{key}]({JIRA_BROWSE}{key})"


def keys(text):
    return [k for _, k in process(text)[1]]


class Keys(unittest.TestCase):
    def test_projects_and_boundaries(self):
        self.assertEqual(keys("INTRD-1, CR-2; SUPS-3 MACRD-4 INTCA-5 INTCS-6"),
                         ["INTRD-1", "CR-2", "SUPS-3", "MACRD-4", "INTCA-5", "INTCS-6"])

    def test_not_keys(self):
        # placeholders, other codes, file names, addresses, glued words
        self.assertEqual(keys("INTRD-44489-S1 NEW-12 DR-27 ADR-0001 CR-1.txt x@CR-9.org XINTRD-1 INTRD-1a"), [])

    def test_punctuation_around(self):
        self.assertEqual(keys("(INTRD-1) «INTRD-2» INTRD-3's INTRD-4..5 **INTRD-6** INTRD-7."),
                         ["INTRD-1", "INTRD-2", "INTRD-3", "INTRD-4", "INTRD-6", "INTRD-7"])

    def test_underscore_emphasis_and_ranges(self):
        self.assertEqual(keys("_INTRD-1_ __INTRD-2__ INTRD-3-INTRD-4"), ["INTRD-1", "INTRD-2", "INTRD-3", "INTRD-4"])

    def test_line_endings_kept(self):
        out, _ = process("a INTRD-1\r\nb\r\n")
        self.assertEqual(out, f"a {linked('INTRD-1')}\r\nb\r\n")

    def test_rule_then_blank_is_not_front_matter(self):
        self.assertEqual(keys("---\n\n# Title INTRD-1\n\n---\n"), ["INTRD-1"])

    def test_fix_rewrites_and_is_idempotent(self):
        once, found = process("See INTRD-1 and CR-2.")
        self.assertEqual(once, f"See {linked('INTRD-1')} and {linked('CR-2')}.")
        self.assertEqual(len(found), 2)
        twice, again = process(once)
        self.assertEqual((twice, again), (once, []))


class Protected(unittest.TestCase):
    def test_front_matter(self):
        self.assertEqual(keys("---\ntitle: 'INTRD-1'\n---\nINTRD-2"), ["INTRD-2"])

    def test_code(self):
        self.assertEqual(keys("`INTRD-1` ``a `INTRD-2` b`` INTRD-3\n```\nINTRD-4\n```\n~~~\nINTRD-5\n~~~"), ["INTRD-3"])

    def test_links_and_urls(self):
        text = (f"{linked('INTRD-1')} [see `x` INTRD-2](https://x.y) ![INTRD-3](a.png) [INTRD-4][ref] "
                "<https://x.y/INTRD-5> https://x.y/browse/INTRD-6 INTRD-7")
        self.assertEqual(keys(text), ["INTRD-7"])

    def test_comments_and_notes(self):
        self.assertEqual(keys("<!-- note: INTRD-1 -->\n<!--\nINTRD-2\n-->\na <!-- INTRD-3 --> INTRD-4"), ["INTRD-4"])

    def test_comment_opened_inline_resumes_markdown_after_close(self):
        self.assertEqual(keys("a INTRD-1 <!-- x\nINTRD-2\n--> INTRD-3"), ["INTRD-1", "INTRD-3"])

    def test_comment_block_closing_line_stays_raw(self):
        self.assertEqual(keys("<!--\nINTRD-1\n--> INTRD-2\n\nINTRD-3"), ["INTRD-3"])

    def test_html_blocks(self):
        text = ("<style>\n.x { content: 'INTRD-1'; }\n</style>\n\n"
                "<div class=\"a\">\n<figure><svg><title>INTRD-2</title></svg></figure>\n</div>\n\n"
                "<span>alone</span>\n\nINTRD-3")
        self.assertEqual(keys(text), ["INTRD-3"])

    def test_inline_tags_are_not_blocks(self):
        # a line opening on an inline tag with text after it is a paragraph: Markdown applies
        self.assertEqual(keys("<b>bold</b> then INTRD-1\n| <span class=\"sw\"></span> INTRD-2 |"),
                         ["INTRD-1", "INTRD-2"])

    def test_comment_opener_in_code_is_not_a_comment(self):
        self.assertEqual(keys("`<!--` opens a Marp note.\n\nINTRD-1 later"), ["INTRD-1"])

    def test_lone_tag_inside_a_paragraph_is_not_a_block(self):
        self.assertEqual(keys("Some text INTRD-1\n<br>\nINTRD-2 after br"), ["INTRD-1", "INTRD-2"])

    def test_html_block_behind_list_or_quote(self):
        self.assertEqual(keys("- <div class=\"c\">\n  INTRD-1\n  </div>\n\n> <div>\n> INTRD-2\n> </div>\n\nINTRD-3"),
                         ["INTRD-3"])

    def test_fence_closes_only_on_a_long_enough_run(self):
        self.assertEqual(keys("````\n```\nINTRD-1\n````\nINTRD-2"), ["INTRD-2"])

    def test_tables_and_headings(self):
        self.assertEqual(keys("## INTRD-1 heading\n| CR-2 | x |\n|---|---|"), ["INTRD-1", "CR-2"])


class Copies(unittest.TestCase):
    def test_decks_copy_is_identical(self):
        # skills take no dependency on each other, so oc-fn-decks carries its own copy
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        other = os.path.join(here, "..", "oc-fn-decks", "jira_links.py")
        if not os.path.exists(other):
            self.skipTest("oc-fn-decks not beside this skill")
        with open(os.path.join(here, "jira_links.py"), "rb") as a, open(other, "rb") as b:
            self.assertEqual(a.read(), b.read(), "oc-fn-briefs/jira_links.py and oc-fn-decks/jira_links.py differ")


if __name__ == "__main__":
    unittest.main()

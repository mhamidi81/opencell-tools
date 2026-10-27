#!/usr/bin/env python3
"""jira_links.py — every Jira work-item key in a Markdown document becomes a link to Jira.

  jira_links.py --check FILE...   list the bare keys as FILE:LINE: KEY; exit 1 if there is any
  jira_links.py --fix FILE...     rewrite them in place as [KEY](https://opencellsoft.atlassian.net/browse/KEY)

The rule (oc-fn-briefs and oc-fn-decks, CPO 2026-10-27): in a document read inside Opencell —
a brief, a note, a deck — every Jira key is a link, so a reader opens the item instead of
looking it up. The internal render lanes refuse a source that still has a bare key; `--fix`
is the one-step repair. Shared by both skills (they ship together in oc-fn-tools).

Only what Markdown would render as a link is touched. Left as they are:
- the YAML front matter, fenced code blocks and inline code — `INTRD-1` in backticks is the way
  to keep one key plain on purpose;
- HTML comments (deck speaker notes, metadata blocks): a note reaches PowerPoint as plain text;
- raw HTML, where Markdown is not parsed: an HTML block (CommonMark types 1, 2, 6 and 7, also
  when it opens a list item or a block quote) and inline tags;
- existing links and images, autolinks and bare URLs.

A key is one of the projects below, standing alone: INTRD-44489-S1, NEW-12, CR-1.txt and DR-27
stay text; _INTRD-1_ (emphasis) and INTRD-1-INTRD-2 (a range) link. The file's line endings are
kept.

Known gaps, rare in briefs and decks: indented (4-space) code blocks, reference-style link
definitions, a link text, code span or tag wrapped over two lines, pandoc attributes ({#id}),
math and citations. Put such a key in backticks if it must stay plain.
"""
import re
import sys

JIRA_BROWSE = "https://opencellsoft.atlassian.net/browse/"
JIRA_PROJECTS = ("INTRD", "SUPS", "CR", "MACRD", "INTCA", "INTCS")
_P = "|".join(JIRA_PROJECTS)
# Not glued to a letter, digit or dot before it, nor to a hyphenated word (NEW-INTRD-1); a hyphen
# right after a number is a range (INTRD-1-INTRD-2). After it: no letter or digit, no ".ext", no
# "@", and a hyphen only when another key follows. Underscores are emphasis, so they do not glue.
KEY_RE = re.compile(r"(?<![A-Za-z0-9.])(?<![A-Za-z.]-)((?:%s)-[0-9]+)"
                    r"(?![A-Za-z0-9]|-(?!(?:%s)-[0-9])|\.\w|@)" % (_P, _P))

# Spans of one line that Markdown does not render as plain text, matched left to right.
SPAN_RE = re.compile(
    r"(?P<code>(?P<ticks>`+).+?(?P=ticks))"                       # inline code, any fence length
    r"|(?P<comment><!--.*?-->)"                                    # an HTML comment closed on the line
    r"|(?P<link>!?\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\([^)\n]*\))"  # [text](url), ![alt](src), one nesting
    r"|(?P<ref>!?\[[^\[\]\n]*\]\[[^\]\n]*\])"                      # [text][ref]
    r"|(?P<auto><https?://[^>\s]+>)"                               # <https://…>
    r"|(?P<tag></?[A-Za-z][^<>\n]*>)"                              # an inline HTML tag
    r"|(?P<url>https?://[^\s<>()\"']+)"                            # a bare URL
)
# Container prefixes a block can sit behind: list markers and block quotes, nested.
CONTAINER = re.compile(r"^(?:\s*(?:[-*+]|\d{1,9}[.)])\s+|\s*>\s?)*")
RAW_BLOCK = re.compile(r"^\s{0,3}<(style|script|pre|textarea)\b", re.I)
BLOCK_TAGS = ("address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|"
              "dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|"
              "hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|"
              "search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul")
HTML_BLOCK6 = re.compile(r"^\s{0,3}</?(?:%s)(?:\s|/?>|$)" % BLOCK_TAGS, re.I)     # interrupts a paragraph
HTML_BLOCK7 = re.compile(r"^\s{0,3}</?[A-Za-z][\w-]*(?:\s[^<>]*)?/?>\s*$")       # a lone tag: does not
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def link(key):
    return f"[{key}]({JIRA_BROWSE}{key})"


def open_comment_at(line):
    """Index where an HTML comment opens on this line, outside code and other spans, and is not
    closed on it; -1 if there is none."""
    pos = 0
    while True:
        m = SPAN_RE.search(line, pos)
        stop = m.start() if m else len(line)
        t = line.find("<!--", pos, stop)
        if t != -1:
            return t           # a closed comment would have matched SPAN_RE first
        if not m:
            return -1
        pos = m.end()


def scan_line(line):
    """Yield (start, end, key) for each bare key of one line outside the protected spans.

    A comment opened on the line and not closed there protects the rest of the line."""
    limit = open_comment_at(line)
    if limit == -1:
        limit = len(line)
    pos = 0
    while pos < limit:
        m = SPAN_RE.search(line, pos, limit)
        stop = m.start() if m else limit
        for k in KEY_RE.finditer(line, pos, stop):
            yield k.start(1), k.end(1), k.group(1)
        if not m:
            break
        pos = m.end()


def link_line(line, no, found):
    """Link the bare keys of one line; record them in found as (line_no, key)."""
    hits = list(scan_line(line))
    for _, _, key in hits:
        found.append((no, key))
    for start, end, key in reversed(hits):
        line = line[:start] + link(key) + line[end:]
    return line, hits


def process(text):
    """Return (new_text, [(line_no, key), ...]) with every bare key linked. Line endings kept."""
    out, found = [], []
    lines = text.splitlines(keepends=True)
    first = lines[0].lstrip("﻿").strip() if lines else ""
    in_front = first == "---" and len(lines) > 1 and lines[1].strip() != ""
    fence = None         # (char, length) of the code fence we are in
    comment = False      # inside a multi-line HTML comment
    inline = False       # ... opened inside a paragraph, so the text after its "-->" is Markdown again
    raw_end = None       # closing tag that ends a <style>/<script>/<pre>/<textarea> block
    html_block = False   # inside an HTML block, which ends at a blank line
    prev_blank = True    # a lone tag (type 7) opens an HTML block only after a blank line
    for i, full in enumerate(lines):
        no = i + 1
        line = full.rstrip("\r\n")
        eol = full[len(line):]
        if in_front:
            out.append(full)
            if i > 0 and line.strip() in ("---", "..."):
                in_front = False
            continue
        if fence:
            out.append(full)
            m = FENCE.match(line[CONTAINER.match(line).end():])
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not line[CONTAINER.match(line).end():].strip()[len(m.group(1)):].strip():
                fence = None
            continue
        if comment:
            if "-->" not in line:
                out.append(full)
                continue
            comment = False
            prev_blank = False
            if not inline:
                out.append(full)
                continue
            cut = line.index("-->") + 3
            new, _ = link_line(line[cut:], no, found)
            out.append(line[:cut] + new + eol)
            if open_comment_at(new) != -1:
                comment, inline = True, True
            continue
        if raw_end:
            out.append(full)
            if raw_end in line.lower():
                raw_end = None
            continue
        if html_block:
            out.append(full)
            if not line.strip():
                html_block = False
                prev_blank = True
            continue
        inner = line[CONTAINER.match(line).end():]
        m = FENCE.match(inner)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            out.append(full)
            continue
        m = RAW_BLOCK.match(inner)
        if m:
            tag = m.group(1).lower()
            if f"</{tag}>" not in line.lower():
                raw_end = f"</{tag}>"
            out.append(full)
            continue
        if HTML_BLOCK6.match(inner) or (prev_blank and HTML_BLOCK7.match(inner)):
            html_block = True
            out.append(full)
            continue
        if inner.lstrip().startswith("<!--") and open_comment_at(inner) != -1:
            comment, inline = True, False
            out.append(full)
            continue
        new, _ = link_line(line, no, found)
        if open_comment_at(new) != -1:
            comment, inline = True, True
        out.append(new + eol)
        prev_blank = not line.strip()
    return "".join(out), found


def main(argv):
    if len(argv) < 3 or argv[1] not in ("--check", "--fix"):
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    mode, files, bare = argv[1], argv[2:], 0
    for path in files:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        new, found = process(text)
        bare += len(found)
        if mode == "--check":
            for no, key in found:
                print(f"{path}:{no}: {key}")
        elif found:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            print(f"{path}: {len(found)} key(s) linked")
    return 1 if (mode == "--check" and bare) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""fragment.py — turn a marp-cli bespoke HTML document into a claude.ai Artifact fragment.

Called by render-artifact.sh; not meant to be run by hand.

marp-cli emits a complete document (doctype, head with its stylesheets, body with the
bespoke viewer). The Artifact tool wraps every page in its own doctype/head/body skeleton at
publish, and scans only the first 8 KB for the <title>. So this keeps the parts that carry
the deck and drops the document shell:

  <title> first, then the provenance comment, then the theme-switch head script, then the
  head <style>s, the page layer, the body as marp-cli wrote it (with the switch button added
  to the on-screen controls), and the switch tail script last.

The <meta> tags go: the skeleton brings its own charset and viewport.
"""

import argparse
import html
import pathlib
import re
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--art", required=True, help="the skill's artifact/ directory")
    ap.add_argument("--stamp", required=True, help="provenance line for the HTML comment")
    ap.add_argument("--pagetitle", default="", help="gallery name; falls back to Marp's <title>")
    a = ap.parse_args()

    doc = pathlib.Path(a.src).read_text(encoding="utf-8")
    art = pathlib.Path(a.art)

    head = re.search(r"<head>(.*?)</head>", doc, re.S)
    body = re.search(r"<body[^>]*>(.*)</body>", doc, re.S)
    if not head or not body:
        sys.exit("fragment.py: marp-cli output has no <head>/<body> — did the render change shape?")
    head, body = head.group(1), body.group(1)

    title = a.pagetitle.strip()
    if not title:
        m = re.search(r"<title>(.*?)</title>", head, re.S)
        title = html.unescape(m.group(1)).strip() if m else "Opencell deck"
    styles = re.findall(r"<style\b[^>]*>.*?</style>", head, re.S)

    # The switch joins Marp's own on-screen controls, so it appears and fades with them and
    # inherits their styling; the controls div holds only buttons and a span, so its first
    # closing </div> is its own.
    osc = body.find('<div class="bespoke-marp-osc">')
    if osc < 0:
        sys.exit("fragment.py: no bespoke on-screen controls in marp-cli output — was --html used?")
    end = body.index("</div>", osc)
    body = body[:end] + (art / "switch.html").read_text(encoding="utf-8").strip() + body[end:]

    # The stamp is written into an HTML comment: it must not be able to close it early.
    stamp = a.stamp.replace("--", "—")
    parts = [
        f"<title>{html.escape(title)}</title>",
        f"<!-- {stamp} -->",
        "<script>\n" + (art / "head.js").read_text(encoding="utf-8").strip() + "\n</script>",
        *styles,
        "<style>\n" + (art / "page.css").read_text(encoding="utf-8").strip() + "\n</style>",
        body.strip(),
        "<script>\n" + (art / "tail.js").read_text(encoding="utf-8").strip() + "\n</script>",
    ]
    pathlib.Path(a.out).write_text("\n".join(parts) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

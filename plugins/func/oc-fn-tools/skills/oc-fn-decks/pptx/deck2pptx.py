#!/usr/bin/env python3
"""Render a Marp-convention Opencell deck to an official-template PPTX.

One command from the shared .md source: bridges the Marp dialect to pandoc,
renders against the curated reference template, then applies the red closing
bookend. The .md stays the source of truth for both lanes (Marp HTML + this).

Bridge transformations (everything else passes through untouched):
  1. drops the explicit lead title slide — pandoc rebuilds the cover from the
     front-matter metadata (title / subtitle / author), which the title slide
     must mirror;
  2. converts `<!-- note: ... -->` comments into pandoc `::: notes` divs so
     they become PowerPoint speaker notes (Marp already shows the same
     comments in presenter view);
  3. Marp's `---` separators and directive comments need no translation —
     pandoc absorbs both silently (verified: no empty slides).

Before rendering, the bridged deck is refused if pandoc would silently lose
content: inside a `::: column` div the PPTX writer keeps the blocks up to and
including the FIRST table and drops everything after it — a second table,
prose, bullets — with no warning (verified on pandoc 3.1.11). On an ordinary
slide the same content goes to a continuation slide instead, so only columns
need the guard.

Usage: deck2pptx.py <deck.md> [-o out.pptx] [--ref reference.pptx]
       --ref defaults to ./assets/pptx/opencell-slides-ref.pptx (repo working
       copy, run from the repo root), falling back to the copy next to this
       script. Requires pandoc >= 2.15 (embedded-font copy).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SEP = re.compile(r"^---\s*$", re.M)


def split_front_matter(text):
    m = re.match(r"\A---\s*\n.*?\n---\s*\n", text, re.S)
    if not m:
        sys.exit("FATAL: no YAML front-matter — the PPTX lane needs "
                 "title/subtitle/author metadata (see pptx.md)")
    return text[:m.end()], text[m.end():]


def bridge(text):
    fm, body = split_front_matter(text)
    for key in ("title",):
        if not re.search(rf"^{key}\s*:", fm, re.M):
            sys.exit(f"FATAL: front-matter lacks {key!r} — pandoc builds the "
                     "cover from metadata")
    slides = SEP.split(body)
    # the explicit Marp title slide duplicates the front-matter — drop it
    if slides and "_class: lead" in slides[0]:
        slides = slides[1:]
    body = "\n---\n".join(slides)
    body = re.sub(r"<!--\s*note:\s*(.*?)-->",
                  lambda m: "::: notes\n" + m.group(1).strip() + "\n:::",
                  body, flags=re.S)
    return fm + body


def plain(node):
    """Flatten a pandoc AST fragment to text (for naming a slide in an error)."""
    if isinstance(node, list):
        return "".join(plain(x) for x in node)
    if not isinstance(node, dict):
        return ""                         # attributes, URLs: not title text
    if node["t"] == "Str":
        return node["c"]
    if node["t"] in ("Space", "SoftBreak", "LineBreak"):
        return " "
    if node["t"] in ("Code", "Math"):
        return node["c"][-1]
    return plain(node.get("c", []))


def check_columns(md_path):
    """Exit if any column holds a block after its first table (pandoc drops it)."""
    ast = json.loads(subprocess.run(["pandoc", md_path, "-t", "json"],
                                    capture_output=True, text=True, check=True).stdout)
    problems, title = [], ["(before the first slide title)"]

    def classes(div):
        return div["c"][0][1]

    def walk(blocks):
        for b in blocks:
            if b["t"] == "Header":
                title[0] = plain(b["c"][2])
            elif b["t"] == "Div":
                inner = b["c"][1]
                if "columns" in classes(b):
                    cols = [x for x in inner if x["t"] == "Div" and "column" in classes(x)]
                    for n, col in enumerate(cols, 1):
                        kinds = [x["t"] for x in col["c"][1]]
                        if "Table" in kinds and kinds.index("Table") < len(kinds) - 1:
                            lost = kinds[kinds.index("Table") + 1:]
                            problems.append(f'  slide "{title[0]}", column {n}: '
                                            f'{", ".join(lost)} after the first table')
                walk(inner)

    walk(ast["blocks"])
    if problems:
        sys.exit("FATAL: pandoc would silently drop content in these columns — it "
                 "keeps a column's blocks up to its first table and loses the rest:\n"
                 + "\n".join(problems)
                 + "\nKeep at most one table per column, as its last block, or move "
                   "the rest out of the columns (see pptx.md).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("-o", "--output")
    ap.add_argument("--ref")
    args = ap.parse_args()

    out = args.output or os.path.splitext(args.deck)[0] + ".pptx"
    ref = args.ref or next(
        (p for p in (os.path.join("assets", "pptx", "opencell-slides-ref.pptx"),
                     os.path.join(HERE, "opencell-slides-ref.pptx"))
         if os.path.exists(p)), None)
    if not ref:
        sys.exit("FATAL: no reference template found — pass --ref or add "
                 "assets/pptx/opencell-slides-ref.pptx to the repo")

    bridged = bridge(open(args.deck, encoding="utf-8").read())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     dir=os.path.dirname(os.path.abspath(args.deck)),
                                     encoding="utf-8") as f:
        f.write(bridged)  # same dir so relative image paths keep resolving
        tmp = f.name
    try:
        check_columns(tmp)
        subprocess.run(["pandoc", tmp, "-o", out,
                        f"--reference-doc={ref}", "--slide-level=2"], check=True)
    finally:
        os.unlink(tmp)
    subprocess.run([sys.executable, os.path.join(HERE, "close_deck.py"), out],
                   check=True)
    print(f"wrote {out} (reference: {ref})")


if __name__ == "__main__":
    main()

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

Usage: deck2pptx.py <deck.md> [-o out.pptx] [--ref reference.pptx]
       --ref defaults to ./assets/pptx/opencell-slides-ref.pptx (repo working
       copy, run from the repo root), falling back to the copy next to this
       script. Requires pandoc >= 2.15 (embedded-font copy).
"""
import argparse
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
        subprocess.run(["pandoc", tmp, "-o", out,
                        f"--reference-doc={ref}", "--slide-level=2"], check=True)
    finally:
        os.unlink(tmp)
    subprocess.run([sys.executable, os.path.join(HERE, "close_deck.py"), out],
                   check=True)
    print(f"wrote {out} (reference: {ref})")


if __name__ == "__main__":
    main()

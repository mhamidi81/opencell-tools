#!/usr/bin/env python3
"""Finishing pass for a pandoc-generated Opencell deck.

One package fix and two per-slide corrections pandoc cannot make itself:

0. Content types — pandoc (verified on 3.1.11) copies the reference doc's
   embedded fonts (ppt/fonts/*.fntdata) but drops their Default declaration
   from [Content_Types].xml, leaving an invalid OPC package: python-pptx
   refuses to open it and strict readers may offer to repair it. Restore the
   declarations this lane is known to lose, and refuse any OTHER undeclared
   part rather than ship an invalid file.

1. Red closing bookend — pandoc maps every H1 to the single "Section Header"
   layout, so the closing "# Thank you" slide comes out as a photo section
   divider. Retarget every Section Header slide titled "Thank you" / "Merci"
   onto the red "Title Slide" layout (matching by title, not position, keeps
   the bookend red when backup slides follow the closing).

2. Caption spacing — on "Content with Caption" slides (commentary above a
   table) the caption inherits a fixed-height strip from the layout, so a
   long caption runs behind the table. Estimate each caption's rendered
   height (chars-per-line heuristic, deliberately conservative) and pin the
   caption box and the table's frame to slide-level geometry accordingly.
   Slides whose non-text content is an image keep pandoc's own placement.

No-op on decks needing none of these, so any deck passes through safely.

Usage: close_deck.py <deck.pptx>
"""
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile

# content types pandoc drops when it copies parts from --reference-doc
KNOWN_CONTENT_TYPES = {"fntdata": "application/x-fontdata"}

CLOSING_TITLE = re.compile(r"^(thank\s*you|merci)\s*[!.]?$", re.I)

# caption-spacing geometry (EMU), matched to the curated layout's content zone
CAP_X, CAP_W = 838201, 10515600
CAP_Y = 980000            # below the title band
GAP = 150000              # caption -> table
BOTTOM = 5580363          # content zone floor (footer starts below)
CHARS_PER_LINE = 70       # ~18pt Montserrat across CAP_W; low on purpose
LINE_H = 300000           # 18pt line incl. spacing, rounded up


def restore_content_types(tmp):
    """Declare every part pandoc left without a content type; return the fixes."""
    path = os.path.join(tmp, "[Content_Types].xml")
    xml = open(path, encoding="utf-8").read()
    defaults = {e.lower() for e in re.findall(r'<Default\s+Extension="([^"]+)"', xml)}
    overrides = set(re.findall(r'<Override\s+PartName="([^"]+)"', xml))
    missing = set()
    for walk_root, _, files in os.walk(tmp):
        for f in files:
            part = "/" + os.path.relpath(os.path.join(walk_root, f), tmp).replace(os.sep, "/")
            if part == "/[Content_Types].xml" or part in overrides:
                continue
            ext = f.rsplit(".", 1)[-1].lower() if "." in f else ""
            if ext not in defaults:
                missing.add(ext)
    unknown = sorted(missing - KNOWN_CONTENT_TYPES.keys())
    if unknown:
        sys.exit("FATAL: parts with no declared content type: "
                 + ", ".join(f".{e}" if e else "(no extension)" for e in unknown)
                 + " — add the type to KNOWN_CONTENT_TYPES in close_deck.py")
    if missing:
        add = "".join(f'<Default Extension="{e}" ContentType="{KNOWN_CONTENT_TYPES[e]}"/>'
                      for e in sorted(missing))
        xml = re.sub(r"(<Types\b[^>]*>)", lambda m: m.group(1) + add, xml, count=1)
        open(path, "w", encoding="utf-8").write(xml)
    return sorted(missing)


def layout_name(root, layout_file):
    xml = open(os.path.join(root, "ppt/slideLayouts", layout_file), encoding="utf-8").read()
    return re.search(r'<p:cSld name="([^"]*)"', xml).group(1)


def retarget(tmp, slide, cover):
    rels_path = os.path.join(tmp, "ppt/slides/_rels", slide + ".rels")
    rels = open(rels_path, encoding="utf-8").read()
    current = re.search(r"slideLayout\d+\.xml", rels).group(0)
    open(rels_path, "w", encoding="utf-8").write(rels.replace(current, cover))
    # retype the title AND drop pandoc's explicit position so the slide fully
    # inherits the cover's white ctrTitle placeholder (style + geometry)
    slide_path = os.path.join(tmp, "ppt/slides", slide)
    xml = open(slide_path, encoding="utf-8").read()
    xml, n = re.subn(r'<p:ph type="title"\s*/>', '<p:ph type="ctrTitle"/>', xml, count=1)
    if n != 1:
        sys.exit(f"FATAL: no title placeholder found on {slide}")
    title_sp = next(m.group(0) for m in re.finditer(r"<p:sp>.*?</p:sp>", xml, re.S)
                    if "ctrTitle" in m.group(0))
    xml = xml.replace(title_sp,
                      re.sub(r"<a:xfrm>.*?</a:xfrm>", "", title_sp, count=1, flags=re.S), 1)
    open(slide_path, "w", encoding="utf-8").write(xml)


def space_caption(tmp, slide):
    """Pin caption height + table position on one Content-with-Caption slide."""
    path = os.path.join(tmp, "ppt/slides", slide)
    xml = open(path, encoding="utf-8").read()
    if "<p:graphicFrame>" not in xml:
        return False                      # image content: pandoc placed it itself
    cap = next((m.group(0) for m in re.finditer(r"<p:sp>.*?</p:sp>", xml, re.S)
                if 'idx="2"' in m.group(0)), None)
    if not cap:
        return False

    paras = [len("".join(re.findall(r"<a:t>([^<]*)</a:t>", p)))
             for p in re.findall(r"<a:p>.*?</a:p>", cap, re.S)]
    lines = sum(max(1, math.ceil(n / CHARS_PER_LINE)) for n in paras)
    cap_h = lines * LINE_H + 100000
    table_y = CAP_Y + cap_h + GAP

    # pandoc self-closes with a space (<p:spPr />) and may already carry an
    # xfrm — replace what exists rather than inserting a duplicate
    xfrm = (f'<a:xfrm><a:off x="{CAP_X}" y="{CAP_Y}"/>'
            f'<a:ext cx="{CAP_W}" cy="{cap_h}"/></a:xfrm>')
    if re.search(r"<p:spPr\s*/>", cap):
        new_cap = re.sub(r"<p:spPr\s*/>", f"<p:spPr>{xfrm}</p:spPr>", cap, count=1)
    else:
        new_cap = re.sub(r"<a:xfrm>.*?</a:xfrm>", "", cap, count=1, flags=re.S)
        new_cap = re.sub(r"<p:spPr>", lambda m: "<p:spPr>" + xfrm, new_cap, count=1)
    xml = xml.replace(cap, new_cap, 1)

    frame_xfrm = (f'<p:xfrm><a:off x="{CAP_X}" y="{table_y}"/>'
                  f'<a:ext cx="{CAP_W}" cy="{max(400000, BOTTOM - table_y)}"/></p:xfrm>')
    xml, n = re.subn(r"(</p:nvGraphicFramePr>)\s*(<p:xfrm>.*?</p:xfrm>)?",
                     lambda m: m.group(1) + frame_xfrm, xml, count=1, flags=re.S)
    if n != 1:
        sys.exit(f"FATAL: could not place the table frame on {slide}")
    open(path, "w", encoding="utf-8").write(xml)
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    deck = sys.argv[1]
    tmp = tempfile.mkdtemp(prefix="occlose-")
    try:
        with zipfile.ZipFile(deck) as z:
            z.extractall(tmp)

        restored = restore_content_types(tmp)
        cover = next(f for f in os.listdir(os.path.join(tmp, "ppt/slideLayouts"))
                     if f.endswith(".xml") and layout_name(tmp, f) == "Title Slide")

        closed, spaced = [], []
        for slide in sorted(
                (f for f in os.listdir(os.path.join(tmp, "ppt/slides")) if f.endswith(".xml")),
                key=lambda f: int(re.search(r"\d+", f).group())):
            rels = open(os.path.join(tmp, "ppt/slides/_rels", slide + ".rels"),
                        encoding="utf-8").read()
            layout = re.search(r"slideLayout\d+\.xml", rels).group(0)
            lname = layout_name(tmp, layout)
            if lname == "Content with Caption":
                if space_caption(tmp, slide):
                    spaced.append(slide)
                continue
            if lname != "Section Header":
                continue
            xml = open(os.path.join(tmp, "ppt/slides", slide), encoding="utf-8").read()
            title = "".join(re.findall(r"<a:t>([^<]*)</a:t>", xml)).strip()
            if CLOSING_TITLE.match(title):
                retarget(tmp, slide, cover)
                closed.append(slide)

        if not closed and not spaced and not restored:
            print("nothing to finish (content types complete, no closing slide, "
                  "no caption slide) — no-op")
            return

        out = deck + ".tmp"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(tmp, "[Content_Types].xml"), "[Content_Types].xml")
            for walk_root, _, files in os.walk(tmp):
                for f in sorted(files):
                    rel = os.path.relpath(os.path.join(walk_root, f), tmp)
                    if rel != "[Content_Types].xml":
                        z.write(os.path.join(walk_root, f), rel)
        os.replace(out, deck)
        if restored:
            print(f"[Content_Types].xml: restored {', '.join('.' + e for e in restored)} "
                  "(dropped by pandoc)")
        if closed:
            print(f"{', '.join(closed)}: Section Header -> Title Slide (red closing bookend)")
        if spaced:
            print(f"{', '.join(spaced)}: caption/table spacing pinned")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
